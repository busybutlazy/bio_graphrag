"""P3: hand-made grouped-propose endpoint (POST /admin/curation/groups).

A hand-authored statement (nodes+edges sharing a group_id) is staged via the endpoint, then
must appear in the group Review queue with its two gates and approve end-to-end — closing the
propose→dispose loop. Also covers the validation guards (bad type / empty / over-cap / duplicate
id), the schema-gap flag, and admin-key auth. HTTP layer, documented {"error":{code,message}}.
"""

import asyncio

import asyncpg
from app.core.config import settings
from app.curation.service import MAX_GROUP_ELEMENTS
from app.main import app
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

client = TestClient(app)

# Complete three-part regulatory statement → schema gate passes → approvable.
_NODES = [
    {
        "id": "hormone:p3_insulin",
        "type": "Hormone",
        "label": "p3 insulin",
        "description": "d",
    },
    {
        "id": "physiological_variable:p3_bg",
        "type": "PhysiologicalVariable",
        "label": "p3 bg",
        "description": "d",
    },
    {
        "id": "regulatory_effect:p3_re",
        "type": "RegulatoryEffect",
        "label": "p3 re",
        "description": "d",
    },
]
_EDGES = [
    {
        "id": "e:p3:has_effect",
        "type": "HAS_EFFECT",
        "source": "hormone:p3_insulin",
        "target": "regulatory_effect:p3_re",
    },
    {
        "id": "e:p3:on_variable",
        "type": "ON_VARIABLE",
        "source": "regulatory_effect:p3_re",
        "target": "physiological_variable:p3_bg",
    },
    {
        "id": "e:p3:decreases",
        "type": "DECREASES",
        "source": "regulatory_effect:p3_re",
        "target": "physiological_variable:p3_bg",
    },
]
_NODE_IDS = [n["id"] for n in _NODES] + [
    "hormone:p3_thyroxine",
    "physiological_variable:p3_metabolic",
]


async def _delete_group(group_id: str) -> None:
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    try:
        await conn.execute("DELETE FROM curation_items WHERE group_id = $1", group_id)
        await conn.execute("DELETE FROM graph_change_logs WHERE target_id = $1", group_id)
    finally:
        await conn.close()


def _cleanup_graph() -> None:
    d = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with d.session() as s:
        s.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=_NODE_IDS)
    d.close()


def _neo4j_status(node_id: str):
    d = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with d.session() as s:
        rec = s.run("MATCH (n {id:$id}) RETURN n.status AS status", id=node_id).single()
    d.close()
    return rec["status"] if rec else None


