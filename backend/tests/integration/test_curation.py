import asyncio

import asyncpg
import pytest
from app.core.config import settings
from app.main import app
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from ingestion.pipeline import run as ingestion_run


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def neo4j_driver():
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    yield driver
    driver.close()


def _cleanup_node(driver, node_id: str) -> None:
    with driver.session() as session:
        session.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)


async def _delete_test_curation_items() -> None:
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
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


async def _delete_change_log(target_id: str) -> None:
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    try:
        await conn.execute("DELETE FROM graph_change_logs WHERE target_id = $1", target_id)
    finally:
        await conn.close()


async def _fetch_change_log(target_id: str):
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    try:
        return await conn.fetchrow(
            "SELECT action, actor, reason FROM graph_change_logs WHERE target_id = $1 ORDER BY created_at DESC LIMIT 1",
            target_id,
        )
    finally:
        await conn.close()


# The single-item propose/approve/reject endpoints these tests used to exercise are gone
# (changes/close-approve-item-backdoor): they let a loose element reach Neo4j without passing
# either gate. Two of the three tests were dropped rather than rewritten, because the group path
# already asserts exactly what they asserted:
#   - approve writes to Neo4j + audits  → test_review_groups.py::test_approve_group_writes_all_and_audits
#   - reject writes nothing + audits    → test_review_groups.py::test_reject_group_writes_nothing_and_audits
# Rewriting them here would have been a second copy, not extra coverage. The invariant that is
# genuinely about *this* file — proposed knowledge does not reach the graph until a human
# approves it — is kept below, expressed through the group path that now owns it.


def test_proposed_statement_reaches_the_graph_only_after_approval(client, neo4j_driver):
    """The governance invariant, end to end: propose → invisible → approve → visible."""
    node_id = "hormone:test_curation_pending"
    resp = client.post(
        "/admin/curation/groups",
        json={
            "proposed_nodes": [
                {
                    "id": node_id,
                    "type": "Hormone",
                    "label": "Test Pending Hormone",
                    "description": "test",
                }
            ],
            "proposed_edges": [],
            "reason": "test",
        },
    )
    assert resp.status_code == 201
    group_id = resp.json()["group_id"]

    # staged, but nowhere near the graph
    with neo4j_driver.session() as session:
        assert session.run("MATCH (n {id: $id}) RETURN n", id=node_id).single() is None

    approve = client.post(
        f"/admin/review/groups/{group_id}/approve",
        json={"reviewer": "test_reviewer", "reason": "looks good"},
    )
    assert approve.status_code == 200

    try:
        with neo4j_driver.session() as session:
            record = session.run(
                "MATCH (n {id: $id}) RETURN n.status AS status", id=node_id
            ).single()
        assert record is not None and record["status"] == "approved"
    finally:
        _cleanup_node(neo4j_driver, node_id)
        # The autouse cleanup matches on '%test_curation%', but approve_group audits under
        # target_id=group_id ("group:human:<uuid4>"), which contains no such marker — so without
        # this the audit table grows by one row per test run (review finding L1). Leaving litter
        # in the audit log is a poor look for the one table this project is about.
        asyncio.run(_delete_change_log(group_id))


def test_the_single_item_write_path_is_gone(client):
    """The backdoor itself, asserted as absent.

    `create_item` staged rows with no group_id — invisible to the review queue — and
    `approve_item` wrote them into Neo4j behind nothing but a `status == 'proposed'` check: no
    Schema gate, no back-translation, no deprecated-resurrection or dangling-edge guard. Anyone
    re-adding these routes for convenience has to make this test fail first.

    This asserts on the **route table**, not on a status code. The first version checked
    `status_code in (404, 405)`, which proved nothing for two of the three paths: the removed
    `approve_item`/`reject_item` raised 404 for an unknown item_id, so the assertion held just as
    well in a world where the routes were back (review finding M1). A test that passes whether or
    not the defect is present is worse than no test — it reports a guard that is not there, which
    for a project whose subject *is* governance is exactly the wrong lie to tell.

    The second version listed exact path strings including `{item_id}`, which left the same
    weakness one level down: re-adding the route as `{id}` would have slipped through (L-A). So
    the assertion is a **prefix sweep** — no POST under `/admin/curation/items` at all, whatever
    the handler decides to call its parameter.
    """
    registered = {
        (route.path, method) for route in app.routes for method in getattr(route, "methods", set())
    }

    offenders = {
        (path, method)
        for path, method in registered
        if method == "POST" and path.startswith("/admin/curation/items")
    }
    assert not offenders, f"單項寫入路徑復活:{offenders} → 提案可繞過兩道 gate"

    # Positive control. Without this the sweep above could pass for the wrong reason — a typo in
    # the prefix, or a route table shaped differently than assumed — and report a guard that is
    # not guarding. The read-only listing also survives on purpose: it writes nothing, and it is
    # the only way to see legacy rows that predate grouping.
    assert ("/admin/curation/items", "GET") in registered
    assert client.get("/admin/curation/items").status_code == 200


def test_delete_edge_soft_deletes_and_is_excluded_from_neighbors(client, neo4j_driver):
    asyncio.run(ingestion_run.run())

    delete_resp = client.post(
        "/admin/graph/delete-edge",
        json={
            "edge_id": "edge:pancreas_secretes_insulin",
            "reason": "test soft delete",
        },
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deprecated"

    neighbors_resp = client.get("/neighbors/structure:pancreas")
    edges = {(e["source"], e["relation"], e["target"]) for e in neighbors_resp.json()["edges"]}
    assert ("structure:pancreas", "SECRETES", "hormone:insulin") not in edges

    with neo4j_driver.session() as session:
        record = session.run(
            "MATCH ()-[r {id: $id}]->() RETURN r.status AS status LIMIT 1",
            id="edge:pancreas_secretes_insulin",
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

    merge_resp = client.post(
        "/admin/graph/merge-nodes",
        json={
            "source_node_id": duplicate_id,
            "target_node_id": "hormone:adh",
            "reason": "duplicate of ADH",
        },
    )
    assert merge_resp.status_code == 200
    assert merge_resp.json()["status"] == "merged"

    with neo4j_driver.session() as session:
        source_record = session.run(
            "MATCH (n {id: $id}) RETURN n.status AS status, n.merged_into AS merged_into",
            id=duplicate_id,
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
