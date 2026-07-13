import asyncio

import pytest
from app.main import app
from fastapi.testclient import TestClient

from ingestion.pipeline import run as ingestion_run


@pytest.fixture(scope="module")
def seeded_client():
    asyncio.run(ingestion_run.run())
    return TestClient(app)


def test_get_node_returns_detail_with_properties(seeded_client):
    resp = seeded_client.get("/nodes/interaction:insulin_glucagon_blood_glucose")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "interaction:insulin_glucagon_blood_glucose"
    assert body["type"] == "Interaction"
    assert body["properties"]["interaction_type"] == "antagonism"
    # reserved keys must not leak into properties
    assert "status" not in body["properties"]
    assert "id" not in body["properties"]


def test_get_node_returns_404_for_unknown(seeded_client):
    resp = seeded_client.get("/nodes/does-not-exist")
    assert resp.status_code == 404


def test_concept_map_from_node_ids(seeded_client):
    resp = seeded_client.post(
        "/concept-map",
        json={"node_ids": ["hormone:insulin"], "depth": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    node_ids = {n["id"] for n in body["nodes"]}
    assert "hormone:insulin" in node_ids
    # depth-1 neighbours of insulin include its regulatory effect
    assert "regulatory_effect:insulin_decreases_blood_glucose" in node_ids


def test_concept_map_from_topic(seeded_client):
    resp = seeded_client.post(
        "/concept-map",
        json={"topic": "blood_glucose_regulation", "depth": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) > 0


def test_concept_map_requires_seed(seeded_client):
    resp = seeded_client.post("/concept-map", json={"depth": 1})
    assert resp.status_code == 422