def test_create_group_appears_in_review_and_approves():
    """Round-trip: hand-made statement → group Review lists it with a passing gate → approve
    writes all members into the approved graph."""
    resp = client.post(
        "/admin/curation/groups",
        json={"proposed_nodes": _NODES, "proposed_edges": _EDGES, "reason": "hand-authored"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    group_id = body["group_id"]
    assert body == {"group_id": group_id, "nodes": 3, "edges": 3}
    assert group_id.startswith("group:human:")
    try:
        # invisible to the approved graph until approved
        assert _neo4j_status("hormone:p3_insulin") is None

        # appears in the group Review queue with a live passing gate + a real sentence
        groups = {g["group_id"]: g for g in client.get("/admin/review/groups").json()}
        assert group_id in groups
        g = groups[group_id]
        assert g["proposed_by"] == "human"
        assert g["schema_gate"]["result"] == "pass"
        assert g["understanding"]["is_gap"] is False

        # approve → round-trips into the approved graph
        appr = client.post(
            f"/admin/review/groups/{group_id}/approve", json={"reviewer": "tester", "reason": "ok"}
        )
        assert appr.status_code == 200
        appr_body = appr.json()
        assert appr_body["group_id"] == group_id and appr_body["status"] == "approved"
        assert (appr_body["nodes"], appr_body["edges"]) == (3, 3)
        assert _neo4j_status("hormone:p3_insulin") == "approved"
    finally:
        asyncio.run(_delete_group(group_id))
        _cleanup_graph()


def test_invalid_type_rejected_422():
    """The injection guard: a type outside the whitelist can never reach Cypher on approval."""
    resp = client.post(
        "/admin/curation/groups",
        json={
            "proposed_nodes": [{"id": "x:1", "type": "Malicious", "label": "x", "description": "d"}]
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_empty_group_rejected_422():
    resp = client.post("/admin/curation/groups", json={"proposed_nodes": [], "proposed_edges": []})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_over_cap_rejected_422():
    nodes = [
        {"id": f"hormone:p3_cap{i}", "type": "Hormone", "label": f"n{i}", "description": "d"}
        for i in range(MAX_GROUP_ELEMENTS + 1)
    ]
    resp = client.post("/admin/curation/groups", json={"proposed_nodes": nodes})
    assert resp.status_code == 422
    assert str(MAX_GROUP_ELEMENTS) in resp.json()["error"]["message"]


def test_duplicate_id_within_group_rejected_422():
    """A repeated id across the combined node+edge set would PK-collide → rejected up front."""
    dup = {"id": "hormone:p3_dup", "type": "Hormone", "label": "d", "description": "d"}
    resp = client.post("/admin/curation/groups", json={"proposed_nodes": [dup, dict(dup)]})
    assert resp.status_code == 422
    assert "duplicate" in resp.json()["error"]["message"]


def test_possible_schema_gap_flag_surfaces_needs_schema_extension():
    """A flagged non-pattern group renders a gap and the gate says needs_schema_extension (D5)."""
    nodes = [
        {
            "id": "hormone:p3_thyroxine",
            "type": "Hormone",
            "label": "thyroxine",
            "description": "d",
            "source_chunk_id": "chunk:p3",
        },
        {
            "id": "physiological_variable:p3_metabolic",
            "type": "PhysiologicalVariable",
            "label": "metabolic rate",
            "description": "d",
            "source_chunk_id": "chunk:p3",
        },
    ]
    resp = client.post(
        "/admin/curation/groups", json={"proposed_nodes": nodes, "possible_schema_gap": True}
    )
    assert resp.status_code == 201
    group_id = resp.json()["group_id"]
    try:
        g = next(x for x in client.get("/admin/review/groups").json() if x["group_id"] == group_id)
        assert g["understanding"]["is_gap"] is True
        assert g["schema_gate"]["result"] == "needs_schema_extension"
    finally:
        asyncio.run(_delete_group(group_id))
        _cleanup_graph()


def test_endpoint_is_admin_gated(monkeypatch):
    """With ADMIN_API_KEYS configured, the propose endpoint requires a valid X-API-Key."""
    monkeypatch.setattr(settings, "admin_api_keys", "acme:secret123")
    node = [{"id": "hormone:p3_auth", "type": "Hormone", "label": "a", "description": "d"}]

    assert client.post("/admin/curation/groups", json={"proposed_nodes": node}).status_code == 401
    assert (
        client.post(
            "/admin/curation/groups", json={"proposed_nodes": node}, headers={"X-API-Key": "wrong"}
        ).status_code
        == 401
    )

    ok = client.post(
        "/admin/curation/groups", json={"proposed_nodes": node}, headers={"X-API-Key": "secret123"}
    )
    assert ok.status_code == 201, ok.text
    asyncio.run(_delete_group(ok.json()["group_id"]))


def _neo4j_delete(ids):
    d = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with d.session() as s:
        s.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=ids)
    d.close()


def test_dangling_edge_endpoint_rejected_422():
    """Review F2: an edge whose endpoint resolves to neither a proposed node nor an approved node
    is rejected at propose time — otherwise the gate passes and the edge is silently dropped on
    approval (false audit)."""
    body = {
        "proposed_nodes": [
            {"id": "hormone:f2_a", "type": "Hormone", "label": "a", "description": "d"}
        ],
        "proposed_edges": [
            {
                "id": "e:f2:dangle",
                "type": "SECRETES",
                "source": "hormone:f2_a",
                "target": "structure:f2_nonexistent",
            }
        ],
    }
    resp = client.post("/admin/curation/groups", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"
    assert "structure:f2_nonexistent" in resp.json()["error"]["message"]


def test_edge_with_empty_endpoint_rejected_422():
    """Review R4: a present-but-empty endpoint (`source: ""`) is the same silent-drop hole as a
    dangling one — the schema accepts an empty string, then MATCH no-ops at approval."""
    body = {
        "proposed_nodes": [
            {"id": "hormone:r4_a", "type": "Hormone", "label": "a", "description": "d"}
        ],
        "proposed_edges": [
            {"id": "e:r4:empty", "type": "SECRETES", "source": "hormone:r4_a", "target": ""}
        ],
    }
    resp = client.post("/admin/curation/groups", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_edge_to_approved_node_is_accepted():
    """F2: an edge endpoint that resolves to an already-approved node (not proposed in this group)
    is accepted — the guard allows references into the approved graph."""
    # stage + approve a node so it exists as approved
    seed = client.post(
        "/admin/curation/groups",
        json={
            "proposed_nodes": [
                {
                    "id": "structure:f2_approved",
                    "type": "Structure",
                    "label": "器官",
                    "description": "d",
                }
            ]
        },
    )
    seed_gid = seed.json()["group_id"]
    assert (
        client.post(
            f"/admin/review/groups/{seed_gid}/approve", json={"reviewer": "t", "reason": "ok"}
        ).status_code
        == 200
    )
    # now an edge from a fresh proposed node to that approved node must be accepted
    resp = client.post(
        "/admin/curation/groups",
        json={
            "proposed_nodes": [
                {"id": "hormone:f2_src", "type": "Hormone", "label": "h", "description": "d"}
            ],
            "proposed_edges": [
                {
                    "id": "e:f2:toapproved",
                    "type": "PART_OF",
                    "source": "hormone:f2_src",
                    "target": "structure:f2_approved",
                }
            ],
        },
    )
    try:
        assert resp.status_code == 201, resp.text
    finally:
        asyncio.run(_delete_group(seed_gid))
        if resp.status_code == 201:
            asyncio.run(_delete_group(resp.json()["group_id"]))
        _neo4j_delete(["structure:f2_approved", "hormone:f2_src"])


def test_reason_is_persisted_and_surfaced():
    """Review F4: the propose-time reason must survive and be visible to the reviewer — persisted
    in schema_check and returned by GET /admin/review/groups as propose_reason."""
    resp = client.post(
        "/admin/curation/groups",
        json={
            "proposed_nodes": [
                {"id": "hormone:f4_r", "type": "Hormone", "label": "h", "description": "d"}
            ],
            "reason": "教學上想補這個內分泌概念",
        },
    )
    assert resp.status_code == 201
    gid = resp.json()["group_id"]
    try:
        g = next(x for x in client.get("/admin/review/groups").json() if x["group_id"] == gid)
        assert g["propose_reason"] == "教學上想補這個內分泌概念"
    finally:
        asyncio.run(_delete_group(gid))
        _neo4j_delete(["hormone:f4_r"])
