"""Keep the valid part of an extraction whose whole-output validation failed.

Before this, one malformed element discarded the chunk it came in. Observed repeatedly on paid
runs: a single edge missing its ``id`` — always a late, semantically marginal one — threw away
two complete and correct regulatory triples alongside it
(``changes/extraction-prompt-inline-pattern-rules/VERIFICATION_REPORT.md``).

Salvage is deliberately narrow. It drops elements, never repairs them: inventing an id or
guessing a relation type would put knowledge in front of an expert that the model never proposed,
which is the one thing this pipeline exists to prevent. What survives still faces both gates, so
an incomplete statement is refused there rather than smuggled through here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jsonschema

from ingestion.pipeline import validate_extraction

# Above this share of dropped elements a chunk is flagged rather than blocked (plan D1b).
# Blocking would restore the whole-chunk loss this module exists to end; staying silent would let
# a model that had systematically degraded still report success.
DEGRADED_DROP_RATIO = 0.5


@dataclass
class Salvaged:
    candidate: dict | None
    dropped: list[dict] = field(default_factory=list)
    degraded: bool = False


def _drop(kind: str, element, reason: str) -> dict:
    element_id = element.get("id") if isinstance(element, dict) else None
    return {"kind": kind, "id": element_id, "reason": reason}


def salvage(raw) -> Salvaged:
    """Return the schema-valid subset of ``raw``, plus what was dropped and why.

    ``candidate`` is ``None`` when nothing survives, so the caller keeps the existing
    "chunk failed" behaviour instead of reporting an empty success.
    """
    if not isinstance(raw, dict):
        return Salvaged(None)
    nodes = raw.get("nodes")
    edges = raw.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return Salvaged(None)

    dropped: list[dict] = []
    kept_nodes: list[dict] = []
    # Ids of nodes that were proposed and then dropped. An endpoint that was never proposed is a
    # different case entirely — extractions are told to reference already-curated concepts rather
    # than re-propose them, so an unknown endpoint is usually correct and must not cascade.
    dropped_node_ids: set[str] = set()

    for node in nodes:
        try:
            validate_extraction.validate_node(node)
            kept_nodes.append(node)
        except jsonschema.ValidationError as exc:
            dropped.append(_drop("node", node, exc.message))
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                dropped_node_ids.add(node["id"])

    kept_edges: list[dict] = []
    for edge in edges:
        try:
            validate_extraction.validate_edge(edge)
        except jsonschema.ValidationError as exc:
            dropped.append(_drop("edge", edge, exc.message))
            continue
        orphaned = [end for end in (edge["source"], edge["target"]) if end in dropped_node_ids]
        if orphaned:
            # Cascade (plan D1a): an edge into a dropped node is the dangling edge that
            # ``approve_group`` already refuses, so the group would arrive unapprovable.
            dropped.append(_drop("edge", edge, f"端點已被丟棄:{', '.join(orphaned)}"))
            continue
        kept_edges.append(edge)

    if not kept_nodes and not kept_edges:
        return Salvaged(None, dropped)

    total = len(nodes) + len(edges)
    degraded = bool(total) and len(dropped) / total > DEGRADED_DROP_RATIO
    return Salvaged({"nodes": kept_nodes, "edges": kept_edges}, dropped, degraded)
