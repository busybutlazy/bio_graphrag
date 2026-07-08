"""Contract / access-control tests that don't require live databases.

The token endpoints (/query, /check-answer) are closed by default: with no key
the require_vendor dependency short-circuits to 401 *before* any DB call or body
validation (auth runs before validation in FastAPI). Body-validation 422 cases
for those endpoints are covered in the authenticated integration test. The still
-open endpoints (concept-map, neighbors) keep their 422 checks here, and the
forbidden bulk/raw endpoints must simply not exist (404).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_query_requires_login_when_no_key():
    # Even a malformed body returns the auth gate first (401), not 422.
    resp = client.post("/query", json={"question": "血" * 501})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "login_required"


def test_query_valid_body_still_requires_login():
    resp = client.post("/query", json={"question": "血糖", "top_k": 5})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "login_required"


def test_check_answer_requires_login_when_no_key():
    resp = client.post("/check-answer", json={"question": "q", "student_answer": "a"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "login_required"


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
