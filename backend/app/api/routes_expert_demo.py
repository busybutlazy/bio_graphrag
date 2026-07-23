"""Expert-in-the-loop demo endpoints.

``GET /admin/expert-demo/cases`` 是固定 demo 資料
(``data/sample/expert_demo/cases.json``)的**唯讀**出口;``system_understanding``
(反向翻譯)與 ``engineer_gate``(形式檢查)結果**當場計算、不落地**,以證明
renderer / gate 是真的在跑,而非預存答案。

``POST /admin/expert-demo/reviews`` 把一位 demo 觀看者的專家 gate 決定寫成
**append-only 稽核列**(``graph_change_logs``,經 curation service);**不碰 approved
圖、不寫 Neo4j、不繞過 curation**。作者權威審查另行 seed;觀看者列以
``actor='demo-viewer'`` 區隔。

auth 與其他 ``/admin/*`` 一致(``require_admin``;未設 key 時為 demo 開放)。
對應 docs/expert-in-the-loop-plan.md 五.4(唯讀設計已依 expert-gate-integrity 變更為
唯讀讀取 + 附加式稽核寫入)。
"""

import json

from fastapi import APIRouter, Depends

from app.api.auth import require_admin
from app.curation.service import record_expert_review
from app.graph.back_translation import build_context, render_understanding
from app.graph.engineer_gate import evaluate
from app.schemas.expert_demo import ExpertReviewRequest
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


@router.post("/expert-demo/reviews", status_code=201)
async def record_expert_demo_review(body: ExpertReviewRequest) -> dict:
    """Persist a demo viewer's expert-gate decision as an append-only audit row.

    Writes only ``graph_change_logs`` (via curation service); never Neo4j, the
    approved graph, or ``curation_items``. Returns the generated ``change_id``.
    """
    change_id = await record_expert_review(
        case_id=body.case_id,
        decision=body.decision,
        schema_gap_type=body.schema_gap_type,
        notes=body.notes,
        actor="demo-viewer",
    )
    return {"change_id": change_id, "status": "recorded"}
