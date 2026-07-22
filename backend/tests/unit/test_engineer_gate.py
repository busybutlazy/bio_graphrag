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
