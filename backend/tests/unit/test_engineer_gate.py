import json
from pathlib import Path

from app.graph.engineer_gate import evaluate


def _find(rel: str) -> Path:
    for parent in Path(__file__).resolve().parents:
        cand = parent / rel
        if cand.exists():
            return cand
    raise FileNotFoundError(rel)


CASES = json.loads(_find("data/sample/expert_demo/cases.json").read_text(encoding="utf-8"))


def _case(cid: str) -> dict:
    return next(c for c in CASES if c["id"] == cid)


def test_cases_1_to_4_pass_engineer_gate():
    for cid in (
        "blood_glucose_case_001",
        "blood_glucose_case_002",
        "blood_glucose_case_003",
        "blood_glucose_case_004",
    ):
        assert evaluate(_case(cid)["proposal"])["result"] == "pass", cid


def test_case5_needs_schema_extension():
    r = evaluate(_case("blood_glucose_case_005")["proposal"])
    assert r["result"] == "needs_schema_extension"
    failed_codes = {c["code"] for c in r["checks"] if not c["passed"]}
    assert "needs_schema_extension" in failed_codes
    # gate 只管形式,不擋生物語意:schema/型別/id 這關仍應通過
    passed = {c["name"] for c in r["checks"] if c["passed"]}
    assert {"schema_validation", "node_type_validation", "id_convention_validation"} <= passed


def test_case6_incomplete_pattern_fails():
    # 原文只說「影響」,方向未定 → RE 缺 ON_VARIABLE 與方向邊 → 形式 gate 退回
    assert evaluate(_case("blood_glucose_case_006")["proposal"])["result"] == "fail_pattern"


def test_case7_wrong_biology_still_passes_form_gate():
    # 三段式完整、schema 合法 → 工程師 gate 過;生物學方向錯誤由專家 gate 攔,不在形式檢查範圍
    assert evaluate(_case("blood_glucose_case_007")["proposal"])["result"] == "pass"


def test_d5_unflagged_no_pattern_passes_gate():
    # schema-valid content with no regulatory pattern and no gap flag -> the renderer now
    # returns a plain summary (is_gap False), so back_translation_available passes and the
    # gate result is pass (was needs_schema_extension before D5).
    proposal = {
        "proposed_nodes": [
            {
                "id": "disease:diabetes",
                "type": "Disease",
                "label": "糖尿病",
                "description": "d",
                "source_chunk_id": "chunk:x",
            },
            {
                "id": "structure:pancreas",
                "type": "Structure",
                "label": "胰臟",
                "description": "d",
                "source_chunk_id": "chunk:x",
            },
        ],
        "proposed_edges": [
            {
                "id": "e:x",
                "type": "PART_OF",
                "source": "structure:pancreas",
                "target": "disease:diabetes",
                "source_chunk_id": "chunk:x",
            }
        ],
    }
    assert evaluate(proposal)["result"] == "pass"


def test_d5_flagged_gap_still_needs_schema_extension():
    proposal = {
        "proposed_nodes": [
            {
                "id": "hormone:x",
                "type": "Hormone",
                "label": "X",
                "description": "d",
                "source_chunk_id": "chunk:x",
            }
        ],
        "proposed_edges": [],
        "possible_schema_gap": True,
    }
    assert evaluate(proposal)["result"] == "needs_schema_extension"


def test_incomplete_pattern_is_not_testable():
    # M1 regression: an incomplete pattern must not light testability green while
    # pattern_validation is red (the two would contradict each other in the gate panel).
    proposal = {
        "proposed_nodes": [
            {
                "id": "hormone:x",
                "type": "Hormone",
                "label": "X",
                "description": "d",
                "source_chunk_id": "c",
            },
            {
                "id": "regulatory_effect:x",
                "type": "RegulatoryEffect",
                "label": "RE",
                "description": "d",
                "source_chunk_id": "c",
            },
        ],
        "proposed_edges": [
            {
                "id": "e:x",
                "type": "HAS_EFFECT",
                "source": "hormone:x",
                "target": "regulatory_effect:x",
                "source_chunk_id": "c",
            }
        ],
    }
    r = evaluate(proposal)
    checks = {c["name"]: c["passed"] for c in r["checks"]}
    assert r["result"] == "fail_pattern"
    assert checks["pattern_validation"] is False
    assert checks["testability"] is False  # must agree with pattern_validation


