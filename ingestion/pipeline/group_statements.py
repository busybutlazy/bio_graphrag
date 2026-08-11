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


def _edge_owner(edge: dict, anchor_ids: set[str]) -> str | None:
    """Which anchor's statement does this edge belong to? ``None`` means residual.

    An edge can touch **two** anchors: a real extraction produced
    ``Interaction ─USES_EFFECT→ RegulatoryEffect``. Letting both claim it would put each anchor
    inside the other's group, so two groups would propose the same node and the second approval
    would collide with the first. The source wins, which matches how the gate reads these edges —
    it checks ``USES_EFFECT`` as an *outgoing* edge of the Interaction, and ``HAS_EFFECT`` as an
    *incoming* edge of the RegulatoryEffect, so in both cases ownership lands where the pattern
    rule looks.
    """
    source, target = edge.get("source"), edge.get("target")
    if source in anchor_ids:
        return source
    if target in anchor_ids:
        return target
    return None


def split_into_statements(candidate: dict, chunk_id: str) -> list[dict]:
    """Return ``[{group_id, nodes, edges}, ...]`` for one chunk's ``{nodes, edges}`` output.

    Groups are ordered by anchor id, residual last, so the result is stable across runs. A node
    shared by two statements (a variable both hormones act on) appears in **both** groups — the
    review unit is the statement, not the concept.

    An anchor is never a *member* of another anchor's group, only referenced by an edge: the claim
    "these two effects antagonise" presupposes the effects, so the effects are their own statements
    and get reviewed on their own terms. The expert lens is built for this — its antagonism rule
    looks the hormone behind each effect up in context rather than requiring the effects in the
    proposal. The cost is an ordering dependency: the interaction cannot be approved until the
    effects it references exist, which ``approve_group`` enforces.
    """
    nodes = candidate.get("nodes") or []
    edges = candidate.get("edges") or []
    by_id = {n["id"]: n for n in nodes}

    anchor_ids = {n["id"] for n in nodes if n.get("type") in PATTERN_ANCHOR_TYPES}

    owned: dict[str, list[dict]] = {anchor_id: [] for anchor_id in anchor_ids}
    residual_edges: list[dict] = []
    for edge in edges:
        owner = _edge_owner(edge, anchor_ids)
        (owned[owner] if owner else residual_edges).append(edge)

    groups: list[dict] = []
    claimed_nodes: set[str] = set(anchor_ids)  # every anchor is claimed by its own group

    for anchor_id in sorted(anchor_ids):
        # the anchor first, then its non-anchor neighbours in edge order — reads like the statement
        member_ids = [anchor_id]
        for edge in owned[anchor_id]:
            for endpoint in (edge.get("source"), edge.get("target")):
                if endpoint in anchor_ids or endpoint not in by_id:
                    continue  # another anchor is referenced, never absorbed; unknown ids are external
                if endpoint not in member_ids:
                    member_ids.append(endpoint)

        groups.append(
            {
                "group_id": anchor_group_id(chunk_id, anchor_id),
                "nodes": [by_id[i] for i in member_ids],
                "edges": owned[anchor_id],
            }
        )
        claimed_nodes.update(member_ids)

    residual_nodes = [n for n in nodes if n["id"] not in claimed_nodes]
    if residual_nodes or residual_edges:
        groups.append(
            {
                "group_id": _residual_group_id(chunk_id),
                "nodes": residual_nodes,
                "edges": residual_edges,
            }
        )
    return groups
