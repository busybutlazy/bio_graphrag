"""T2: group-level two-gate review — list_groups / approve_group / reject_group.

Inserts proposal groups (nodes+edges sharing a group_id) directly, then verifies the
schema gate + expert-lens assembly, that approve writes all members to Neo4j + one audit
row (invariant: absent before, present after), and that reject writes nothing.
"""

import asyncio
import json
import uuid

import asyncpg
import pytest
from app.core.config import settings
from app.curation import service
from neo4j import GraphDatabase

from ingestion.pipeline.load_postgres import stage_demo_review_group

GROUP_OK = "group:test_t2_ok"
GROUP_REJ = "group:test_t2_rej"
GROUP_BAD = "group:test_t2_gatefail"
GROUP_ACT = "group:test_t2_badaction"
GROUP_GAP = "group:test_t2_gap"
GROUP_PLAIN = "group:test_t2_plain"
GROUP_REC = "group:test_gap_record"
GROUP_REF = "group:test_dangling_ref"
_ALL_GROUPS = [
    GROUP_OK,
    GROUP_REJ,
    GROUP_BAD,
    GROUP_ACT,
    GROUP_GAP,
    GROUP_PLAIN,
    GROUP_REC,
    GROUP_REF,
]

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
# The gap-group and reference-group members too: neither should ever reach Neo4j, but a *regression*
# (an approve that should have been refused) would write them — teardown must be able to clean that
# up, or the next run inherits a poisoned graph.
_NODE_IDS = [n["id"] for n in _NODES] + [
    "hormone:test_rec_a",
    "hormone:test_rec_b",
    "interaction:t1c_antag",
    "physiological_variable:t1c_var",
    "regulatory_effect:t1c_absent_a",
    "regulatory_effect:t1c_absent_b",
]


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


async def _item_statuses(group_id: str) -> list[str]:
    conn = await _conn()
    try:
        rows = await conn.fetch("SELECT status FROM curation_items WHERE group_id = $1", group_id)
        return [r["status"] for r in rows]
    finally:
        await conn.close()


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
    assert res["status"] == "approved" and (res["nodes"], res["edges"]) == (3, 3)

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


def test_approve_reuses_an_already_approved_member_without_rewriting_it():
    """Curated wording must survive a later proposal, and a shared concept must not block approval.

    This replaces an earlier guard that refused the whole group. In a graph one node carries many
    relationships, so a concept every statement in a paragraph mentions appears in several groups —
    refusing on that basis let a reviewer approve only one statement per paragraph, whichever they
    picked. The real risk was `write_nodes` following its MERGE with an unconditional SET of
    label/description; not writing the member at all removes that risk outright.
    """
    _write_approved_node("hormone:t2_insulin")  # curated label: 'pre-existing'

    res = asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", None))

    assert res["status"] == "approved"
    assert res["reused_nodes"] == 1
    assert res["nodes"] == 2  # the other two members were written; the curated one was not

    # the curated version won — the proposal's label did NOT replace it
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with driver.session() as session:
        label = session.run("MATCH (n {id:'hormone:t2_insulin'}) RETURN n.label AS l").single()["l"]
    driver.close()
    assert label == "pre-existing"

    # and the reuse is recorded, not implied
    after = asyncio.run(_latest_after_state(GROUP_OK))
    after = json.loads(after) if isinstance(after, str) else after
    assert after["reused_nodes"] == ["hormone:t2_insulin"]


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


