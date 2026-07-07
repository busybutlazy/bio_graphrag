import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from ingestion.pipeline import run as ingestion_run


@pytest.fixture(scope="module")
def seeded_client():
    asyncio.run(ingestion_run.run())
    return TestClient(app)


def test_query_returns_grounded_answer(seeded_client):
    resp = seeded_client.post(
        "/query",
        json={"question": "胰島素如何降低血糖?", "top_k": 5, "graph_depth": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    # grounded: must return supporting nodes or citations
    assert body["supporting_nodes"] or body["citations"]
    # node cap from api_contract
    assert len(body["supporting_nodes"]) <= 30


def test_query_debug_hidden_by_default(seeded_client):
    resp = seeded_client.post("/query", json={"question": "血糖如何調節?"})
    assert resp.status_code == 200
    assert resp.json()["retrieval_debug"] is None


def test_query_debug_visible_when_requested_in_local_env(seeded_client):
    resp = seeded_client.post(
        "/query", json={"question": "血糖如何調節?", "include_debug": True}
    )
    assert resp.status_code == 200
    debug = resp.json()["retrieval_debug"]
    assert debug is not None
    assert debug["graph_depth"] == 1


def test_check_answer_returns_verdict(seeded_client):
    resp = seeded_client.post(
        "/check-answer",
        json={
            "question": "胰島素與升糖素如何調節血糖?",
            "student_answer": "胰島素降低血糖,升糖素提高血糖,兩者拮抗維持恆定。",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["is_correct"], bool)
    assert "feedback" in body