def test_invalid_node_type_fails_schema():
    bad = {
        "proposed_nodes": [
            {
                "id": "foo:bar",
                "type": "NotARealType",
                "label": "x",
                "description": "y",
                "source_chunk_id": "chunk:x",
            }
        ],
        "proposed_edges": [],
    }
    assert evaluate(bad)["result"] == "fail_schema"


def test_bad_node_id_convention_fails_schema():
    bad = {
        "proposed_nodes": [
            {
                "id": "BadID",
                "type": "Hormone",
                "label": "x",
                "description": "y",
                "source_chunk_id": "chunk:x",
            }
        ],
        "proposed_edges": [],
    }
    assert evaluate(bad)["result"] == "fail_schema"


def test_incomplete_regulatory_effect_fails_pattern():
    # RE 少了 ON_VARIABLE 與方向邊 → pattern 不完整(但 schema/型別仍合法)
    proposal = {
        "proposed_nodes": [
            {
                "id": "hormone:x",
                "type": "Hormone",
                "label": "X",
                "description": "d",
                "source_chunk_id": "chunk:x",
            },
            {
                "id": "regulatory_effect:x",
                "type": "RegulatoryEffect",
                "label": "RE",
                "description": "d",
                "source_chunk_id": "chunk:x",
            },
        ],
        "proposed_edges": [
            {
                "id": "e:x",
                "type": "HAS_EFFECT",
                "source": "hormone:x",
                "target": "regulatory_effect:x",
                "source_chunk_id": "chunk:x",
            },
        ],
    }
    assert evaluate(proposal)["result"] == "fail_pattern"


# --- FeedbackLoop (P6) ---------------------------------------------------------------------
# A loop used to be invisible to this gate: not an anchor, no pattern rule, no renderer branch.
# It was folded into whichever statement group owned its neighbours, so approving "insulin lowers
# blood glucose" also wrote a loop nobody had been shown. These pin the shape it must now have.


def _loop_proposal(properties: dict, *, with_edge: bool = True) -> dict:
    nodes = [
        {
            "id": "feedback:x",
            "type": "FeedbackLoop",
            "label": "血糖負回饋",
            "description": "d",
            "properties": properties,
            "source_chunk_id": "chunk:x",
        },
        {
            "id": "regulatory_effect:x",
            "type": "RegulatoryEffect",
            "label": "RE",
            "description": "d",
            "source_chunk_id": "chunk:x",
        },
    ]
    edges = (
        [
            {
                "id": "e:x",
                "type": "USES_EFFECT",
                "source": "feedback:x",
                "target": "regulatory_effect:x",
                "source_chunk_id": "chunk:x",
            }
        ]
        if with_edge
        else []
    )
    # The referenced effect is its own statement elsewhere; here it is only a target, so the loop
    # group carries no HAS_EFFECT/ON_VARIABLE of its own. Drop it from the nodes the gate sees.
    return {"proposed_nodes": nodes[:1], "proposed_edges": edges}


def test_feedback_loop_with_one_effect_and_both_properties_passes():
    """One USES_EFFECT is enough on purpose — three of the four curated loops reference a single
    effect, so requiring two (as Interaction does) would condemn the project's own knowledge."""
    proposal = _loop_proposal({"feedback_type": "negative", "regulated_variable": "blood_glucose"})
    result = evaluate(proposal)
    assert result["result"] == "pass"


def test_feedback_loop_without_uses_effect_fails_pattern():
    proposal = _loop_proposal(
        {"feedback_type": "negative", "regulated_variable": "blood_glucose"}, with_edge=False
    )
    assert evaluate(proposal)["result"] == "fail_pattern"