def test_approve_group_rolls_back_postgres_on_neo4j_failure(monkeypatch):
    """A4: a mid-write Neo4j failure aborts the Postgres commit.

    approve_group writes nodes then edges to Neo4j *inside* the pg transaction, then flips
    items + writes the audit row. Injecting a failure at the edge write must leave the
    Postgres side untouched — every item still ``proposed``, no ``approve`` audit row.

    Scope note (documented cross-DB limit): the nodes MERGE'd before the failure are NOT
    rolled back (Neo4j is not in the pg transaction). They are idempotent MERGEs, so a
    later retry re-writes them and completes; the fixture teardown DETACH-DELETEs them.
    """

    def boom(*_a, **_k):
        raise RuntimeError("injected: neo4j edge write failed")

    monkeypatch.setattr(service.load_neo4j, "write_edges", boom)

    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", "will fail"))

    # Postgres rolled back: nothing flipped, nothing logged.
    statuses = asyncio.run(_item_statuses(GROUP_OK))
    assert statuses and all(s == "proposed" for s in statuses)
    assert asyncio.run(_latest_action(GROUP_OK)) is None


async def _stage_demo(group_id, candidate, gap=False):
    conn = await _conn()
    try:
        await stage_demo_review_group(conn, group_id, candidate, possible_schema_gap=gap)
    finally:
        await conn.close()


def test_seeded_gap_flag_flows_to_gate_and_lens():
    """D5 threading: a flagged group renders a gap and the gate says needs_schema_extension."""
    candidate = {
        "nodes": [
            {
                "id": "hormone:test_gap_a",
                "type": "Hormone",
                "label": "A",
                "description": "d",
                "source_chunk_id": "c",
            },
            {
                "id": "hormone:test_gap_b",
                "type": "Hormone",
                "label": "B",
                "description": "d",
                "source_chunk_id": "c",
            },
        ],
        "edges": [],
    }
    asyncio.run(_stage_demo(GROUP_GAP, candidate, gap=True))
    g = next(x for x in asyncio.run(service.list_groups()) if x["group_id"] == GROUP_GAP)
    assert g["understanding"]["is_gap"] is True
    assert g["schema_gate"]["result"] == "needs_schema_extension"


def test_seeded_unflagged_no_pattern_is_plain_summary_and_passes_gate():
    """D5 threading: an unflagged schema-valid non-pattern group is a plain summary, gate pass."""
    candidate = {
        "nodes": [
            {
                "id": "disease:test_plain",
                "type": "Disease",
                "label": "測試疾病",
                "description": "d",
                "source_chunk_id": "c",
            },
            {
                "id": "structure:test_plain_organ",
                "type": "Structure",
                "label": "測試器官",
                "description": "d",
                "source_chunk_id": "c",
            },
        ],
        "edges": [
            {
                "id": "e:test_plain",
                "type": "PART_OF",
                "source": "structure:test_plain_organ",
                "target": "disease:test_plain",
                "source_chunk_id": "c",
            },
        ],
    }
    asyncio.run(_stage_demo(GROUP_PLAIN, candidate, gap=False))
    g = next(x for x in asyncio.run(service.list_groups()) if x["group_id"] == GROUP_PLAIN)
    assert g["understanding"]["is_gap"] is False
    assert "無法" not in g["understanding"]["text"]
    assert g["schema_gate"]["result"] == "pass"


def test_approve_audit_records_full_payloads():
    """M1: the audit row must reconstruct what entered the graph, not just ids."""
    asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", "ok"))
    after = asyncio.run(_latest_after_state(GROUP_OK))
    after = json.loads(after) if isinstance(after, str) else after
    assert len(after["nodes"]) == 3 and len(after["edges"]) == 3
    assert after["nodes"][0]["label"]  # full payloads, not bare ids
    assert after["item_ids"]


# --- T1c: a group may reference a node it does not propose, but only once that node exists ----
# (changes/extract-per-group-staging). The extraction path splits an interaction away from the
# effects it uses, so the interaction group points at nodes another group proposes. Approving it
# first would write an edge into nothing.


_ABSENT_EFFECTS = ["regulatory_effect:t1c_absent_a", "regulatory_effect:t1c_absent_b"]


