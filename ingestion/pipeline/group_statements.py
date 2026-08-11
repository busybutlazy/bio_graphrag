"""Split one chunk's extraction output into reviewable *statements*.

A proposal group is the unit a human approves, so it must be exactly one biological claim. Grouping
any coarser is not cosmetic: ``back_translation.render_understanding`` returns on the **first**
pattern it matches, so a group holding two statements shows the reviewer a sentence about one of
them while the other rides along unseen into the approved graph.

Splitting therefore has to know the same statement shapes the renderer does. An earlier version
keyed only on *node types* (RegulatoryEffect / Interaction), which covered two of the renderer's
four patterns and quietly broke the other two: a secretion statement has no distinctive node type
at all, so it could never form a group, and a mechanism (`CAUSES`) hangs off the hormone rather
than the effect, so it was severed from the statement it belongs to.

The shapes live here as explicit templates because ``ingestion`` must not import ``backend``
(the dependency runs one way). Two behavioural guards in the backend tests keep the two copies
honest: every template must render as its pattern, and a residual group must **never** render a
pattern sentence — which is what catches a renderer pattern that no template covers.

Order of work, mirroring the renderer's own precedence:

1. **templates** — complete statements claim their edges;
2. **anchor fallback** — a RegulatoryEffect / Interaction whose pattern is incomplete still forms
   its own group, so the Schema gate can answer ``fail_pattern`` and the reviewer can turn it away.
   Blending it into the residual bag would hide a defective proposal instead of surfacing it;
3. **residual** — whatever is left, one group per chunk, rendered as a plain summary.
"""

from ingestion.pipeline.normalize_concepts import PATTERN_ANCHOR_TYPES

IN, OUT = "in", "out"

# (focus node type, [(direction relative to focus, relation types, how many)])
# Order mirrors back_translation's return order (P2 → P4 → P1/P3): the renderer answers with the
# first shape it finds, so the splitter must claim them in the same priority or the two disagree.
_TEMPLATES: tuple[tuple[str, str, tuple[tuple[str, frozenset[str], int], ...]], ...] = (
    (
        "P2",
        "Hormone",
        (
            (IN, frozenset({"REGULATES_SECRETION_OF"}), 1),
            (IN, frozenset({"SECRETES"}), 1),
        ),
    ),
    (
        "P4",
        "Interaction",
        (
            (OUT, frozenset({"USES_EFFECT"}), 2),
            (OUT, frozenset({"ON_VARIABLE"}), 1),
        ),
    ),
    (
        "P1",
        "RegulatoryEffect",
        (
            (IN, frozenset({"HAS_EFFECT"}), 1),
            (OUT, frozenset({"ON_VARIABLE"}), 1),
            (OUT, frozenset({"INCREASES", "DECREASES"}), 1),
        ),
    ),
)

# Which end of an edge the Schema gate reads it from. ``_pattern_check`` asks for HAS_EFFECT as an
# *incoming* edge of the RegulatoryEffect but USES_EFFECT as an *outgoing* edge of the Interaction,
# so "the source always owns it" only happened to agree for today's types (review finding M1).
# Ownership belongs to whichever end the pattern rule looks at.
_GATE_ANCHOR_END = {
    "HAS_EFFECT": "target",
    "ON_VARIABLE": "source",
    "INCREASES": "source",
    "DECREASES": "source",
    "USES_EFFECT": "source",
}


def _residual_group_id(chunk_id: str) -> str:
    return f"group:llm:{chunk_id}:residual"


def anchor_group_id(chunk_id: str, focus_id: str) -> str:
    """Group ids are derived, never random.

    Staging scopes ``item_id`` by ``group_id``, so a random id would give every re-run fresh
    item_ids, defeating ``ON CONFLICT DO NOTHING`` and duplicating the whole review queue on a
    second ingest of the same chapter. Deriving the id from chunk + focus keeps re-runs idempotent.

    Note the id contains colons from ``chunk_id`` itself — compare group ids whole, never split
    them on ``:`` (review finding S2).
    """
    return f"group:llm:{chunk_id}:{focus_id}"


def _match_template(
    focus_id: str,
    requirements: tuple[tuple[str, frozenset[str], int], ...],
    available: list[dict],
) -> list[dict] | None:
    """Edges satisfying every requirement around ``focus_id``, or ``None`` if the shape is absent."""
    picked: list[dict] = []
    for direction, relations, needed in requirements:
        end = "target" if direction == IN else "source"
        found = sorted(
            (e for e in available if e.get(end) == focus_id and e.get("type") in relations),
            key=lambda e: str(e["id"]),
        )
        if len(found) < needed:
            return None
        # Exactly what the renderer will read, never more. The renderer describes `edges[0]` of each
        # role, so sweeping surplus edges of the same role into the group would put a second claim
        # (a second hormone acting on the same effect) beside a sentence that only mentions the
        # first — the reviewer would approve something the lens never showed them. The surplus falls
        # through to the residual group, where a plain summary names it honestly.
        picked.extend(found[:needed])
    # dedupe while keeping order: one edge can satisfy two requirements only if relations overlap
    seen: set[str] = set()
    deduped: list[dict] = []
    for edge in picked:
        if edge["id"] not in seen:
            seen.add(edge["id"])
            deduped.append(edge)
    return deduped


