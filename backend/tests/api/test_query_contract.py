"""Contract / access-control tests that don't require live databases.

Oversized params are rejected by request validation (422) before any DB call,
and the forbidden bulk/raw endpoints must simply not exist (404).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_query_rejects_overlong_question():
    resp = client.post("/query", json={"question": "血" * 501})
    assert resp.status_code == 422


def test_query_rejects_top_k_over_limit():
    resp = client.post("/query", json={"question": "血糖", "top_k": 11})
    assert resp.status_code == 422


def test_query_rejects_graph_depth_over_limit():
    resp = client.post("/query", json={"question": "血糖", "graph_depth": 3})
    assert resp.status_code == 422


def test_query_rejects_empty_question():
    resp = client.post("/query", json={"question": ""})
    assert resp.status_code == 422


def test_check_answer_requires_question_or_id():
    resp = client.post("/check-answer", json={"student_answer": "something"})
    assert resp.status_code == 422


def test_check_answer_rejects_overlong_student_answer():
    resp = client.post(
        "/check-answer", json={"question": "q", "student_answer": "字" * 1001}
    )
    assert resp.status_code == 422


def test_concept_map_rejects_depth_over_limit():
    resp = client.post("/concept-map", json={"node_ids": ["x"], "depth": 3})
    assert resp.status_code == 422


def test_neighbors_rejects_depth_over_limit():
    resp = client.get("/neighbors/x?depth=3")
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/cypher"),
        ("get", "/all-nodes"),
        ("get", "/all-edges"),
        ("get", "/export-all"),
        ("get", "/raw-source/doc:sample:blood_glucose_regulation"),
    ],
)
def test_forbidden_endpoints_do_not_exist(method, path):
    resp = client.post(path, json={}) if method == "post" else client.get(path)
    assert resp.status_code == 404
