import pytest
from app.core.config import settings
from app.graph.cypher_templates import expand_from_seeds
from app.main import app
from fastapi.testclient import TestClient
from neo4j import GraphDatabase


@pytest.fixture
def sample_subgraph():
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    with driver.session() as session:
        session.run(
            """
            MERGE (a:Hormone {id: 'test:hormone_a'})
            SET a.label = 'Test Hormone A', a.status = 'approved', a.description = 'test'
            MERGE (b:PhysiologicalVariable {id: 'test:variable_b'})
            SET b.label = 'Test Variable B', b.status = 'approved', b.description = 'test'
            MERGE (a)-[r:DECREASES {id: 'test:edge_ab'}]->(b)
            SET r.status = 'approved'
            """
        )
    yield
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.id STARTS WITH 'test:' DETACH DELETE n")
    driver.close()


def test_neighbors_returns_local_subgraph(sample_subgraph):
    client = TestClient(app)
    response = client.get("/neighbors/test:hormone_a")
    assert response.status_code == 200

    body = response.json()
    assert body["center_node"]["id"] == "test:hormone_a"
    assert "test:variable_b" in {n["id"] for n in body["nodes"]}
    edges = {(e["source"], e["relation"], e["target"]) for e in body["edges"]}
    assert ("test:hormone_a", "DECREASES", "test:variable_b") in edges


def test_neighbors_returns_404_for_unknown_node():
    client = TestClient(app)
    response = client.get("/neighbors/does-not-exist")
    assert response.status_code == 404


@pytest.fixture
def wide_star_forward():
    """Centre A with 5 approved neighbors, all edges stored A -> Ni.

    Five neighbors exceed a node_limit of 3, so the BFS cap is reached
    mid-expansion — the scenario that used to emit dangling edges.
    """
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    with driver.session() as session:
        session.run(
            """
            MERGE (a:Hormone {id: 'test:star_a'})
            SET a.label = 'Star A', a.status = 'approved', a.description = 'test'
            WITH a
            UNWIND range(1, 5) AS i
            MERGE (n:PhysiologicalVariable {id: 'test:star_n' + toString(i)})
            SET n.label = 'Star N' + toString(i), n.status = 'approved',
                n.description = 'test'
            MERGE (a)-[r:DECREASES {id: 'test:star_e' + toString(i)}]->(n)
            SET r.status = 'approved'
            """
        )
    yield driver
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.id STARTS WITH 'test:' DETACH DELETE n")
    driver.close()


@pytest.fixture
def wide_star_reversed():
    """Centre A with 5 approved neighbors, all edges stored Ni -> A.

    Same cap scenario, but the dangling endpoint would be the edge ``source``
    rather than ``target`` — guards the direction-agnostic gate.
    """
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    with driver.session() as session:
        session.run(
            """
            MERGE (a:Hormone {id: 'test:star_a'})
            SET a.label = 'Star A', a.status = 'approved', a.description = 'test'
            WITH a
            UNWIND range(1, 5) AS i
            MERGE (n:PhysiologicalVariable {id: 'test:star_n' + toString(i)})
            SET n.label = 'Star N' + toString(i), n.status = 'approved',
                n.description = 'test'
            MERGE (n)-[r:INCREASES {id: 'test:star_e' + toString(i)}]->(a)
            SET r.status = 'approved'
            """
        )
    yield driver
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.id STARTS WITH 'test:' DETACH DELETE n")
    driver.close()


def _assert_no_dangling_edges(result):
    node_ids = {n["id"] for n in result["nodes"]}
    assert node_ids  # expansion returned something
    dangling = [
        e
        for e in result["edges"]
        if e["source"] not in node_ids or e["target"] not in node_ids
    ]
    assert dangling == [], f"dangling edges: {dangling}; nodes: {node_ids}"


def test_bfs_never_returns_dangling_edges_when_node_limit_reached(wide_star_forward):
    result = expand_from_seeds(wide_star_forward, ["test:star_a"], depth=2, node_limit=3)
    assert len(result["nodes"]) <= 3  # cap honored
    _assert_no_dangling_edges(result)


def test_bfs_no_dangling_edges_with_reversed_edge_direction(wide_star_reversed):
    result = expand_from_seeds(wide_star_reversed, ["test:star_a"], depth=2, node_limit=3)
    assert len(result["nodes"]) <= 3
    _assert_no_dangling_edges(result)