def _owner_end(edge: dict, anchor_ids: set[str]) -> str | None:
    """Which anchor owns this edge in the fallback pass? ``None`` means residual."""
    source, target = edge.get("source"), edge.get("target")
    ends = {"source": source, "target": target}
    preferred = _GATE_ANCHOR_END.get(str(edge.get("type")))
    if preferred and ends[preferred] in anchor_ids:
        return ends[preferred]
    # not a pattern relation, or the end the gate reads is not an anchor here: fall back to
    # whichever end anchors, source first for determinism
    if source in anchor_ids:
        return source
    if target in anchor_ids:
        return target
    return None


def split_into_statements(candidate: dict, chunk_id: str) -> list[dict]:
    """Return ``[{group_id, nodes, edges}, ...]`` for one chunk's ``{nodes, edges}`` output.

    Groups are ordered by focus id with the residual last, so the result is stable across runs. A
    node shared by two statements (a variable both hormones act on) appears in **both** groups — the
    review unit is the statement, not the concept. An anchor is never absorbed into another group as
    a member, only referenced: the claim "these two effects antagonise" presupposes the effects, so
    the effects stay their own statements. ``approve_group`` enforces the ordering that implies.
    """
    nodes = candidate.get("nodes") or []
    edges = candidate.get("edges") or []
    by_id = {n["id"]: n for n in nodes}
    types = {n["id"]: n.get("type") for n in nodes}
    anchor_ids = {nid for nid, t in types.items() if t in PATTERN_ANCHOR_TYPES}

    claimed_edges: set[str] = set()
    groups_by_focus: dict[str, dict] = {}

    def _remaining() -> list[dict]:
        return [e for e in edges if e["id"] not in claimed_edges]

    def _members(focus_id: str, own_edges: list[dict]) -> list[dict]:
        """Focus first, then its non-anchor neighbours in edge order — reads like the statement."""
        member_ids = [focus_id]
        for edge in own_edges:
            for endpoint in (str(edge.get("source")), str(edge.get("target"))):
                if endpoint in anchor_ids or endpoint not in by_id:
                    continue  # another anchor is referenced, never absorbed; unknown ids external
                if endpoint not in member_ids:
                    member_ids.append(endpoint)
        return [by_id[i] for i in member_ids]

    # ---- 1. complete statements, in the renderer's own precedence -------------------
    for _pattern, focus_type, requirements in _TEMPLATES:
        for focus_id in sorted(nid for nid, t in types.items() if t == focus_type):
            if focus_id in groups_by_focus:
                continue
            matched = _match_template(focus_id, requirements, _remaining())
            if matched is None:
                continue
            claimed_edges.update(e["id"] for e in matched)
            groups_by_focus[focus_id] = {
                "group_id": anchor_group_id(chunk_id, focus_id),
                "nodes": _members(focus_id, matched),
                "edges": matched,
            }

    # ---- 2. anchors whose pattern is incomplete still stand alone -------------------
    unmatched_anchors = sorted(anchor_ids - set(groups_by_focus))
    for focus_id in unmatched_anchors:
        own = [e for e in _remaining() if _owner_end(e, set(unmatched_anchors)) == focus_id]
        claimed_edges.update(e["id"] for e in own)
        groups_by_focus[focus_id] = {
            "group_id": anchor_group_id(chunk_id, focus_id),
            "nodes": _members(focus_id, own),
            "edges": own,
        }

    groups = [groups_by_focus[k] for k in sorted(groups_by_focus)]

    # ---- 3. residual: leftovers, carrying their endpoints so no edge dangles --------
    residual_edges = _remaining()
    claimed_nodes = {n["id"] for g in groups for n in g["nodes"]}
    residual_ids: list[str] = []
    for edge in residual_edges:
        # an endpoint already claimed elsewhere is pulled in as well (review finding B1): leaving it
        # out produced a group whose edges pointed at nothing, which approve_group refuses — and if
        # the group that owned the node was rejected, that refusal had no way out.
        for endpoint in (str(edge.get("source")), str(edge.get("target"))):
            if endpoint in by_id and endpoint not in residual_ids:
                residual_ids.append(endpoint)
    for node in nodes:
        if node["id"] not in claimed_nodes and node["id"] not in residual_ids:
            residual_ids.append(node["id"])
    if residual_ids or residual_edges:
        groups.append(
            {
                "group_id": _residual_group_id(chunk_id),
                "nodes": [by_id[i] for i in residual_ids],
                "edges": residual_edges,
            }
        )
    return groups
