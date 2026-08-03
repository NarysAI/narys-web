from fastapi.testclient import TestClient

from app.main import app, service


client = TestClient(app)


def test_health_contract():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalog_contract():
    response = client.get("/api/v1/catalog")
    assert response.status_code == 200
    assert "categories" in response.json()


def test_missing_object_is_404():
    response = client.get("/api/v1/objects/not-a-real-object")
    assert response.status_code == 404
