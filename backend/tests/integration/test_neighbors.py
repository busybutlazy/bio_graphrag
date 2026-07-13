import pytest
from app.core.config import settings
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
