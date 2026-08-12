"""Derive the API-facing strict schema from the internal extraction schema.

``schema/extraction_output_schema.json`` stays the single source of truth: it is what
``validate_extraction_output`` enforces, and — through ``engineer_gate`` — what a hand-made
proposal is judged against. Structured Outputs needs a *different* shape of the same rules, so
this module derives it at request time rather than forking the file (plan D2). Nothing here may
mutate the loaded schema; ``validate_extraction`` caches it at module level.

Two deviations from a naive conversion, both established by the Task 1 probe against
``gpt-4o-mini`` (see ``changes/structured-outputs-extraction/TASK_LOG.md``):

1. ``pattern`` is **dropped**, though strict mode accepts it. Constrained decoding walks the
   regex's character class and will not come out: the probe's one request produced a node id of
   runaway ``[a-z_]`` text and burned 16795 tokens against 588 for the same request without it.
   Id shape is still enforced, twice, where it costs nothing — the internal schema and
   ``engineer_gate._ID_RE``.
2. The free-form ``properties`` object is **enumerated**. Strict mode rejects an object whose
   keys are not declared ("'additionalProperties' is required to be supplied and to be false"),
   so the keys the gate and the lens actually read have to be spelled out. Adding a new node
   property therefore means adding it here too, or the model cannot emit it —
   ``test_strict_schema.py`` fails the build if the two drift apart.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from ingestion.pipeline.validate_extraction import SCHEMA_PATH

# Property keys read by app.graph.engineer_gate and app.graph.back_translation. A guard test
# scans both modules and fails if either reads a key that is missing here.
NODE_PROPERTY_KEYS = ("interaction_type", "feedback_type", "regulated_variable")
EDGE_PROPERTY_KEYS = ("trigger_direction",)

# Dropped for cost, not for support — see the module docstring.
_DROPPED_KEYWORDS = ("pattern", "description")


def _enumerated_properties(keys: tuple[str, ...]) -> dict[str, Any]:
    """A declared, closed object standing in for the free-form ``properties`` bag."""
    return {
        "type": ["object", "null"],
        "properties": {key: {"type": ["string", "null"]} for key in keys},
        "required": list(keys),
        "additionalProperties": False,
    }


def _strictify(node: Any, property_keys: tuple[str, ...]) -> Any:
    if not isinstance(node, dict):
        return node

    node = {k: v for k, v in node.items() if k not in _DROPPED_KEYWORDS}
    original_required = list(node.get("required", []))

    if node.get("type") == "object" and isinstance(node.get("properties"), dict):
        converted: dict[str, Any] = {}
        for key, sub in node["properties"].items():
            if key == "properties":
                converted[key] = _enumerated_properties(property_keys)
                continue
            sub = _strictify(sub, property_keys)
            # strict requires every declared property in `required`; an optional field keeps its
            # optionality by admitting null instead of by being absent.
            if key not in original_required and isinstance(sub.get("type"), str):
                sub["type"] = [sub["type"], "null"]
            converted[key] = sub
        node["properties"] = converted
        node["required"] = list(converted)
        node["additionalProperties"] = False

    if "items" in node:
        node["items"] = _strictify(node["items"], property_keys)
    return node


def _internal_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _optional_keys(definition: str) -> set[str]:
    node = _internal_schema()["$defs"][definition]
    return set(node["properties"]) - set(node.get("required", []))


def drop_strict_nulls(candidate: dict) -> dict:
    """Undo strict mode's "optional means present-and-nullable" on the way back in.

    Strict mode has no notion of an absent field, so an optional one has to be declared and the
    model answers ``"properties": null`` / ``"possible_duplicate_of": null`` to mean "none". The
    internal schema — deliberately untouched — says those are an object and a string, so every
    node arrived invalid: a real extraction lost all four chunks this way before the translation
    existed. Null is the wire form of absent, so absent is what it becomes here.

    Only *optional* keys are stripped. A null in a required field is a genuinely broken element
    and must stay broken, for salvage to drop and disclose.
    """
    if not isinstance(candidate, dict):
        return candidate
    for collection, definition in (("nodes", "node"), ("edges", "edge")):
        items = candidate.get(collection)
        if not isinstance(items, list):
            continue
        optional = _optional_keys(definition)
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in [k for k, v in item.items() if v is None and k in optional]:
                del item[key]
            props = item.get("properties")
            if isinstance(props, dict):
                # the enumerated bag arrives with every declared key, most of them null
                for key in [k for k, v in props.items() if v is None]:
                    del props[key]
                if not props:
                    del item["properties"]
    return candidate


def build_strict_schema() -> dict:
    """Return the JSON Schema to send as ``response_format.json_schema.schema``."""
    schema = copy.deepcopy(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    schema.pop("$schema", None)
    schema.pop("title", None)

    defs = schema.get("$defs", {})
    # node and edge carry different property bags, so they are converted separately rather than
    # by one blanket walk over $defs.
    for name, keys in (("node", NODE_PROPERTY_KEYS), ("edge", EDGE_PROPERTY_KEYS)):
        if name in defs:
            defs[name] = _strictify(defs[name], keys)
    for name, sub in defs.items():
        if name not in ("node", "edge"):
            defs[name] = _strictify(sub, ())

    schema = _strictify(schema, ())
    schema["$defs"] = defs
    return schema