def test_feedback_loop_without_feedback_type_fails_pattern():
    """Without it the renderer cannot say negative or positive, and the expert would be asked to
    approve a loop whose direction the screen never states."""
    proposal = _loop_proposal({"regulated_variable": "blood_glucose"})
    assert evaluate(proposal)["result"] == "fail_pattern"


def test_feedback_loop_without_regulated_variable_fails_pattern():
    proposal = _loop_proposal({"feedback_type": "negative"})
    assert evaluate(proposal)["result"] == "fail_pattern"


def test_interaction_without_interaction_type_fails_pattern():
    """Same defect as the loop's missing feedback_type: USES_EFFECT×2 and ON_VARIABLE are all
    present, so the shape looks complete, but the P4 renderer needs interaction_type to say whether
    this is antagonism or synergism. Without it the expert reads the "not any known pattern"
    fallback while the gate reports pass."""
    proposal = {
        "proposed_nodes": [
            {
                "id": "interaction:x",
                "type": "Interaction",
                "label": "拮抗",
                "description": "d",
                "source_chunk_id": "chunk:x",
            }
        ],
        "proposed_edges": [
            {
                "id": "e:1",
                "type": "USES_EFFECT",
                "source": "interaction:x",
                "target": "regulatory_effect:a",
                "source_chunk_id": "chunk:x",
            },
            {
                "id": "e:2",
                "type": "USES_EFFECT",
                "source": "interaction:x",
                "target": "regulatory_effect:b",
                "source_chunk_id": "chunk:x",
            },
            {
                "id": "e:3",
                "type": "ON_VARIABLE",
                "source": "interaction:x",
                "target": "physiological_variable:bg",
                "source_chunk_id": "chunk:x",
            },
        ],
    }
    assert evaluate(proposal)["result"] == "fail_pattern"


# --- drift guard: the splitter's anchor set vs the gate's pattern rules --------------------
# `ingestion.pipeline.group_statements` splits an extraction output into one review group per
# statement, using PATTERN_ANCHOR_TYPES to decide what anchors a statement. The gate is the other
# half of the same idea — it special-cases exactly the types a pattern hangs off. If someone teaches
# the gate a third pattern without telling the splitter, that pattern's members would quietly land in
# the residual group instead of forming their own reviewable statement. Backend may import ingestion
# (never the reverse), so the check lives here.


def test_pattern_anchor_types_cover_every_type_the_gate_special_cases():
    from app.graph.engineer_gate import _pattern_check

    from ingestion.pipeline.normalize_concepts import PATTERN_ANCHOR_TYPES, VALID_NODE_TYPES

    # Behavioural probe rather than source parsing: a lone node with no edges can only draw a
    # complaint from _pattern_check if that type is one the gate expects a pattern around.
    gate_anchors = {
        node_type
        for node_type in VALID_NODE_TYPES
        if _pattern_check([{"id": "probe:x", "type": node_type}], []) is not None
    }

    assert gate_anchors == PATTERN_ANCHOR_TYPES, (
        "engineer_gate and group_statements disagree about what anchors a statement; "
        f"gate={sorted(gate_anchors)} splitter={sorted(PATTERN_ANCHOR_TYPES)}"
    )


def test_a_proposal_with_no_nodes_cannot_pass():
    """An empty proposal used to sail through: every other check reads `nodes`, so an empty list
    satisfied them all vacuously, while back_translation could only answer 「本提案沒有可呈現的
    內容」. The gate said pass, the lens said nothing, and the approve button was live — a reviewer
    could commit knowledge the system had just told them it could not show.
    """
    proposal = {
        "proposed_nodes": [],
        "proposed_edges": [
            {
                "id": "e:empty",
                "type": "SECRETED_BY",
                "source": "hormone:insulin",
                "target": "structure:pancreas",
                "source_chunk_id": "c",
            }
        ],
    }
    result = evaluate(proposal)
    assert result["result"] == "fail_schema"
    failed = [c["name"] for c in result["checks"] if not c["passed"]]
    assert "describable" in failed
