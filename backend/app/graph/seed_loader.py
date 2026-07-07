import json
from pathlib import Path
from typing import Iterable

from neo4j import Driver

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"


def load_sample_data() -> tuple[list[dict], list[dict]]:
    nodes = json.loads((DATA_DIR / "biology_sample_concepts.json").read_text())
    edges = json.loads((DATA_DIR / "biology_sample_edges.json").read_text())
    return nodes, edges


def clear_graph(driver: Driver) -> None:
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def write_nodes(driver: Driver, nodes: Iterable[dict]) -> None:
    with driver.session() as session:
        for node in nodes:
            session.run(
                f"""
                MERGE (n:{node['type']} {{id: $id}})
                SET n.label = $label,
                    n.status = $status,
                    n.description = $description,
                    n += $props
                """,
                id=node["id"],
                label=node["label"],
                status=node["status"],
                description=node["description"],
                props=node.get("properties", {}),
            )


def write_edges(driver: Driver, edges: Iterable[dict]) -> None:
    with driver.session() as session:
        for edge in edges:
            props = {**edge.get("properties", {}), "status": edge["status"]}
            session.run(
                f"""
                MATCH (a {{id: $source}}), (b {{id: $target}})
                MERGE (a)-[r:{edge['type']} {{id: $id}}]->(b)
                SET r += $props
                """,
                source=edge["source"],
                target=edge["target"],
                id=edge["id"],
                props=props,
            )


def seed_sample_graph(driver: Driver) -> tuple[int, int]:
    nodes, edges = load_sample_data()
    clear_graph(driver)
    write_nodes(driver, nodes)
    write_edges(driver, edges)
    return len(nodes), len(edges)
