from neo4j import Driver

# Node properties that are structural/reserved and not surfaced as domain
# properties in NodeDetailResponse.properties.
_RESERVED_NODE_KEYS = {"id", "label", "status", "description", "merged_into"}

# Expansion query shared by fetch_neighbors and expand_from_seeds: one hop out
# from an approved frontier, only traversing approved nodes/edges.
_EXPAND_QUERY = """
MATCH (a)-[r]-(b)
WHERE a.id IN $frontier AND a.status = 'approved'
  AND b.status = 'approved' AND r.status = 'approved'
RETURN DISTINCT startNode(r).id AS source, type(r) AS relation,
       endNode(r).id AS target, b.id AS neighbor_id,
       b.label AS neighbor_label, labels(b)[0] AS neighbor_type
"""


def fetch_node_detail(driver: Driver, node_id: str) -> dict | None:
    """Return an approved node's detail, or None if missing/not approved."""
    with driver.session() as session:
        record = session.run(
            "MATCH (n {id: $id}) WHERE n.status = 'approved' "
            "RETURN n.id AS id, labels(n)[0] AS type, n.label AS label, "
            "n.description AS description, properties(n) AS props",
            id=node_id,
        ).single()
    if record is None:
        return None
    props = {k: v for k, v in record["props"].items() if k not in _RESERVED_NODE_KEYS}
    return {
        "id": record["id"],
        "type": record["type"],
        "label": record["label"],
        "description": record["description"],
        "properties": props,
    }


def fetch_nodes_brief(driver: Driver, node_ids: list[str]) -> list[dict]:
    """Return {id,label,type} for the approved nodes among node_ids."""
    if not node_ids:
        return []
    with driver.session() as session:
        rows = session.run(
            "MATCH (n) WHERE n.id IN $ids AND n.status = 'approved' "
            "RETURN n.id AS id, n.label AS label, labels(n)[0] AS type "
            "ORDER BY labels(n)[0], n.label",
            ids=node_ids,
        ).data()
    return rows


def graph_counts(driver: Driver) -> dict:
    """Count approved nodes and edges (for the Library summary)."""
    with driver.session() as session:
        nodes = session.run(
            "MATCH (n) WHERE n.status = 'approved' RETURN count(n) AS c"
        ).single()["c"]
        edges = session.run(
            "MATCH ()-[r]->() WHERE r.status = 'approved' RETURN count(r) AS c"
        ).single()["c"]
    return {"nodes": nodes, "edges": edges}


def expand_from_seeds(
    driver: Driver, seed_ids: list[str], depth: int, node_limit: int
) -> dict:
    """BFS an approved subgraph starting from seed nodes.

    Seeds that are missing or not approved are silently dropped. Returns
    {"nodes": [...], "edges": [...]} where nodes include the surviving seeds.
    """
    with driver.session() as session:
        rows = session.run(
            "MATCH (n) WHERE n.id IN $ids AND n.status = 'approved' "
            "RETURN n.id AS id, n.label AS label, labels(n)[0] AS type",
            ids=list(seed_ids),
        ).data()
        nodes: dict[str, dict] = {
            r["id"]: {"id": r["id"], "label": r["label"], "type": r["type"]} for r in rows
        }
        visited = set(nodes)
        frontier = set(nodes)
        edges: dict[tuple, dict] = {}

        for _ in range(depth):
            if not frontier or len(nodes) >= node_limit:
                break
            result = session.run(_EXPAND_QUERY, frontier=list(frontier))
            next_frontier: set[str] = set()
            for record in result:
                edges[(record["source"], record["relation"], record["target"])] = {
                    "source": record["source"],
                    "relation": record["relation"],
                    "target": record["target"],
                }
                neighbor_id = record["neighbor_id"]
                if neighbor_id not in visited and len(nodes) < node_limit:
                    nodes[neighbor_id] = {
                        "id": neighbor_id,
                        "label": record["neighbor_label"],
                        "type": record["neighbor_type"],
                    }
                    next_frontier.add(neighbor_id)
            visited |= next_frontier
            frontier = next_frontier

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def fetch_neighbors(driver: Driver, node_id: str, depth: int, limit: int) -> dict | None:
    with driver.session() as session:
        center = session.run(
            "MATCH (n {id: $id}) WHERE n.status = 'approved' "
            "RETURN n.id AS id, n.label AS label, labels(n)[0] AS type",
            id=node_id,
        ).single()
        if center is None:
            return None

        visited = {node_id}
        frontier = {node_id}
        neighbors: dict[str, dict] = {}
        edges: dict[tuple, dict] = {}

        for _ in range(depth):
            if not frontier or len(neighbors) >= limit:
                break
            result = session.run(
                """
                MATCH (a)-[r]-(b)
                WHERE a.id IN $frontier AND a.status = 'approved'
                  AND b.status = 'approved' AND r.status = 'approved'
                RETURN DISTINCT startNode(r).id AS source, type(r) AS relation,
                       endNode(r).id AS target, b.id AS neighbor_id,
                       b.label AS neighbor_label, labels(b)[0] AS neighbor_type
                """,
                frontier=list(frontier),
            )
            next_frontier = set()
            for record in result:
                edges[(record["source"], record["relation"], record["target"])] = {
                    "source": record["source"],
                    "relation": record["relation"],
                    "target": record["target"],
                }
                neighbor_id = record["neighbor_id"]
                if neighbor_id not in visited and len(neighbors) < limit:
                    neighbors[neighbor_id] = {
                        "id": neighbor_id,
                        "label": record["neighbor_label"],
                        "type": record["neighbor_type"],
                    }
                    next_frontier.add(neighbor_id)
            visited |= next_frontier
            frontier = next_frontier

        return {
            "center_node": {"id": center["id"], "label": center["label"], "type": center["type"]},
            "nodes": list(neighbors.values()),
            "edges": list(edges.values()),
        }
