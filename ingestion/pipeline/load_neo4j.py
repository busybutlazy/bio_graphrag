import re

from neo4j import Driver

# Neo4j labels and relationship types are identifiers that can't be parameterised,
# so we interpolate them into Cypher. Guard the interpolation: a type must be a
# plain identifier. Callers should also whitelist the value (see
# normalize_concepts), but this keeps the raw string out of the query text no
# matter which path reaches here.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_type(type_name: str) -> str:
    if not isinstance(type_name, str) or not _IDENTIFIER.match(type_name):
        raise ValueError(f"unsafe graph type: {type_name!r}")
    return type_name


def clear_graph(driver: Driver) -> None:
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def write_nodes(driver: Driver, nodes: list[dict]) -> None:
    with driver.session() as session:
        for node in nodes:
            session.run(
                f"""
                MERGE (n:{_safe_type(node["type"])} {{id: $id}})
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


def write_edges(driver: Driver, edges: list[dict]) -> None:
    with driver.session() as session:
        for edge in edges:
            props = {**edge.get("properties", {}), "status": edge["status"]}
            session.run(
                f"""
                MATCH (a {{id: $source}}), (b {{id: $target}})
                MERGE (a)-[r:{_safe_type(edge["type"])} {{id: $id}}]->(b)
                SET r += $props
                """,
                source=edge["source"],
                target=edge["target"],
                id=edge["id"],
                props=props,
            )


def load(
    driver: Driver, nodes: list[dict], edges: list[dict], clear: bool = True
) -> tuple[int, int]:
    if clear:
        clear_graph(driver)
    write_nodes(driver, nodes)
    write_edges(driver, edges)
    return len(nodes), len(edges)
