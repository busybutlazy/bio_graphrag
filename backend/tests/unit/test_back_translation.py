import json
from pathlib import Path

from app.graph.back_translation import build_context, render_understanding


def _find(rel: str) -> Path:
    for parent in Path(__file__).resolve().parents:
        cand = parent / rel
        if cand.exists():
            return cand
    raise FileNotFoundError(rel)


CASES = json.loads(_find("data/sample/expert_demo/cases.json").read_text(encoding="utf-8"))
CTX = build_context(CASES)


def _case(cid: str) -> dict:
    return next(c for c in CASES if c["id"] == cid)


def _render(cid: str) -> dict:
    return render_understanding(_case(cid)["proposal"], CTX)


def test_case1_single_regulatory_effect():
    r = _render("blood_glucose_case_001")
    assert r["pattern"] == "P1" and r["is_gap"] is False
    assert r["text"] == "胰島素會造成一個調控效果:使血糖下降。"


def test_case2_regulatory_effect_with_mechanism():
    r = _render("blood_glucose_case_002")
    assert r["pattern"] == "P3" and r["is_gap"] is False
    assert "肝醣分解" in r["text"] and "上升" in r["text"]


def test_case3_secretion_trigger():
    r = _render("blood_glucose_case_003")
    assert r["pattern"] == "P2" and r["is_gap"] is False
    assert r["text"].startswith("當血糖升高時,")
    assert "分泌胰島素" in r["text"]


def test_case4_antagonistic_interaction():
    r = _render("blood_glucose_case_004")
    assert r["pattern"] == "P4" and r["is_gap"] is False
    assert "胰島素" in r["text"] and "升糖素" in r["text"]
    assert "拮抗" in r["text"] and "血糖" in r["text"]


def test_case5_schema_gap():
    r = _render("blood_glucose_case_005")
    assert r["pattern"] == "P5" and r["is_gap"] is True


def test_render_without_context_is_still_deterministic():
    # gate 只需 is_gap,不供 ctx;label 退回 humanized id 也不應報錯
    r = render_understanding(_case("blood_glucose_case_001")["proposal"])
    assert r["pattern"] == "P1" and r["is_gap"] is False


# --- D5: third outcome — flagged gap vs schema-valid-but-no-pattern ----------------------


def test_d5_flagged_no_pattern_is_a_gap():
    proposal = {
        "proposed_nodes": [
            {"id": "hormone:x", "type": "Hormone", "label": "X", "description": "d"},
            {"id": "hormone:y", "type": "Hormone", "label": "Y", "description": "d"},
        ],
        "proposed_edges": [],
        "possible_schema_gap": True,
    }
    r = render_understanding(proposal)
    assert r["pattern"] == "P5" and r["is_gap"] is True


def test_d5_unflagged_no_pattern_is_a_plain_summary_not_a_gap():
    # schema-valid content that matches no regulatory pattern and is NOT flagged as a gap:
    # a plain, non-gap summary naming the concepts — never "系統無法表達".
    proposal = {
        "proposed_nodes": [
            {"id": "disease:diabetes", "type": "Disease", "label": "糖尿病", "description": "d"},
            {"id": "structure:pancreas", "type": "Structure", "label": "胰臟", "description": "d"},
        ],
        "proposed_edges": [
            {
                "id": "e:x",
                "type": "PART_OF",
                "source": "structure:pancreas",
                "target": "disease:diabetes",
            }
        ],
    }
    r = render_understanding(proposal)
    assert r["pattern"] == "P0" and r["is_gap"] is False
    assert "糖尿病" in r["text"] and "胰臟" in r["text"]
    assert "無法" not in r["text"]  # must not read as a gap
