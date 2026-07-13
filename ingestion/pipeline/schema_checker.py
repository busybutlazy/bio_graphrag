"""Automated schema checks for proposed curation items.

Runs stateless structural checks on node/edge dicts extracted by the LLM.
Results are stored in curation_items.schema_check so the expert reviewer
can see at a glance whether the item is structurally sound.

Checks deliberately cover what jsonschema validation cannot: id-prefix/type
coherence and description quality. jsonschema still runs first in
validate_extraction — these checks are additive, not a replacement.
"""

from __future__ import annotations

import re

from ingestion.pipeline.normalize_concepts import VALID_NODE_TYPES, VALID_RELATIONSHIP_TYPES

_ID_RE = re.compile(r"^[a-z_]+:[a-z0-9_]+$")

# ponytail-forge: derived from VALID_NODE_TYPES so it can't drift out of sync
# when a type is added/renamed there.
_PREFIX_TO_TYPE: dict[str, str] = {
    re.sub(r"(?<!^)(?=[A-Z])", "_", t).lower(): t for t in VALID_NODE_TYPES
}

_MIN_DESCRIPTION_LEN = 10


def _check(name: str, passed: bool, detail: str | None = None) -> dict:
    entry: dict = {"name": name, "passed": passed}
    if detail:
        entry["detail"] = detail
    return entry


def check_node(node: dict) -> dict:
    """Return schema_check payload for a proposed node."""
    node_id = node.get("id", "")
    node_type = node.get("type", "")
    description = node.get("description", "")

    id_ok = bool(_ID_RE.match(node_id))

    type_ok = node_type in VALID_NODE_TYPES

    desc_ok = len(description.strip()) >= _MIN_DESCRIPTION_LEN

    prefix = node_id.split(":")[0] if ":" in node_id else ""
    expected_type = _PREFIX_TO_TYPE.get(prefix)
    prefix_ok = expected_type == node_type
    prefix_detail = (
        None if prefix_ok
        else f"prefix '{prefix}' expects type '{expected_type}', got '{node_type}'"
    )

    checks = [
        _check("id_format", id_ok),
        _check("type_valid", type_ok),
        _check("description_quality", desc_ok),
        _check("id_prefix_type_match", prefix_ok, prefix_detail),
    ]
    return _result(checks)


def check_edge(edge: dict) -> dict:
    """Return schema_check payload for a proposed edge."""
    edge_type = edge.get("type", "")
    edge_id = edge.get("id", "")

    type_ok = edge_type in VALID_RELATIONSHIP_TYPES
    id_ok = bool(edge_id.strip())

    checks = [
        _check("type_valid", type_ok),
        _check("id_not_empty", id_ok),
    ]
    return _result(checks)


def _result(checks: list[dict]) -> dict:
    return {"passed": all(c["passed"] for c in checks), "checks": checks}
