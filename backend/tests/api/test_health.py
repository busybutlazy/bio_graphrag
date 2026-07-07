from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_200_with_all_dependencies():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert {dep["name"] for dep in body["dependencies"]} == {"postgres", "neo4j", "qdrant"}
