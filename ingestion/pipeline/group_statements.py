"""Split one chunk's extraction output into reviewable *statements*.

A proposal group is the unit a human approves or turns away, so it must be exactly one biological
claim. Grouping any coarser is not a cosmetic problem: ``back_translation.render_understanding``
describes only the **first** pattern it finds in a proposal, so a group holding two statements shows
the reviewer a sentence about one of them while the other rides along unseen into the approved graph.
That is the failure this module exists to prevent (see changes/extract-per-group-staging/).

The rule needs no pattern-specific edge knowledge: a group is an **anchor** node
(``PATTERN_ANCHOR_TYPES`` — RegulatoryEffect / Interaction), every edge touching it, and the nodes at
the far end of those edges. Anything no anchor claims becomes one residual group per chunk, which the
expert lens renders as a plain summary rather than a pattern sentence.

Deliberately *not* a completeness check. An anchor missing a required edge still forms its own group —
the Schema gate then answers ``fail_pattern`` and the reviewer turns it away. Filtering incomplete
patterns out here would hide them instead.
"""

from ingestion.pipeline.normalize_concepts import PATTERN_ANCHOR_TYPES


def _residual_group_id(chunk_id: str) -> str:
    return f"group:llm:{chunk_id}:residual"


def anchor_group_id(chunk_id: str, anchor_id: str) -> str:
    """Group ids are derived, never random.

    Staging scopes ``item_id`` by ``group_id``, so a random id would give every re-run fresh item_ids,
    defeating ``ON CONFLICT DO NOTHING`` and duplicating the whole review queue on a second ingest of
    the same chapter. Deriving the id from chunk + anchor keeps re-runs idempotent.
    """
    return f"group:llm:{chunk_id}:{anchor_id}"


def split_into_statements(candidate: dict, chunk_id: str) -> list[dict]:
    """Return ``[{group_id, nodes, edges}, ...]`` for one chunk's ``{nodes, edges}`` output.

    Groups are ordered by anchor id, residual last, so the result is stable across runs. A node
    shared by two statements (a variable both hormones act on) appears in **both** groups — the
    review unit is the statement, not the concept.
    """
    nodes = candidate.get("nodes") or []
    edges = candidate.get("edges") or []
    by_id = {n["id"]: n for n in nodes}

    anchors = sorted(n["id"] for n in nodes if n.get("type") in PATTERN_ANCHOR_TYPES)

    groups: list[dict] = []
    claimed_nodes: set[str] = set()
    claimed_edges: set[str] = set()

    for anchor_id in anchors:
        incident = [
            e for e in edges if e.get("source") == anchor_id or e.get("target") == anchor_id
        ]
        # the anchor first, then its neighbours in edge order — reads like the statement itself
        member_ids = [anchor_id]
        for edge in incident:
            for endpoint in (edge.get("source"), edge.get("target")):
                if endpoint != anchor_id and endpoint in by_id and endpoint not in member_ids:
                    member_ids.append(endpoint)

        groups.append(
            {
                "group_id": anchor_group_id(chunk_id, anchor_id),
                "nodes": [by_id[i] for i in member_ids],
                "edges": incident,
            }
        )
        claimed_nodes.update(member_ids)
        claimed_edges.update(e["id"] for e in incident)

    residual_nodes = [n for n in nodes if n["id"] not in claimed_nodes]
    residual_edges = [e for e in edges if e["id"] not in claimed_edges]
    if residual_nodes or residual_edges:
        groups.append(
            {
                "group_id": _residual_group_id(chunk_id),
                "nodes": residual_nodes,
                "edges": residual_edges,
            }
        )
    return groups
