"""T1: splitting one chunk's extraction output into one review group per statement.

The property under test is the one that motivated the change: a group must hold exactly one
statement, because the expert lens describes only the first pattern it finds — a group with two
statements shows the reviewer half of what they are approving.
"""

from ingestion.pipeline.group_statements import split_into_statements

CHUNK = "doc:test:chunk:000"


def _n(node_id, node_type, label="l"):
    return {"id": node_id, "type": node_type, "label": label, "description": "d"}


def _e(edge_id, edge_type, source, target):
    return {"id": edge_id, "type": edge_type, "source": source, "target": target}


# 胰島素 ─HAS_EFFECT→ RE1 ─ON_VARIABLE/DECREASES→ 血糖
# 升糖素 ─HAS_EFFECT→ RE2 ─ON_VARIABLE/INCREASES→ 血糖     (血糖 shared by both)
_TWO_STATEMENTS = {
    "nodes": [
        _n("hormone:insulin", "Hormone", "胰島素"),
        _n("hormone:glucagon", "Hormone", "升糖素"),
        _n("regulatory_effect:lower_bg", "RegulatoryEffect", "降血糖"),
        _n("regulatory_effect:raise_bg", "RegulatoryEffect", "升血糖"),
        _n("physiological_variable:bg", "PhysiologicalVariable", "血糖"),
    ],
    "edges": [
        _e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg"),
        _e("e:2", "ON_VARIABLE", "regulatory_effect:lower_bg", "physiological_variable:bg"),
        _e("e:3", "DECREASES", "regulatory_effect:lower_bg", "physiological_variable:bg"),
        _e("e:4", "HAS_EFFECT", "hormone:glucagon", "regulatory_effect:raise_bg"),
        _e("e:5", "ON_VARIABLE", "regulatory_effect:raise_bg", "physiological_variable:bg"),
        _e("e:6", "INCREASES", "regulatory_effect:raise_bg", "physiological_variable:bg"),
    ],
}


def test_two_statements_split_and_share_their_common_variable():
    """The core case. One chunk, two claims, one variable in common."""
    groups = split_into_statements(_TWO_STATEMENTS, CHUNK)

    assert len(groups) == 2, "two anchors must not collapse into one reviewable unit"
    assert [g["group_id"] for g in groups] == [
        f"group:llm:{CHUNK}:regulatory_effect:lower_bg",
        f"group:llm:{CHUNK}:regulatory_effect:raise_bg",
    ]

    lower, raise_ = groups
    assert {n["id"] for n in lower["nodes"]} == {
        "regulatory_effect:lower_bg",
        "hormone:insulin",
        "physiological_variable:bg",
    }
    assert {e["id"] for e in lower["edges"]} == {"e:1", "e:2", "e:3"}
    assert {n["id"] for n in raise_["nodes"]} == {
        "regulatory_effect:raise_bg",
        "hormone:glucagon",
        "physiological_variable:bg",
    }
    assert {e["id"] for e in raise_["edges"]} == {"e:4", "e:5", "e:6"}

    # the shared variable belongs to BOTH statements; the review unit is the claim, not the concept
    assert all("physiological_variable:bg" in {n["id"] for n in g["nodes"]} for g in groups)
    # no residual group: every element was claimed by an anchor
    assert not any(g["group_id"].endswith(":residual") for g in groups)


def test_no_anchor_yields_a_single_residual_group():
    """A misconception / part-of chunk has no pattern anchor but is still worth reviewing."""
    candidate = {
        "nodes": [
            _n("misconception:insulin_raises", "Misconception", "誤以為胰島素升血糖"),
            _n("hormone:insulin", "Hormone", "胰島素"),
        ],
        "edges": [
            _e("e:m", "COMMONLY_CONFUSED_WITH", "misconception:insulin_raises", "hormone:insulin")
        ],
    }
    groups = split_into_statements(candidate, CHUNK)

    assert len(groups) == 1
    assert groups[0]["group_id"] == f"group:llm:{CHUNK}:residual"
    assert len(groups[0]["nodes"]) == 2
    assert len(groups[0]["edges"]) == 1


def test_mixed_chunk_splits_into_pattern_group_plus_residual():
    candidate = {
        "nodes": [
            _n("hormone:insulin", "Hormone"),
            _n("regulatory_effect:lower_bg", "RegulatoryEffect"),
            _n("physiological_variable:bg", "PhysiologicalVariable"),
            _n("structure:pancreas", "Structure"),
            _n("system:endocrine", "System"),
        ],
        "edges": [
            _e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg"),
            _e("e:2", "ON_VARIABLE", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            _e("e:3", "DECREASES", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            # unrelated to the effect: pancreas is part of the endocrine system
            _e("e:4", "PART_OF", "structure:pancreas", "system:endocrine"),
        ],
    }
    groups = split_into_statements(candidate, CHUNK)

    assert len(groups) == 2
    assert groups[-1]["group_id"] == f"group:llm:{CHUNK}:residual"
    assert {n["id"] for n in groups[-1]["nodes"]} == {"structure:pancreas", "system:endocrine"}
    assert {e["id"] for e in groups[-1]["edges"]} == {"e:4"}


def test_incomplete_pattern_still_forms_its_own_group():
    """Splitting is not validation. An anchor missing ON_VARIABLE/direction still gets its own
    group so the Schema gate can answer fail_pattern and the reviewer can turn it away — dropping
    it here would hide a defective proposal instead of surfacing it."""
    candidate = {
        "nodes": [
            _n("hormone:insulin", "Hormone"),
            _n("regulatory_effect:lower_bg", "RegulatoryEffect"),
        ],
        "edges": [_e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg")],
    }
    groups = split_into_statements(candidate, CHUNK)

    assert len(groups) == 1
    assert groups[0]["group_id"] == f"group:llm:{CHUNK}:regulatory_effect:lower_bg"
    assert {n["id"] for n in groups[0]["nodes"]} == {
        "regulatory_effect:lower_bg",
        "hormone:insulin",
    }


def test_empty_output_yields_no_groups():
    assert split_into_statements({"nodes": [], "edges": []}, CHUNK) == []
    assert split_into_statements({}, CHUNK) == []


def test_group_ids_are_deterministic_across_calls():
    """Staging scopes item_id by group_id, so a non-deterministic group id would duplicate the
    entire review queue on a re-ingest of the same chapter."""
    first = split_into_statements(_TWO_STATEMENTS, CHUNK)
    second = split_into_statements(_TWO_STATEMENTS, CHUNK)
    assert [g["group_id"] for g in first] == [g["group_id"] for g in second]
    # and the chunk id is what scopes them — a different chunk yields different groups
    other = split_into_statements(_TWO_STATEMENTS, "doc:test:chunk:001")
    assert {g["group_id"] for g in first}.isdisjoint({g["group_id"] for g in other})
