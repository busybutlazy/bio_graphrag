"""Read-only expert-in-the-loop demo endpoint.

固定 demo 資料(``data/sample/expert_demo/cases.json``)的唯讀出口。
``system_understanding``(反向翻譯)與 ``engineer_gate``(形式檢查)結果**當場計算、
不落地**,以證明 renderer / gate 是真的在跑,而非預存答案。

此端點:唯讀、**不寫任何 store、不碰 approved 圖、不繞過 curation**;auth 與其他
``/admin/*`` 一致(``require_admin``;未設 key 時為 demo 開放)。
對應 docs/expert-in-the-loop-plan.md 五.4。
"""

import json

from fastapi import APIRouter, Depends

from app.api.auth import require_admin
from app.graph.back_translation import build_context, render_understanding
from app.graph.engineer_gate import evaluate
from ingestion.pipeline.parse_source import DATA_DIR

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

_CASES_PATH = DATA_DIR / "expert_demo" / "cases.json"


def _load_cases() -> list[dict]:
    return json.loads(_CASES_PATH.read_text(encoding="utf-8"))


@router.get("/expert-demo/cases")
async def list_expert_demo_cases() -> list[dict]:
    cases = _load_cases()
    ctx = build_context(cases)  # 跨 case label / effect_to_hormone 索引
    return [
        {
            **case,
            "system_understanding": render_understanding(case.get("proposal", {}), ctx),
            "engineer_gate": evaluate(case.get("proposal", {})),
        }
        for case in cases
    ]
