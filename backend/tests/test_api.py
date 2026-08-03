from fastapi.testclient import TestClient

from app.catalog import CatalogObject
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


def test_object_can_be_resolved_by_partcad_path():
    item = CatalogObject(
        id="ego-battery",
        package_id="ego",
        package_path="//pub/electrical/battery/ego",
        name="battery-7_5",
        kind="part",
        description="EGO battery",
        source_type="step",
        source_path="battery-7_5.step",
        source_url="https://github.com/partcad/partcad-electrical-ego",
        semantic_path="electrical/battery/ego:battery-7_5",
    )
    service._objects[item.id] = item
    try:
        response = client.get("/api/v1/by-path/part/electrical/battery/ego:battery-7_5")
        assert response.status_code == 200
        assert response.json()["name"] == "battery-7_5"
    finally:
        service._objects.pop(item.id, None)


def test_jinja_partcad_config_supports_math_constants(tmp_path):
    config = tmp_path / "partcad.yaml"
    config.write_text("parts:\n  item:\n    desc: '{{ SQRT_2 }}'\n", encoding="utf-8")
    data = service._load_package_yaml(config)
    assert data["parts"]["item"]["desc"].startswith("1.414")
