import asyncio
from datetime import date, timedelta

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db import vendors as vendors_db
from app.main import app
from ingestion.pipeline import run as ingestion_run

# Token endpoints (/query, /check-answer) are closed by default; tests seed a
# vendor account and send its key. Offline mode spends 0 tokens, so quota is only
# consumed when we explicitly record usage.
MAIN_KEY = "test-key-main"


async def _connect():
    return await asyncpg.connect(
        host=settings.postgres_host, port=settings.postgres_port, database=settings.postgres_db,
        user=settings.postgres_user, password=settings.postgres_password,
    )


async def _seed_vendor(code, key, quota, expires=None, active=True):
    conn = await _connect()
    try:
        await conn.execute("DELETE FROM vendor_usage WHERE vendor_code = $1", code)
        await conn.execute("DELETE FROM vendors WHERE vendor_code = $1", code)
        await conn.execute(
            """
            INSERT INTO vendors (vendor_code, name, api_key, expires_at, token_quota, active)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            code, code, key, expires, quota, active,
        )
    finally:
        await conn.close()


async def _remove_vendor(code):
    conn = await _connect()
    try:
        await conn.execute("DELETE FROM vendor_usage WHERE vendor_code = $1", code)
        await conn.execute("DELETE FROM vendors WHERE vendor_code = $1", code)
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def seeded_client():
    asyncio.run(ingestion_run.run())
    asyncio.run(_seed_vendor("test_vendor_main", MAIN_KEY, quota=1_000_000))
    client = TestClient(app, headers={"X-API-Key": MAIN_KEY})
    yield client
    asyncio.run(_remove_vendor("test_vendor_main"))


# --- happy path (authenticated) ----------------------------------------------


def test_query_returns_grounded_answer(seeded_client):
    resp = seeded_client.post(
        "/query", json={"question": "胰島素如何降低血糖?", "top_k": 5, "graph_depth": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    assert body["supporting_nodes"] or body["citations"]
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


# --- body validation happens after auth passes (needs a valid key) -----------


def test_query_rejects_overlong_question_when_authed(seeded_client):
    resp = seeded_client.post("/query", json={"question": "血" * 501})
    assert resp.status_code == 422


def test_query_rejects_top_k_over_limit_when_authed(seeded_client):
    resp = seeded_client.post("/query", json={"question": "血糖", "top_k": 11})
    assert resp.status_code == 422


def test_check_answer_rejects_overlong_answer_when_authed(seeded_client):
    resp = seeded_client.post(
        "/check-answer", json={"question": "q", "student_answer": "字" * 1001}
    )
    assert resp.status_code == 422


# --- access control gates -----------------------------------------------------


def test_query_unknown_key_rejected(seeded_client):
    resp = seeded_client.post(
        "/query", json={"question": "血糖"}, headers={"X-API-Key": "nope"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "login_required"


def test_query_disabled_vendor_rejected(seeded_client):
    asyncio.run(_seed_vendor("test_vendor_disabled", "test-key-disabled", quota=1000, active=False))
    try:
        resp = seeded_client.post(
            "/query", json={"question": "血糖"}, headers={"X-API-Key": "test-key-disabled"}
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "account_disabled"
    finally:
        asyncio.run(_remove_vendor("test_vendor_disabled"))


def test_query_expired_vendor_rejected(seeded_client):
    yesterday = date.today() - timedelta(days=1)
    asyncio.run(_seed_vendor("test_vendor_expired", "test-key-expired", quota=1000, expires=yesterday))
    try:
        resp = seeded_client.post(
            "/query", json={"question": "血糖"}, headers={"X-API-Key": "test-key-expired"}
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "account_expired"
    finally:
        asyncio.run(_remove_vendor("test_vendor_expired"))


def test_query_quota_exceeded_after_recorded_usage(seeded_client):
    asyncio.run(_seed_vendor("test_vendor_quota", "test-key-quota", quota=100))
    try:
        # Simulate prior spend that fills the quota, then the next call is blocked.
        asyncio.run(vendors_db.record_usage("test_vendor_quota", 100, "/query"))
        resp = seeded_client.post(
            "/query", json={"question": "血糖"}, headers={"X-API-Key": "test-key-quota"}
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "quota_exceeded"
    finally:
        asyncio.run(_remove_vendor("test_vendor_quota"))
