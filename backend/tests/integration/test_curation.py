import asyncio

import asyncpg
import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from app.core.config import settings
from app.main import app
from ingestion.pipeline import run as ingestion_run


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def neo4j_driver():
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password),
    )
    yield driver
    driver.close()


def _cleanup_node(driver, node_id: str) -> None:
    with driver.session() as session:
        session.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)


async def _delete_test_curation_items() -> None:
    conn = await asyncpg.connect(
        host=settings.postgres_host, port=settings.postgres_port, database=settings.postgres_db,
        user=settings.postgres_user, password=settings.postgres_password,
    )
    try:
        await conn.execute("DELETE FROM graph_change_logs WHERE target_id LIKE '%test_curation%'")
        await conn.execute("DELETE FROM curation_items WHERE item_id LIKE '%test_curation%'")
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
def cleanup_curation_items():
    yield
    asyncio.run(_delete_test_curation_items())


async def _fetch_change_log(target_id: str):
    conn = await asyncpg.connect(
        host=settings.postgres_host, port=settings.postgres_port, database=settings.postgres_db,
        user=settings.postgres_user, password=settings.postgres_password,
    )
    try:
        return await conn.fetchrow(
            "SELECT action, actor, reason FROM graph_change_logs WHERE target_id = $1 ORDER BY created_at DESC LIMIT 1",
            target_id,
        )
    finally:
        await conn.close()


def test_proposed_node_not_written_until_reviewed(client, neo4j_driver):
    payload = {
        "id": "hormone:test_curation_pending", "type": "Hormone",
        "label": "Test Pending Hormone", "description": "test",
    }
    resp = client.post("/admin/curation/items", json={
        "item_type": "node", "action": "create", "payload": payload, "reason": "test",
    })
    assert resp.status_code == 201

    with neo4j_driver.session() as session:
        record = session.run("MATCH (n {id: $id}) RETURN n", id=payload["id"]).single()
    assert record is None


def test_reject_never_writes_to_neo4j_and_logs_change(client, neo4j_driver):
    payload = {
        "id": "hormone:test_curation_reject", "type": "Hormone",
        "label": "Test Reject Hormone", "description": "test",
    }
    create_resp = client.post("/admin/curation/items", json={
        "item_type": "node", "action": "create", "payload": payload, "reason": "test proposal",
    })
    item_id = create_resp.json()["item_id"]

    reject_resp = client.post(f"/admin/curation/items/{item_id}/reject", json={
        "reviewer": "test_reviewer", "reason": "not needed",
    })
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    with neo4j_driver.session() as session:
        record = session.run("MATCH (n {id: $id}) RETURN n", id=payload["id"]).single()
    assert record is None

    log = asyncio.run(_fetch_change_log(payload["id"]))
    assert log is not None
    assert log["action"] == "reject"
    assert log["actor"] == "test_reviewer"


def test_approve_writes_to_neo4j_and_logs_change(client, neo4j_driver):
    payload = {
        "id": "hormone:test_curation_approve", "type": "Hormone",
        "label": "Test Approve Hormone", "description": "test",
    }
    create_resp = client.post("/admin/curation/items", json={
        "item_type": "node", "action": "create", "payload": payload, "reason": "test proposal",
    })
    item_id = create_resp.json()["item_id"]

    approve_resp = client.post(f"/admin/curation/items/{item_id}/approve", json={
        "reviewer": "test_reviewer", "reason": "looks good",
    })
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    with neo4j_driver.session() as session:
        record = session.run("MATCH (n {id: $id}) RETURN n.status AS status", id=payload["id"]).single()
    assert record is not None
    assert record["status"] == "approved"

    log = asyncio.run(_fetch_change_log(payload["id"]))
    assert log is not None
    assert log["action"] == "approve"

    _cleanup_node(neo4j_driver, payload["id"])


def test_delete_edge_soft_deletes_and_is_excluded_from_neighbors(client, neo4j_driver):
    asyncio.run(ingestion_run.run())

    delete_resp = client.post("/admin/graph/delete-edge", json={
        "edge_id": "edge:pancreas_secretes_insulin", "reason": "test soft delete",
    })
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deprecated"

    neighbors_resp = client.get("/neighbors/structure:pancreas")
    edges = {(e["source"], e["relation"], e["target"]) for e in neighbors_resp.json()["edges"]}
    assert ("structure:pancreas", "SECRETES", "hormone:insulin") not in edges

    with neo4j_driver.session() as session:
        record = session.run(
            "MATCH ()-[r {id: $id}]->() RETURN r.status AS status LIMIT 1", id="edge:pancreas_secretes_insulin"
        ).single()
    assert record["status"] == "deprecated"

    log = asyncio.run(_fetch_change_log("edge:pancreas_secretes_insulin"))
    assert log is not None
    assert log["action"] == "delete"


def test_merge_nodes_redirects_relationships_and_marks_merged(client, neo4j_driver):
    asyncio.run(ingestion_run.run())

    duplicate_id = "hormone:test_curation_duplicate_adh"
    with neo4j_driver.session() as session:
        session.run(
            """
            MERGE (n:Hormone {id: $id})
            SET n.label = 'Duplicate ADH', n.status = 'approved', n.description = 'test duplicate'
            """,
            id=duplicate_id,
        )
        session.run(
            """
            MATCH (a:Hormone {id: $id}), (b:Receptor {id: 'receptor:adh_receptor'})
            MERGE (a)-[r:BINDS_TO {id: 'edge:test_duplicate_binds_to'}]->(b)
            SET r.status = 'approved'
            """,
            id=duplicate_id,
        )

    merge_resp = client.post("/admin/graph/merge-nodes", json={
        "source_node_id": duplicate_id, "target_node_id": "hormone:adh", "reason": "duplicate of ADH",
    })
    assert merge_resp.status_code == 200
    assert merge_resp.json()["status"] == "merged"

    with neo4j_driver.session() as session:
        source_record = session.run(
            "MATCH (n {id: $id}) RETURN n.status AS status, n.merged_into AS merged_into", id=duplicate_id
        ).single()
        redirected = session.run(
            "MATCH (a {id: 'hormone:adh'})-[r:BINDS_TO {id: 'edge:test_duplicate_binds_to'}]->(b) RETURN b.id AS id"
        ).single()

    assert source_record["status"] == "merged"
    assert source_record["merged_into"] == "hormone:adh"
    assert redirected is not None
    assert redirected["id"] == "receptor:adh_receptor"

    log = asyncio.run(_fetch_change_log(duplicate_id))
    assert log is not None
    assert log["action"] == "merge"

    _cleanup_node(neo4j_driver, duplicate_id)