def _seed_reference_group():
    """An interaction-shaped group exactly as the splitter produces one: it proposes its own anchor
    (plus the variable it acts on) and *references* the two effects, which are other statements.

    Built to **pass** the Schema gate — two USES_EFFECT plus an ON_VARIABLE satisfy the Interaction
    pattern — so the run reaches the endpoint guard instead of stopping at the gate.
    """
    nodes = [
        {
            "id": "interaction:t1c_antag",
            "type": "Interaction",
            "label": "t1c antagonism",
            "description": "d",
            "source_chunk_id": "chunk:t1c",
            "properties": {"interaction_type": "antagonism"},
        },
        {
            "id": "physiological_variable:t1c_var",
            "type": "PhysiologicalVariable",
            "label": "t1c variable",
            "description": "d",
            "source_chunk_id": "chunk:t1c",
        },
    ]
    edges = [
        {
            "id": f"e:t1c:uses_{i}",
            "type": "USES_EFFECT",
            "source": "interaction:t1c_antag",
            "target": effect_id,
            "source_chunk_id": "chunk:t1c",
        }
        for i, effect_id in enumerate(_ABSENT_EFFECTS)
    ] + [
        {
            "id": "e:t1c:on_var",
            "type": "ON_VARIABLE",
            "source": "interaction:t1c_antag",
            "target": "physiological_variable:t1c_var",
            "source_chunk_id": "chunk:t1c",
        }
    ]
    for node in nodes:
        asyncio.run(_insert_item(GROUP_REF, node, "node"))
    for edge in edges:
        asyncio.run(_insert_item(GROUP_REF, edge, "edge"))


def _drop_nodes(ids):
    d = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with d.session() as s:
        s.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=ids)
    d.close()


def test_approve_refuses_an_edge_endpoint_that_exists_nowhere():
    _seed_reference_group()
    groups = {g["group_id"]: g for g in asyncio.run(service.list_groups())}
    assert groups[GROUP_REF]["schema_gate"]["result"] == "pass"  # the gate is not what stops this

    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group(GROUP_REF, "test_reviewer", None))
    assert exc.value.status_code == 409
    assert all(effect_id in exc.value.message for effect_id in _ABSENT_EFFECTS)

    # nothing written: a refused approval must not leave the anchor behind
    assert _neo4j_node_status("interaction:t1c_antag") is None
    assert all(s == "proposed" for s in asyncio.run(_item_statuses(GROUP_REF)))


def test_approve_succeeds_once_the_referenced_nodes_are_approved():
    """The ordering dependency is resolvable, not a dead end — the point of splitting them apart."""
    _seed_reference_group()
    d = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    try:
        with d.session() as s:
            for effect_id in _ABSENT_EFFECTS:
                s.run(
                    "MERGE (n:RegulatoryEffect {id:$id}) "
                    "SET n.label='pre-approved', n.status='approved'",
                    id=effect_id,
                )
        d.close()

        res = asyncio.run(service.approve_group(GROUP_REF, "test_reviewer", None))
        assert res["status"] == "approved"
        assert _neo4j_node_status("interaction:t1c_antag") == "approved"
    finally:
        _drop_nodes([*_ABSENT_EFFECTS, "interaction:t1c_antag", "physiological_variable:t1c_var"])


def test_existing_groups_still_approve_under_the_endpoint_guard():
    """Regression: the guard must not block groups whose edges stay inside the group."""
    res = asyncio.run(service.approve_group(GROUP_OK, "test_reviewer", None))
    assert res["status"] == "approved" and (res["nodes"], res["edges"]) == (3, 3)


# --- record-as-gap: the third dispose outcome (changes/group-review-gap-outcome) ----------

_GAP_CANDIDATE = {
    "nodes": [
        {
            "id": "hormone:test_rec_a",
            "type": "Hormone",
            "label": "A",
            "description": "d",
            "source_chunk_id": "c",
        },
        {
            "id": "hormone:test_rec_b",
            "type": "Hormone",
            "label": "B",
            "description": "d",
            "source_chunk_id": "c",
        },
    ],
    "edges": [],
}


def _stage_gap_group(group_id: str = GROUP_REC) -> None:
    """Stage a group the Schema gate flags ``needs_schema_extension`` (the only gap-eligible one)."""
    asyncio.run(_stage_demo(group_id, _GAP_CANDIDATE, gap=True))


