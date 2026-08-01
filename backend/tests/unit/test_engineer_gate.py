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
