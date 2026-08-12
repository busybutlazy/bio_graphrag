"""The API-facing strict schema, and the two rules the Task 1 probe established.

Structural assertions here are what the probe verified against gpt-4o-mini; they are cheap to
keep true and expensive to rediscover (a rejected schema fails a paid extraction, and one
accepted-but-wrong shape burned 16795 tokens on a single request).
"""

import json

from ingestion.extract import llm_client, strict_schema
from ingestion.pipeline import validate_extraction
from ingestion.pipeline.validate_extraction import SCHEMA_PATH

# The drift guard pairing these keys with what the gate and the lens actually read lives in
# backend/tests/unit/test_property_key_coverage.py — it needs to import backend, and the
# dependency only runs that way.


def _objects(node, seen=None):
    """Every object-typed subschema, so the strict rules can be asserted on all of them."""
    seen = seen if seen is not None else []
    if isinstance(node, dict):
        if node.get("type") == "object" or (
            isinstance(node.get("type"), list) and "object" in node["type"]
        ):
            seen.append(node)
        for value in node.values():
            _objects(value, seen)
    elif isinstance(node, list):
        for value in node:
            _objects(value, seen)
    return seen


def test_every_object_declares_all_properties_and_closes_the_door():
    schema = strict_schema.build_strict_schema()
    for obj in _objects(schema):
        props = obj.get("properties")
        if props is None:
            continue
        assert obj.get("additionalProperties") is False, obj
        assert sorted(obj.get("required", [])) == sorted(props), (
            f"strict 要求每個宣告的屬性都列入 required:{obj}"
        )


def test_pattern_is_dropped():
    """Accepted by strict mode, but constrained decoding walks the character class and does not
    come out — 16795 tokens against 588 for the same request (TASK_LOG Task 1)."""
    assert "pattern" not in json.dumps(strict_schema.build_strict_schema())


def test_node_and_edge_property_bags_are_enumerated():
    """Strict mode rejects a free-form object outright, so the keys must be spelled out."""
    defs = strict_schema.build_strict_schema()["$defs"]
    node_bag = defs["node"]["properties"]["properties"]
    edge_bag = defs["edge"]["properties"]["properties"]
    assert sorted(node_bag["properties"]) == sorted(strict_schema.NODE_PROPERTY_KEYS)
    assert sorted(edge_bag["properties"]) == sorted(strict_schema.EDGE_PROPERTY_KEYS)
    assert node_bag["additionalProperties"] is False


def test_optional_fields_become_nullable_rather_than_absent():
    node = strict_schema.build_strict_schema()["$defs"]["node"]
    internal = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["node"]
    for key in node["properties"]:
        if key in internal["required"]:
            continue
        declared = node["properties"][key]["type"]
        assert "null" in declared, f"{key} 在內部 schema 是選用的,strict 版必須允許 null"


def test_building_does_not_mutate_the_internal_schema():
    """``validate_extraction`` caches the loaded schema at module level; mutating it here would
    change what every proposal — including hand-made ones via engineer_gate — is judged against."""
    before = json.dumps(validate_extraction._schema, sort_keys=True)
    strict_schema.build_strict_schema()
    assert json.dumps(validate_extraction._schema, sort_keys=True) == before
    # and the internal schema still enforces the id convention the strict one gives up
    assert "pattern" in json.dumps(validate_extraction._schema)


def test_response_format_is_strict_json_schema():
    fmt = llm_client.response_format()
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["$defs"]["node"]["additionalProperties"] is False


class _Refused:
    refusal = "I cannot help with that."
    content = None


class _Answered:
    refusal = None
    content = '{"nodes": [], "edges": []}'


def test_refusal_raises_instead_of_becoming_an_empty_extraction():
    """Reading content blindly would turn a refusal into a silently empty chunk."""
    try:
        llm_client.content_of(_Refused())
    except llm_client.LLMRefused as exc:
        assert "cannot help" in str(exc)
    else:
        raise AssertionError("refusal 必須拋出,不能被當成空抽取")

    assert llm_client.content_of(_Answered()) == '{"nodes": [], "edges": []}'


# --- strict mode's nulls, on the way back in ----------------------------------------------
# Shaped after what the API actually returned, not after hand-written fixtures: every test above
# used clean candidates, so none of them could catch this. A real extraction lost all four of its
# chunks to it.

CHUNK = "doc:x:chunk:000"


def _strict_node(**overrides):
    node = {
        "id": "hormone:insulin",
        "type": "Hormone",
        "label": "胰島素",
        "description": "d",
        "properties": None,
        "source_chunk_id": CHUNK,
        "possible_duplicate_of": None,
    }
    node.update(overrides)
    return node


def test_null_optionals_become_absent_and_the_node_validates():
    candidate = {"nodes": [_strict_node()], "edges": []}
    strict_schema.drop_strict_nulls(candidate)

    node = candidate["nodes"][0]
    assert "properties" not in node
    assert "possible_duplicate_of" not in node
    validate_extraction.validate_extraction_output(candidate)  # would raise before the fix


def test_a_bag_of_nulls_is_dropped_but_a_real_value_survives():
    """Strict mode makes the model send every declared property key, most of them null."""
    candidate = {
        "nodes": [
            _strict_node(
                id="interaction:a",
                type="Interaction",
                properties={
                    "interaction_type": "antagonism",
                    "feedback_type": None,
                    "regulated_variable": None,
                },
            ),
            _strict_node(id="hormone:b", properties={"interaction_type": None}),
        ],
        "edges": [],
    }
    strict_schema.drop_strict_nulls(candidate)

    assert candidate["nodes"][0]["properties"] == {"interaction_type": "antagonism"}
    assert "properties" not in candidate["nodes"][1], "全為 null 的屬性袋應整個消失,不留空 dict"
    validate_extraction.validate_extraction_output(candidate)


def test_a_null_in_a_required_field_stays_broken():
    """Salvage must still drop and disclose it — silently deleting the key would turn a broken
    element into one that merely looks incomplete."""
    candidate = {"nodes": [_strict_node(label=None)], "edges": []}
    strict_schema.drop_strict_nulls(candidate)

    assert "label" in candidate["nodes"][0]
    assert candidate["nodes"][0]["label"] is None


def test_edge_properties_are_normalised_too():
    candidate = {
        "nodes": [],
        "edges": [
            {
                "id": "e1",
                "type": "REGULATES_SECRETION_OF",
                "source": "physiological_variable:bg",
                "target": "hormone:insulin",
                "properties": {"trigger_direction": None},
                "source_chunk_id": CHUNK,
            }
        ],
    }
    strict_schema.drop_strict_nulls(candidate)
    assert "properties" not in candidate["edges"][0]
    validate_extraction.validate_extraction_output(candidate)
