from neo4j import GraphDatabase

from app.core.config import settings
from app.graph.seed_loader import load_sample_data, seed_sample_graph

MIN_NODES = 30
MIN_EDGES = 50
MIN_NODE_TYPES = 7
MIN_RELATIONSHIP_TYPES = 10


def test_seed_sample_graph_loads_correct_counts():
    nodes, edges = load_sample_data()
    assert len(nodes) >= MIN_NODES
    assert len(edges) >= MIN_EDGES
    assert len({n["type"] for n in nodes}) >= MIN_NODE_TYPES
    assert len({e["type"] for e in edges}) >= MIN_RELATIONSHIP_TYPES

    feedback_types = [n["properties"]["feedback_type"] for n in nodes if n["type"] == "FeedbackLoop"]
    interaction_types = [n["properties"]["interaction_type"] for n in nodes if n["type"] == "Interaction"]
    assert feedback_types.count("negative") >= 3
    assert feedback_types.count("positive") >= 1
    assert interaction_types.count("antagonism") >= 2
    assert interaction_types.count("synergism") >= 1

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        node_count, edge_count = seed_sample_graph(driver)
        assert node_count == len(nodes)
        assert edge_count == len(edges)

        with driver.session() as session:
            db_node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            db_edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        assert db_node_count == len(nodes)
        assert db_edge_count == len(edges)
    finally:
        driver.close()
