from neo4j import Driver


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
