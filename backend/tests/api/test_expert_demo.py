from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_expert_demo_cases_read_only_contract():
    resp = client.get("/admin/expert-demo/cases")
    assert resp.status_code == 200
    cases = resp.json()
    assert len(cases) == 5

    for case in cases:
        # 原始 proposal 仍在(Tab1),且當場計算的兩個結果都附上
        assert "proposal" in case
        su = case["system_understanding"]
        assert su["text"] and "pattern" in su and "is_gap" in su
        gate = case["engineer_gate"]
        assert gate["result"] in {
            "pass", "fail_schema", "fail_pattern",
            "fail_testability", "needs_schema_extension",
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
