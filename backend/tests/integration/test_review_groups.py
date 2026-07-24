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
        await conn.execute(
            "DELETE FROM curation_items WHERE group_id = ANY($1)", [GROUP_OK, GROUP_REJ]
        )
        await conn.execute(
            "DELETE FROM graph_change_logs WHERE target_id = ANY($1)", [GROUP_OK, GROUP_REJ]
        )
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
    import pytest as _pytest

    with _pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group("group:nonexistent", "r", None))
    assert exc.value.status_code == 404
