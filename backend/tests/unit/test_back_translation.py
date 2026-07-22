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