async def _gap_log_rows(group_id: str) -> list:
    conn = await _conn()
    try:
        return await conn.fetch(
            "SELECT action, actor, reason, after_state FROM graph_change_logs "
            "WHERE target_id = $1 AND action = 'schema_gap'",
            group_id,
        )
    finally:
        await conn.close()


def test_record_gap_flips_status_audits_once_and_leaves_queue():
    """Happy path: status -> schema_gap, exactly one audit row carrying the type, no Neo4j write."""
    _stage_gap_group()
    assert GROUP_REC in {g["group_id"] for g in asyncio.run(service.list_groups())}

    res = asyncio.run(
        service.record_group_gap(GROUP_REC, "test_reviewer", "schema 表達不了", "permissive_effect")
    )
    assert res == {
        "group_id": GROUP_REC,
        "status": "schema_gap",
        "schema_gap_type": "permissive_effect",
    }

    statuses = asyncio.run(_item_statuses(GROUP_REC))
    assert statuses and all(s == "schema_gap" for s in statuses)

    rows = asyncio.run(_gap_log_rows(GROUP_REC))
    assert len(rows) == 1  # audit uniqueness
    assert rows[0]["actor"] == "test_reviewer" and rows[0]["reason"] == "schema 表達不了"
    after = rows[0]["after_state"]
    after = json.loads(after) if isinstance(after, str) else after
    assert after["schema_gap_type"] == "permissive_effect"
    assert len(after["item_ids"]) == 2

    # nothing written to the graph, and the group left the review queue
    assert _neo4j_node_status("hormone:test_rec_a") is None
    assert GROUP_REC not in {g["group_id"] for g in asyncio.run(service.list_groups())}


def test_double_record_gap_is_409():
    _stage_gap_group()
    asyncio.run(service.record_group_gap(GROUP_REC, "r", None, "unknown"))
    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.record_group_gap(GROUP_REC, "r", None, "unknown"))
    assert exc.value.status_code == 409
    assert len(asyncio.run(_gap_log_rows(GROUP_REC))) == 1  # still exactly one audit row


def test_record_gap_only_touches_proposed_members():
    """A member already disposed of stays as it was; only the proposed ones flip."""
    _stage_gap_group()
    frozen = f"curation:{GROUP_REC}:hormone:test_rec_b"

    async def _freeze():
        conn = await _conn()
        try:
            await conn.execute(
                "UPDATE curation_items SET status = 'rejected' WHERE item_id = $1", frozen
            )
        finally:
            await conn.close()

    asyncio.run(_freeze())
    asyncio.run(service.record_group_gap(GROUP_REC, "r", None, "unknown"))

    async def _by_item():
        conn = await _conn()
        try:
            rows = await conn.fetch(
                "SELECT item_id, status FROM curation_items WHERE group_id = $1", GROUP_REC
            )
            return {r["item_id"]: r["status"] for r in rows}
        finally:
            await conn.close()

    statuses = asyncio.run(_by_item())
    assert statuses[frozen] == "rejected"  # untouched
    assert all(s == "schema_gap" for k, s in statuses.items() if k != frozen)

    rows = asyncio.run(_gap_log_rows(GROUP_REC))
    assert len(rows) == 1
    after = rows[0]["after_state"]
    after = json.loads(after) if isinstance(after, str) else after
    assert after["item_ids"] == [f"curation:{GROUP_REC}:hormone:test_rec_a"]


def test_record_gap_is_atomic(monkeypatch):
    """Condition 3: the status UPDATE and the audit INSERT commit together or not at all."""
    _stage_gap_group()

    async def boom(*_a, **_k):
        raise RuntimeError("injected: audit insert failed")

    monkeypatch.setattr(service, "_log_change", boom)

    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(service.record_group_gap(GROUP_REC, "r", None, "unknown"))

    statuses = asyncio.run(_item_statuses(GROUP_REC))
    assert statuses and all(s == "proposed" for s in statuses)  # UPDATE rolled back
    assert asyncio.run(_gap_log_rows(GROUP_REC)) == []


