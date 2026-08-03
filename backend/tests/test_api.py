from fastapi.testclient import TestClient

from app.catalog import CatalogObject, Package
from app.main import app, auth, service


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


def test_local_source_and_compatible_package_archive(tmp_path):
    package = Package(
        id="local-package", path="//pub/test/local", name="local",
        description="Local package", source_url="https://example.test/local.git", status="loaded",
    )
    item = CatalogObject(
        id="local-part", package_id=package.id, package_path=package.path, name="part",
        kind="part", description="Part", source_type="step", source_path="part.step",
        source_url=package.source_url, semantic_path="test/local:part",
    )
    checkout_key = f"{package.source_url}@HEAD"
    import hashlib
    checkout = service.package_dir / hashlib.sha256(checkout_key.encode()).hexdigest()[:16]
    checkout.mkdir(parents=True, exist_ok=True)
    (checkout / "partcad.yaml").write_text("parts: {}\n", encoding="utf-8")
    (checkout / "part.step").write_bytes(b"STEP")
    service._packages[package.id] = package
    service._objects[item.id] = item
    service._object_roots[item.id] = checkout
    archive = None
    try:
        assert service.source_file(item.id).read_bytes() == b"STEP"
        archive = service.package_archive(package.id)
        import zipfile
        with zipfile.ZipFile(archive) as content:
            assert "local/partcad.yaml" in content.namelist()
            assert "local/part.step" in content.namelist()
    finally:
        service._objects.pop(item.id, None)
        service._packages.pop(package.id, None)
        service._object_roots.pop(item.id, None)
        import shutil
        shutil.rmtree(checkout)
        if archive:
            archive.unlink(missing_ok=True)


def test_private_catalog_is_hidden_and_ticket_is_one_use(tmp_path):
    package = Package(id="private-package", path="//private/project/package", name="package",
                      description="Private", source_url=f"file://{tmp_path}", status="loaded")
    item = CatalogObject(id="private-part", package_id=package.id, package_path=package.path,
                         name="part", kind="part", description="Private part", source_type="step",
                         source_path="part.step", source_url=package.source_url,
                         semantic_path="private/project/package:part")
    (tmp_path / "part.step").write_bytes(b"PRIVATE")
    service._packages[package.id] = package
    service._objects[item.id] = item
    service._object_roots[item.id] = tmp_path
    plaintext, metadata = auth.create_key("test-user", "user")
    headers = {"Authorization": f"Bearer {plaintext}"}
    try:
        assert client.get(f"/api/v1/objects/{item.id}").status_code == 404
        assert client.get(f"/api/v1/objects/{item.id}", headers=headers).status_code == 200
        ticket = client.post("/api/v1/download-tickets", headers=headers, json={"object_id": item.id}).json()["ticket"]
        assert client.get(f"/api/v1/downloads/{ticket}").content == b"PRIVATE"
        assert client.get(f"/api/v1/downloads/{ticket}").status_code == 410
        assert client.get(f"/api/v1/objects/{item.id}", headers={"Authorization": "Bearer wrong"}).status_code == 401
        auth.revoke_key(metadata["key_id"])
        assert client.get(f"/api/v1/objects/{item.id}", headers=headers).status_code == 401
    finally:
        auth.revoke_key(metadata["key_id"])
        service._packages.pop(package.id, None)
        service._objects.pop(item.id, None)
        service._object_roots.pop(item.id, None)
