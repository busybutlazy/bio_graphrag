"""T4: group-level review endpoints (HTTP layer + error mapping)."""

import asyncio
import json

import asyncpg
from app.core.config import settings
from app.main import app
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

client = TestClient(app)

G_OK = "group:test_t4_ok"
G_REJ = "group:test_t4_rej"

_NODES = [
    {
        "id": "hormone:t4_insulin",
        "type": "Hormone",
        "label": "t4 insulin",
        "description": "d",
        "source_chunk_id": "chunk:t4",
    },
    {
        "id": "physiological_variable:t4_bg",
        "type": "PhysiologicalVariable",
        "label": "t4 bg",
        "description": "d",
        "source_chunk_id": "chunk:t4",
    },
    {
        "id": "regulatory_effect:t4_re",
        "type": "RegulatoryEffect",
        "label": "t4 re",
        "description": "d",
        "source_chunk_id": "chunk:t4",
    },
]
_EDGES = [
    {
        "id": "e:t4:has_effect",
        "type": "HAS_EFFECT",
        "source": "hormone:t4_insulin",
        "target": "regulatory_effect:t4_re",
        "source_chunk_id": "chunk:t4",
    },
    {
        "id": "e:t4:on_variable",
        "type": "ON_VARIABLE",
        "source": "regulatory_effect:t4_re",
        "target": "physiological_variable:t4_bg",
        "source_chunk_id": "chunk:t4",
    },
    {
        "id": "e:t4:decreases",
        "type": "DECREASES",
        "source": "regulatory_effect:t4_re",
        "target": "physiological_variable:t4_bg",
        "source_chunk_id": "chunk:t4",
    },
]
_NODE_IDS = [n["id"] for n in _NODES]


async def _conn():
    return await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


async def _seed(group_id):
    conn = await _conn()
    try:
        for it, kind in [(n, "node") for n in _NODES] + [(e, "edge") for e in _EDGES]:
            await conn.execute(
                "INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, group_id) "
                "VALUES ($1,$2,'create',$3,'proposed','test',$4) ON CONFLICT (item_id) DO NOTHING",
                f"curation:{group_id}:{it['id']}",
                kind,
                json.dumps({**it, "status": "proposed"}),
                group_id,
            )
    finally:
        await conn.close()


async def _cleanup():
    conn = await _conn()
    try:
        await conn.execute("DELETE FROM curation_items WHERE group_id = ANY($1)", [G_OK, G_REJ])
        await conn.execute("DELETE FROM graph_change_logs WHERE target_id = ANY($1)", [G_OK, G_REJ])
    finally:
        await conn.close()
    d = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    )
    with d.session() as s:
        s.run("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=_NODE_IDS)
    d.close()


def _reseed():
    asyncio.run(_cleanup())
    asyncio.run(_seed(G_OK))
    asyncio.run(_seed(G_REJ))


def test_list_groups_endpoint_shape():
    _reseed()
    try:
        resp = client.get("/admin/review/groups")
        assert resp.status_code == 200
        groups = {g["group_id"]: g for g in resp.json()}
        assert G_OK in groups
        g = groups[G_OK]
        assert g["schema_gate"]["result"] == "pass"
        assert g["understanding"]["is_gap"] is False
        assert "proposed_nodes" in g["proposal"]
    finally:
        asyncio.run(_cleanup())


def test_approve_endpoint():
    _reseed()
    try:
        resp = client.post(
            f"/admin/review/groups/{G_OK}/approve",
            json={"reviewer": "tester", "reason": "ok"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"group_id": G_OK, "status": "approved", "nodes": 3, "edges": 3}
    finally:
        asyncio.run(_cleanup())


def test_reject_endpoint():
    _reseed()
    try:
        resp = client.post(
            f"/admin/review/groups/{G_REJ}/reject",
            json={"reviewer": "tester", "reason": "no"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
    finally:
        asyncio.run(_cleanup())


def test_unknown_group_404():
    resp = client.post(
        "/admin/review/groups/group:does_not_exist/approve",
        json={"reviewer": "tester"},
    )
    assert resp.status_code == 404
