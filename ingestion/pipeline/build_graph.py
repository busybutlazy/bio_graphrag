from ingestion.pipeline import normalize_concepts


def build(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    normalize_concepts.validate_nodes(nodes)
    normalize_concepts.validate_edges(nodes, edges)
    return nodes, edges
