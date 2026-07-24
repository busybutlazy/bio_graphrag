"""T2: group-level two-gate review — list_groups / approve_group / reject_group.

Inserts proposal groups (nodes+edges sharing a group_id) directly, then verifies the
schema gate + expert-lens assembly, that approve writes all members to Neo4j + one audit
row (invariant: absent before, present after), and that reject writes nothing.
"""

import asyncio
import json

import asyncpg
import pytest
from app.core.config import settings
from app.curation import service
from neo4j import GraphDatabase

GROUP_OK = "group:test_t2_ok"
GROUP_REJ = "group:test_t2_rej"
GROUP_BAD = "group:test_t2_gatefail"
GROUP_ACT = "group:test_t2_badaction"
_ALL_GROUPS = [GROUP_OK, GROUP_REJ, GROUP_BAD, GROUP_ACT]

_NODES = [
    {
        "id": "hormone:t2_insulin",
        "type": "Hormone",
        "label": "t2 insulin",
        "description": "d",
        "source_chunk_id": "chunk:t2",
    },
    {
        "id": "physiological_variable:t2_bg",
        "type": "PhysiologicalVariable",
        "label": "t2 bg",
        "description": "d",
        "source_chunk_id": "chunk:t2",
    },
    {
        "id": "regulatory_effect:t2_re",
        "type": "RegulatoryEffect",
        "label": "t2 re",
        "description": "d",
        "source_chunk_id": "chunk:t2",
    },
]
_EDGES = [
    {
        "id": "e:t2:has_effect",
        "type": "HAS_EFFECT",
        "source": "hormone:t2_insulin",
        "target": "regulatory_effect:t2_re",
        "source_chunk_id": "chunk:t2",
    },
    {
        "id": "e:t2:on_variable",
        "type": "ON_VARIABLE",
        "source": "regulatory_effect:t2_re",
        "target": "physiological_variable:t2_bg",
        "source_chunk_id": "chunk:t2",
    },
    {
        "id": "e:t2:decreases",
        "type": "DECREASES",
        "source": "regulatory_effect:t2_re",
        "target": "physiological_variable:t2_bg",
        "source_chunk_id": "chunk:t2",
    },
]
_NODE_IDS = [n["id"] for n in _NODES]


async def _conn() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


async def _seed_group(group_id: str) -> None:
    conn = await _conn()
    try:
        for n in _NODES:
            await conn.execute(
                "INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, group_id) "
                "VALUES ($1,'node','create',$2,'proposed','test',$3) ON CONFLICT (item_id) DO NOTHING",
                f"curation:{group_id}:{n['id']}",
                json.dumps({**n, "status": "proposed"}),
                group_id,
            )
        for e in _EDGES:
            await conn.execute(
                "INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, group_id) "
                "VALUES ($1,'edge','create',$2,'proposed','test',$3) ON CONFLICT (item_id) DO NOTHING",
                f"curation:{group_id}:{e['id']}",
                json.dumps({**e, "status": "proposed"}),
                group_id,
            )
    finally:
        await conn.close()


async def _cleanup() -> None:
    conn = await _conn()
    try:
        await conn.execute("DELETE FROM curation_items WHERE group_id = ANY($1)", _ALL_GROUPS)
        await conn.execute("DELETE FROM graph_change_logs WHERE target_id = ANY($1)", _ALL_GROUPS)
    finally:
        await conn.close()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with driver.session() as s:
        s.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=_NODE_IDS)
    driver.close()


@pytest.fixture(autouse=True)
def groups():
    asyncio.run(_cleanup())
    asyncio.run(_seed_group(GROUP_OK))
    asyncio.run(_seed_group(GROUP_REJ))
    yield
    asyncio.run(_cleanup())


def _neo4j_node_status(node_id: str):
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with driver.session() as s:
        rec = s.run("MATCH (n {id:$id}) RETURN n.status AS status", id=node_id).single()
    driver.close()
    return rec["status"] if rec else None


async def _latest_after_state(target_id: str):
    conn = await _conn()
    try:
        row = await conn.fetchrow(
            "SELECT after_state FROM graph_change_logs WHERE target_id=$1 "
            "ORDER BY created_at DESC LIMIT 1",
            target_id,
        )
        return row["after_state"] if row else None
    finally:
        await conn.close()


async def _latest_action(target_id: str):
    conn = await _conn()
    try:
        return await conn.fetchrow(
            "SELECT action, actor FROM graph_change_logs WHERE target_id=$1 ORDER BY created_at DESC LIMIT 1",
            target_id,
        )
    finally:
        await conn.close()


