import os

from neo4j import GraphDatabase

from app.graph.seed_loader import seed_sample_graph

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "change_me")


def main() -> None:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    try:
        node_count, edge_count = seed_sample_graph(driver)
        print(f"Loaded {node_count} nodes and {edge_count} edges.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
