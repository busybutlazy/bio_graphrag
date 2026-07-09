import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

DEMO_SOURCE = "data/sample/chapters/demo.md"


@pytest.fixture
def client():
    return TestClient(app)


# --- options ------------------------------------------------------------------


def test_options_lists_strategies_and_demo_source(client):
    resp = client.get("/admin/ingest/options")
    assert resp.status_code == 200
    body = resp.json()

    names = {s["name"] for s in body["strategies"]}
    assert names == {"fixed", "recursive", "markdown_header"}
    assert body["run_requires_owner_token"] is True

    source_keys = {s["key"] for s in body["sources"]}
    assert DEMO_SOURCE in source_keys


# --- preview (admin key only, no spend) ---------------------------------------


def test_preview_returns_chunks_and_prompts_without_spend(client):
    resp = client.post(
        "/admin/ingest/preview",
        json={"source": DEMO_SOURCE, "strategy": "markdown_header"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "preview"
    assert body["dry_run"] is True
    assert body["system_prompt"]
    assert len(body["chunks"]) >= 2
    for ch in body["chunks"]:
        assert ch["user_prompt"]
        assert ch["tokens"] == 0


def test_preview_strategy_switch_changes_chunk_count(client):
    coarse = client.post(
        "/admin/ingest/preview",
        json={"source": DEMO_SOURCE, "strategy": "fixed",
              "chunk_params": {"chunk_size": 5000, "chunk_overlap": 0}},
    ).json()
    fine = client.post(
        "/admin/ingest/preview",
        json={"source": DEMO_SOURCE, "strategy": "fixed",
              "chunk_params": {"chunk_size": 80, "chunk_overlap": 0}},
    ).json()
    assert len(fine["chunks"]) > len(coarse["chunks"])


def test_preview_rejects_unknown_strategy(client):
    resp = client.post(
        "/admin/ingest/preview",
        json={"source": DEMO_SOURCE, "strategy": "does_not_exist"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unknown_strategy"


def test_preview_rejects_path_traversal(client):
    resp = client.post(
        "/admin/ingest/preview",
        json={"source": "../../../etc/passwd", "strategy": "fixed"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "source_not_found"


# --- run (owner-only lock) ----------------------------------------------------


def test_run_locked_without_owner_token(client, monkeypatch):
    # even with an owner secret configured, a missing token stays locked
    monkeypatch.setattr(settings, "ingest_owner_secret", "s3cret")
    resp = client.post("/admin/ingest/run", json={"source": DEMO_SOURCE})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ingest_locked"


def test_run_locked_when_no_secret_configured(client, monkeypatch):
    # closed by default: empty secret locks the endpoint for everyone
    monkeypatch.setattr(settings, "ingest_owner_secret", "")
    resp = client.post(
        "/admin/ingest/run",
        json={"source": DEMO_SOURCE},
        headers={"X-Ingest-Owner-Token": "anything"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ingest_locked"


def test_run_wrong_owner_token_locked(client, monkeypatch):
    monkeypatch.setattr(settings, "ingest_owner_secret", "s3cret")
    resp = client.post(
        "/admin/ingest/run",
        json={"source": DEMO_SOURCE},
        headers={"X-Ingest-Owner-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_run_unlocked_but_llm_not_configured(client, monkeypatch):
    # correct owner token passes the lock; without an LLM key the run reports a
    # clean config error instead of silently staging nothing.
    monkeypatch.setattr(settings, "ingest_owner_secret", "s3cret")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    resp = client.post(
        "/admin/ingest/run",
        json={"source": DEMO_SOURCE},
        headers={"X-Ingest-Owner-Token": "s3cret"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "llm_not_configured"
