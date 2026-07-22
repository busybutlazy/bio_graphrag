"""Gold regression: 通過專家審查的案例固化成最小結構斷言 + renderer 回歸基準。

MVP 先打 cases.json 裡的固定 proposal;未來換真 pipeline 時,gold 從「打固定
proposal」切成「打真實抽取輸出」,本斷言即成為改 prompt/schema/pipeline 的回歸網。
對應 docs/expert-in-the-loop-plan.md 五.5。
"""

import json
from pathlib import Path

import pytest
from app.graph.back_translation import build_context, render_understanding

_DIRECTION_EDGE = {"increase": "INCREASES", "decrease": "DECREASES"}


def _find(rel: str) -> Path:
    for parent in Path(__file__).resolve().parents:
        cand = parent / rel
        if cand.exists():
            return cand
    raise FileNotFoundError(rel)


CASES = json.loads(_find("data/sample/expert_demo/cases.json").read_text(encoding="utf-8"))
CTX = build_context(CASES)
GOLD_DIR = _find("data/sample/expert_demo/gold")
GOLD = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GOLD_DIR.glob("*.json"))]


def _case(cid: str) -> dict:
    return next(c for c in CASES if c["id"] == cid)


def test_every_case_has_a_gold_file():
    assert {g["gold_id"] for g in GOLD} == {c["id"] for c in CASES}


@pytest.mark.parametrize("gold", GOLD, ids=[g["gold_id"] for g in GOLD])
def test_gold_min_assertions(gold):
    proposal = _case(gold["gold_id"])["proposal"]
    rendered = render_understanding(proposal, CTX)

    # renderer 回歸基準:白話句必須逐字符合
    assert rendered["text"] == gold["expected_understanding"]
    assert rendered["is_gap"] is gold["is_gap"]

    node_types = {n["type"] for n in proposal.get("proposed_nodes", [])}
    edge_types = {e["type"] for e in proposal.get("proposed_edges", [])}
    ma = gold["min_assertions"]
    assert set(ma["has_node_types"]) <= node_types
    assert set(ma["has_edge_types"]) <= edge_types

    if ma["direction"]:
        assert _DIRECTION_EDGE[ma["direction"]] in edge_types