def test_list_groups_assembles_proposal_with_gates():
    groups = {g["group_id"]: g for g in asyncio.run(service.list_groups())}
    assert GROUP_OK in groups
    g = groups[GROUP_OK]
    assert len(g["proposal"]["proposed_nodes"]) == 3
    assert len(g["proposal"]["proposed_edges"]) == 3
    assert g["schema_gate"]["result"] == "pass"  # schema gate: complete three-part
    assert g["understanding"]["is_gap"] is False  # expert lens: a real sentence


def test_approve_group_writes_all_and_audits():
    # invariant: node absent from Neo4j before approval
    assert _neo4j_node_status("hormone:t2_insulin") is None

    res = asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", "looks correct"))
    assert res == {"group_id": GROUP_OK, "status": "approved", "nodes": 3, "edges": 3}

    # invariant: now present + approved
    assert _neo4j_node_status("hormone:t2_insulin") == "approved"

    log = asyncio.run(_latest_action(GROUP_OK))
    assert log is not None and log["action"] == "approve" and log["actor"] == "test_reviewer"

    # group no longer listed as proposed
    assert GROUP_OK not in {g["group_id"] for g in asyncio.run(service.list_groups())}


def test_reject_group_writes_nothing_and_audits():
    res = asyncio.run(service.reject_group(GROUP_REJ, "test_reviewer", "not needed"))
    assert res["status"] == "rejected"
    # nothing written to Neo4j
    assert _neo4j_node_status("hormone:t2_insulin") is None
    log = asyncio.run(_latest_action(GROUP_REJ))
    assert log is not None and log["action"] == "reject"


def test_missing_group_404():
    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group("group:nonexistent", "r", None))
    assert exc.value.status_code == 404


# --- guards added after review (B1 collision, H2 enforcing gate, L2 action, M3 409) -----


async def _insert_item(group_id, item, kind, action="create"):
    conn = await _conn()
    try:
        await conn.execute(
            "INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, group_id) "
            "VALUES ($1,$2,$3,$4,'proposed','test',$5) ON CONFLICT (item_id) DO NOTHING",
            f"curation:{group_id}:{item['id']}",
            kind,
            action,
            json.dumps({**item, "status": "proposed"}),
            group_id,
        )
    finally:
        await conn.close()


def _write_approved_node(node_id: str) -> None:
    d = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with d.session() as s:
        s.run(
            "MERGE (n:Hormone {id:$id}) SET n.label='pre-existing', n.status='approved'",
            id=node_id,
        )
    d.close()


def test_approve_refuses_when_a_member_already_exists_approved():
    """B1: approving must never MERGE-overwrite curated knowledge."""
    _write_approved_node("hormone:t2_insulin")
    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", None))
    assert exc.value.status_code == 409
    assert "already exist" in exc.value.message
    # and the pre-existing node was left untouched
    assert _neo4j_node_status("hormone:t2_insulin") == "approved"


def test_approve_refuses_when_schema_gate_fails():
    """H2: the Schema gate is enforcing — a malformed group cannot reach the graph."""
    # RegulatoryEffect with HAS_EFFECT but no ON_VARIABLE / direction edge -> fail_pattern
    asyncio.run(_insert_item(GROUP_BAD, _NODES[0], "node"))
    asyncio.run(_insert_item(GROUP_BAD, _NODES[2], "node"))
    asyncio.run(_insert_item(GROUP_BAD, _EDGES[0], "edge"))

    groups = {g["group_id"]: g for g in asyncio.run(service.list_groups())}
    assert groups[GROUP_BAD]["schema_gate"]["result"] == "fail_pattern"

    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group(GROUP_BAD, "test_reviewer", None))
    assert exc.value.status_code == 409
    assert "schema gate" in exc.value.message
    # nothing written
    assert _neo4j_node_status("hormone:t2_insulin") is None


def test_approve_refuses_non_create_action():
    """L2: the group path only implements 'create'."""
    asyncio.run(_insert_item(GROUP_ACT, _NODES[0], "node", action="delete"))
    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group(GROUP_ACT, "test_reviewer", None))
    assert exc.value.status_code == 422


def test_double_approve_is_409():
    """M3: no proposed items left -> 409."""
    asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", None))
    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", None))
    assert exc.value.status_code == 409


def test_approve_audit_records_full_payloads():
    """M1: the audit row must reconstruct what entered the graph, not just ids."""
    asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", "ok"))
    after = asyncio.run(_latest_after_state(GROUP_OK))
    after = json.loads(after) if isinstance(after, str) else after
    assert len(after["nodes"]) == 3 and len(after["edges"]) == 3
    assert after["nodes"][0]["label"]  # full payloads, not bare ids
    assert after["item_ids"]