def test_approve_refuses_a_flagged_schema_gap_group():
    """The Schema gate must be enforcing *server-side* for a flagged gap group too.

    Regression: the gap flag lives in ``schema_check``, not in the payloads, so a proposal
    assembled without it evaluates as ``pass`` — the API would have approved a group the queue
    and the UI both show as ``needs_schema_extension``, leaving the gate enforced by a disabled
    button only.
    """
    _stage_gap_group()
    g = next(x for x in asyncio.run(service.list_groups()) if x["group_id"] == GROUP_REC)
    assert g["schema_gate"]["result"] == "needs_schema_extension"

    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.approve_group(GROUP_REC, "test_reviewer", None))
    assert exc.value.status_code == 409
    assert "needs_schema_extension" in exc.value.message

    assert _neo4j_node_status("hormone:test_rec_a") is None
    assert all(s == "proposed" for s in asyncio.run(_item_statuses(GROUP_REC)))


def test_record_gap_refuses_a_non_gap_group():
    """D2: record-as-gap is only for needs_schema_extension — a passing group is a 409."""
    with pytest.raises(service.CurationError) as exc:
        asyncio.run(service.record_group_gap(GROUP_OK, "r", None, "unknown"))
    assert exc.value.status_code == 409
    assert "needs_schema_extension" in exc.value.message
    assert all(s == "proposed" for s in asyncio.run(_item_statuses(GROUP_OK)))


def test_record_gap_rejects_unknown_type_blank_reviewer_and_missing_group():
    _stage_gap_group()
    with pytest.raises(service.CurationError) as exc:  # not in the taxonomy whitelist
        asyncio.run(service.record_group_gap(GROUP_REC, "r", None, "not_a_real_gap_type"))
    assert exc.value.status_code == 422

    with pytest.raises(service.CurationError) as exc:  # blank reviewer
        asyncio.run(service.record_group_gap(GROUP_REC, "   ", None, "unknown"))
    assert exc.value.status_code == 422

    with pytest.raises(service.CurationError) as exc:  # unknown group
        asyncio.run(service.record_group_gap("group:nonexistent", "r", None, "unknown"))
    assert exc.value.status_code == 404

    # none of the rejected calls disposed of anything
    assert all(s == "proposed" for s in asyncio.run(_item_statuses(GROUP_REC)))


def test_create_group_is_atomic_on_failure(monkeypatch):
    """P3 condition 2: a failure partway through staging rolls the whole group back.

    Pin group_id (fixed uuid), pre-insert a decoy occupying node_b's item_id so the *second*
    insert PK-collides; node_a (inserted first, same transaction) must not survive.
    """
    fixed = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    monkeypatch.setattr(service.uuid, "uuid4", lambda: fixed)
    group_id = f"group:human:{fixed}"
    node_a = {"id": "hormone:atomic_a", "type": "Hormone", "label": "a", "description": "d"}
    node_b = {"id": "hormone:atomic_b", "type": "Hormone", "label": "b", "description": "d"}

    async def _run():
        conn = await _conn()
        try:
            await conn.execute(
                "INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, group_id) "
                "VALUES ($1,'node','create',$2,'proposed','test',$3)",
                f"curation:{group_id}:{node_b['id']}",
                json.dumps(node_b),
                group_id,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await service.create_group([node_a, node_b], [])
            rows = await conn.fetch(
                "SELECT item_id FROM curation_items WHERE group_id = $1 ORDER BY item_id", group_id
            )
            return [r["item_id"] for r in rows]
        finally:
            await conn.execute("DELETE FROM curation_items WHERE group_id = $1", group_id)
            await conn.close()

    remaining = asyncio.run(_run())
    # only the decoy survives — node_a's insert was rolled back with the failed transaction
    assert remaining == [f"curation:{group_id}:{node_b['id']}"]
