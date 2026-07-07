import asyncio

import pytest

from app.eval import runner
from ingestion.pipeline import run as ingestion_run


@pytest.fixture(scope="module", autouse=True)
def seeded():
    asyncio.run(ingestion_run.run())


def test_evaluation_meets_thresholds():
    report = asyncio.run(runner.run_evaluation(persist=False))
    summary = report["summary"]

    assert summary["num_questions"] >= 20
    assert summary["recall_at_k"] >= runner.RECALL_THRESHOLD
    assert summary["grounded_pass_rate"] >= runner.GROUNDED_THRESHOLD
    assert summary["latency_p95_ms"] <= runner.LATENCY_P95_MS
    assert summary["passed"] is True


def test_low_quality_answer_is_flagged():
    # A question whose required supporting node is unrelated to what retrieval
    # will surface must fail grounding and be flagged as not passed.
    bogus = {
        "question_id": "q_bogus",
        "question": "胰島素如何降低血糖?",
        "topic": "blood_glucose_regulation",
        "expected_chunk_ids": ["chunk:sample:001"],
        "expected_node_ids": ["hormone:does_not_exist"],  # never in any subgraph
    }
    item = asyncio.run(runner._evaluate_question(bogus))
    assert item["grounded_pass"] is False
    assert item["passed"] is False


def test_evaluation_persists_run_and_items():
    report = asyncio.run(runner.run_evaluation(persist=True))
    assert report["summary"]["run_id"].startswith("eval:")
    assert len(report["items"]) == report["summary"]["num_questions"]
