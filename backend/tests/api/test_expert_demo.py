import asyncio

import asyncpg
from app.core.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

T3_CASE = "blood_glucose_case_t3_test"


async def _cleanup_reviews(target_id: str) -> None:
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    try:
        await conn.execute("DELETE FROM graph_change_logs WHERE target_id = $1", target_id)
    finally:
        await conn.close()


def test_expert_demo_cases_read_only_contract():
    # Asserts only the GET read contract. The surface also has an append-only write
    # endpoint (POST /admin/expert-demo/reviews) — see test_post_review_validates_and_records.
    resp = client.get("/admin/expert-demo/cases")
    assert resp.status_code == 200
    cases = resp.json()
    assert len(cases) == 7

    for case in cases:
        # 原始 proposal 仍在(Tab1),且當場計算的兩個結果都附上
        assert "proposal" in case
        su = case["system_understanding"]
        assert su["text"] and "pattern" in su and "is_gap" in su
        gate = case["engineer_gate"]
        assert gate["result"] in {
            "pass",
            "fail_schema",
            "fail_pattern",
            "fail_testability",
            "needs_schema_extension",
        }
        assert isinstance(gate["checks"], list) and gate["checks"]


def test_expert_demo_gate_and_understanding_are_computed_live():
    cases = {c["id"]: c for c in client.get("/admin/expert-demo/cases").json()}
    # Case 1 過 gate 且非 gap
    c1 = cases["blood_glucose_case_001"]
    assert c1["engineer_gate"]["result"] == "pass"
    assert c1["system_understanding"]["is_gap"] is False
    # Case 5 為 schema gap → needs_schema_extension
    c5 = cases["blood_glucose_case_005"]
    assert c5["engineer_gate"]["result"] == "needs_schema_extension"
    assert c5["system_understanding"]["is_gap"] is True
    # Case 6 形式不完整(缺 ON_VARIABLE/方向邊)→ 工程師 gate 退回
    c6 = cases["blood_glucose_case_006"]
    assert c6["engineer_gate"]["result"] == "fail_pattern"
    # Case 7 形式合法但生物學錯誤:gate 過、understanding 非 gap,但專家 rejected(形式 vs 意義分離)
    c7 = cases["blood_glucose_case_007"]
    assert c7["engineer_gate"]["result"] == "pass"
    assert c7["system_understanding"]["is_gap"] is False
    # marquee "form vs meaning": renderer faithfully reflects the WRONG (reversed) direction
    # the expert rejects — pin the text so renderer drift can't quietly erase the point.
    assert "上升" in c7["system_understanding"]["text"]
    assert c7["expert_review"]["status"] == "rejected"


def test_post_review_validates_and_records():
    try:
        # invalid decision → 422 (Pydantic Literal), no row written
        bad = client.post(
            "/admin/expert-demo/reviews",
            json={"case_id": T3_CASE, "decision": "bogus"},
        )
        assert bad.status_code == 422

        # valid → 201 with change_id; surface is now read + append-only write
        ok = client.post(
            "/admin/expert-demo/reviews",
            json={"case_id": T3_CASE, "decision": "agree", "notes": "看起來正確"},
        )
        assert ok.status_code == 201
        body = ok.json()
        assert body["status"] == "recorded"
        assert body["change_id"].startswith("change:")
    finally:
        asyncio.run(_cleanup_reviews(T3_CASE))
