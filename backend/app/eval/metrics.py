"""Evaluation metrics for the retrieval / grounded-answer pipeline."""


def recall_at_k(expected_ids: list[str], retrieved_ids: list[str]) -> float:
    """Fraction of expected items present in the retrieved list.

    Returns 1.0 when nothing is expected (vacuously satisfied).
    """
    if not expected_ids:
        return 1.0
    retrieved = set(retrieved_ids)
    hit = sum(1 for eid in expected_ids if eid in retrieved)
    return hit / len(expected_ids)


def grounded_pass(expected_node_ids: list[str], supporting_node_ids: list[str]) -> bool:
    """A grounded answer passes when every required supporting node is present."""
    supporting = set(supporting_node_ids)
    return all(nid in supporting for nid in expected_node_ids)


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (p in [0, 100]); 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100) * len(ordered) + 0.5) - 1))
    return ordered[k]
