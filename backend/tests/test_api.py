import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import pytest
import trimesh

from app.catalog import CatalogError, CatalogObject, CatalogService, Package, scad_materials
from app.main import app, auth, service


client = TestClient(app)


def test_scad_material_declarations(tmp_path):
    source = tmp_path / "colored.scad"
    source.write_text(
        "// NARYS_MATERIAL: housing=#25282B\n"
        "// NARYS_MATERIAL: contacts=#D6A83B\n",
        encoding="utf-8",
    )
    assert scad_materials(source) == [
        ("housing", (37, 40, 43, 255)),
        ("contacts", (214, 168, 59, 255)),
    ]


def test_health_contract():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalog_contract():
    response = client.get("/api/v1/catalog")
    assert response.status_code == 200
    assert "categories" in response.json()


def test_catalog_hides_empty_containers_but_keeps_populated_descendants(tmp_path):
    local = CatalogService(
        index_url="unused",
        index_ref="main",
        cache_dir=tmp_path / "cache",
        index_dir=tmp_path / "index",
    )
    parent = Package(
        id="empty-container",
        path="//pub/std/metric",
        name="metric",
        description="Empty navigation container",
        source_url="https://example.test/PUB.git",
        category="std",
    )
    child = Package(
        id="populated-child",
        path="//pub/std/metric/standoffs",
        name="standoffs",
        description="Metric threaded standoffs",
        source_url="https://example.test/PUB.git",
        category="std",
    )
    local._packages = {parent.id: parent, child.id: child}
    local._objects["standoff-ff"] = CatalogObject(
        id="standoff-ff",
        package_id=child.id,
        package_path=child.path,
        name="female-female",
        kind="part",
        description="Female-female threaded standoff",
        source_type="scad",
        source_path="female-female.scad",
        source_url=child.source_url,
        semantic_path="std/metric/standoffs:female-female",
    )

    payload = local.catalog()
    package_ids = {
        package["id"]
        for category in payload["categories"]
        for package in category["packages"]
    }
    assert package_ids == {child.id}
    assert payload["package_count"] == 1
    assert local.search("empty navigation") == []
    assert local.package_detail(parent.id)["objects"] == []


def test_direct_empty_package_page_is_404(monkeypatch):
    package = Package(
        id="empty-package-page",
        path="//pub/std/metric/empty",
        name="empty",
        description="No catalog objects",
        source_url="https://example.test/PUB.git",
    )
    service._packages[package.id] = package
    monkeypatch.setattr(service, "load_package", lambda _: {})
    try:
        response = client.get(f"/api/v1/packages/{package.id}")
        assert response.status_code == 404
    finally:
        service._packages.pop(package.id, None)


def test_missing_object_is_404():
    response = client.get("/api/v1/objects/not-a-real-object")
    assert response.status_code == 404


def test_duplicate_preview_parameter_is_rejected():
    item = CatalogObject(
        id="duplicate-query",
        package_id="test",
        package_path="//pub/test",
        name="duplicate-query",
        kind="part",
        description="Test object",
        source_type="scad",
        source_path="test.scad",
        source_url="https://example.test/PUB.git",
        semantic_path="test:duplicate-query",
    )
    service._objects[item.id] = item
    try:
        response = client.get(f"/api/v1/objects/{item.id}/preview.gltf?body_length=10&body_length=10")
        assert response.status_code == 422
        assert response.json()["detail"] == "Duplicate preview parameter"
    finally:
        service._objects.pop(item.id, None)


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


def test_electronic_component_requires_scad():
    CatalogService._validate_model_role("camera", "scad", "camera.scad", "electronic_component")
    with pytest.raises(CatalogError, match="requires exactly one .scad"):
        CatalogService._validate_model_role("camera", "freecad", "camera.FCStd", "electronic_component")


def test_printable_part_requires_freecad_master():
    CatalogService._validate_model_role("bracket", "freecad", "bracket.FCStd", "printable_part")
    with pytest.raises(CatalogError, match="requires exactly one .FCStd"):
        CatalogService._validate_model_role("bracket", "scad", "bracket.scad", "printable_part")


def test_basic_sketch_has_generated_preview_without_fake_source(tmp_path):
    local = CatalogService(
        index_url="unused",
        index_ref="main",
        cache_dir=tmp_path / "cache",
        index_dir=tmp_path / "index",
    )
    package = Package(
        id="metric-m",
        path="//pub/std/metric/m",
        name="m",
        description="Metric interfaces",
        source_url="https://example.test/PUB.git",
    )
    local._packages[package.id] = package
    local._register_objects(package, tmp_path, {"sketches": {"m1": {"type": "basic", "circle": 0.5}}})
    item = local.objects[0]

    assert item.source_path is None
    preview = local.preview(item.id)
    scene = trimesh.load(preview, force="scene")
    assert scene.extents.tolist() == pytest.approx([1.0, 1.0, 0.08], abs=0.01)


def test_scad_configuration_is_exposed_without_leaking_the_full_spec(tmp_path):
    local = CatalogService(
        index_url="unused",
        index_ref="main",
        cache_dir=tmp_path / "cache",
        index_dir=tmp_path / "index",
    )
    package = Package(
        id="standoffs",
        path="//pub/std/metric/standoffs",
        name="standoffs",
        description="Metric standoffs",
        source_url="https://example.test/PUB.git",
    )
    local._packages[package.id] = package
    local._register_objects(package, tmp_path, {"parts": {"mf": {
        "type": "scad",
        "path": "mf.scad",
        "parameters": {
            "thread_diameter": {"type": "float", "default": 3.0, "min": 2.0, "max": 6.0},
            "body_length": {"type": "float", "default": 10.0, "min": 4.0, "max": 100.0},
        },
        "narys": {
            "parameter_options": {"thread_diameter": [2.0, 3.0], "body_length": [6.0, 10.0]},
            "presets": {
                "m2": {"label": "M2", "parameters": {"thread_diameter": 2.0, "body_length": 6.0}},
                "broken": {"label": "Broken", "parameters": {"thread_diameter": 9.0, "body_length": 6.0}},
            },
        },
    }}})
    payload = local.object_detail(local.objects[0].id)

    assert payload["parameters"]["thread_diameter"]["default"] == 3.0
    assert payload["parameter_presets"] == [{
        "id": "m2",
        "label": "M2",
        "parameters": {"thread_diameter": 2.0, "body_length": 6.0},
    }]
    assert "spec_json" not in payload


def test_scad_preview_validates_and_passes_parameter_overrides(tmp_path, monkeypatch):
    local = CatalogService(
        index_url="unused",
        index_ref="main",
        cache_dir=tmp_path / "cache",
        index_dir=tmp_path / "index",
    )
    source = tmp_path / "standoff.scad"
    source.write_text("cube([body_length, thread_diameter, 1]);\n", encoding="utf-8")
    spec = {
        "type": "scad",
        "path": source.name,
        "parameters": {
            "thread_diameter": {"type": "float", "default": 3.0, "min": 2.0, "max": 6.0},
            "body_length": {"type": "float", "default": 10.0, "min": 4.0, "max": 100.0},
        },
        "narys": {
            "parameter_options": {"thread_diameter": [2.0, 2.5, 3.0], "body_length": [6.0, 10.0, 12.0]},
        },
    }
    item = CatalogObject(
        id="standoff-mf",
        package_id="standoffs",
        package_path="//pub/std/metric/standoffs",
        name="standoff-mf",
        kind="part",
        description="Configurable standoff",
        source_type="scad",
        source_path=source.name,
        source_url="https://example.test/PUB.git",
        semantic_path="std/metric/standoffs:standoff-mf",
        spec_json=json.dumps(spec),
    )
    local._objects[item.id] = item
    local._object_roots[item.id] = tmp_path
    calls: list[list[str]] = []

    def fake_openscad(args, **_kwargs):
        calls.append(args)
        output = Path(args[args.index("-o") + 1])
        trimesh.creation.box().export(output)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("app.catalog.subprocess.run", fake_openscad)
    configured = local.preview(item.id, {"thread_diameter": "2.5", "body_length": "12"})
    configured_again = local.preview(item.id, {"thread_diameter": "2.50", "body_length": "12.0"})

    assert configured.is_file()
    assert configured_again == configured
    assert len(calls) == 1
    assert "thread_diameter=2.5" in calls[0]
    assert "body_length=12.0" in calls[0]
    with pytest.raises(CatalogError, match="at least 2.0"):
        local.preview(item.id, {"thread_diameter": "1"})
    with pytest.raises(CatalogError, match="Unsupported value"):
        local.preview(item.id, {"thread_diameter": "2.7"})
    with pytest.raises(CatalogError, match="Unknown preview parameter"):
        local.preview(item.id, {"shell": "rm"})


def test_thumbnail_prefers_checked_in_release_png(tmp_path):
    release = tmp_path / "cad" / "v1.0.0"
    source_dir = release / "FCstd"
    source_dir.mkdir(parents=True)
    source = source_dir / "case.FCStd"
    source.write_bytes(b"FCStd")
    thumbnail = release / "case.png"
    from PIL import Image
    Image.new("RGB", (32, 20), "#00ff99").save(thumbnail)

    item = CatalogObject(
        id="release-preview", package_id="case", package_path="//pub/fpv/case",
        name="case", kind="part", description="Case", source_type="freecad",
        source_path="cad/v1.0.0/FCstd/case.FCStd", source_url="https://example.test/case",
        semantic_path="fpv/case:case",
    )
    service._objects[item.id] = item
    service._object_roots[item.id] = tmp_path
    try:
        assert service.thumbnail(item.id) == thumbnail
    finally:
        service._objects.pop(item.id, None)
        service._object_roots.pop(item.id, None)


def test_unknown_model_role_is_rejected():
    with pytest.raises(CatalogError, match="unsupported model_role"):
        CatalogService._validate_model_role("thing", "scad", "thing.scad", "unknown")


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


def test_project_metadata_is_exposed_without_changing_package_routes(tmp_path):
    repository = tmp_path / "project"
    repository.mkdir()
    (repository / "partcad.yaml").write_text(
        "name: //pub/fpv/case-holder\n"
        "desc: FPV project\n"
        "narys_project:\n"
        "  schema_version: 1\n"
        "  kind: project\n"
        "  access: public\n"
        "  canonical_repo: https://github.com/NarysAI/Case_holder\n"
        "  default_branch: main\n"
        "  contribution_url: https://github.com/NarysAI/Case_holder/blob/main/CONTRIBUTING.md\n"
        "  issues_url: https://github.com/NarysAI/Case_holder/issues\n"
        "  current_drawing: drawing-v1.0.0\n"
        "  category: FPV\n",
        encoding="utf-8",
    )
    package = Package(
        id="case-project",
        path="//pub/fpv/case-holder",
        name="Case_holder",
        description="FPV project",
        source_url=repository.as_uri(),
        category="fpv",
    )
    service._packages[package.id] = package
    try:
        payload = service.load_package(package.id)
        detail = service.package_detail(package.id)
        assert payload["entry_type"] == "project"
        assert detail["canonical_repo_url"] == "https://github.com/NarysAI/Case_holder"
        assert detail["current_drawing"] == "drawing-v1.0.0"
        assert detail["objects"] == []
    finally:
        service._packages.pop(package.id, None)


def test_private_index_accepts_standalone_git_projects_without_guest_leak(tmp_path):
    private = tmp_path / "indra"
    (private / "index").mkdir(parents=True)
    (private / "index" / "partcad.yaml").write_text(
        "desc: private overlay\n"
        "import:\n"
        "  comp-ivins-case-4:\n"
        "    type: git\n"
        "    url: https://github.com/NarysAI/COMP-IVINS-CASE-4.git\n"
        "    catalog_path: projects/comp-ivins-case-4\n"
        "    revision: main\n"
        "    narys_project:\n"
        "      kind: project\n"
        "      access: private\n"
        "      canonical_repo: https://github.com/NarysAI/COMP-IVINS-CASE-4\n",
        encoding="utf-8",
    )
    local = CatalogService(
        index_url="unused",
        index_ref="main",
        cache_dir=tmp_path / "cache",
        private_repo_dir=private,
        index_dir=tmp_path / "index",
    )
    (tmp_path / "index").mkdir()
    local._read_private_index()
    assert local.catalog(include_private=False)["package_count"] == 0
    private_catalog = local.catalog(include_private=True)
    assert private_catalog["package_count"] == 1
    indexed = private_catalog["categories"][0]["packages"][0]
    assert indexed["entry_type"] == "project"
    assert indexed["visibility"] == "private"
    assert indexed["canonical_repo_url"].endswith("COMP-IVINS-CASE-4")


def test_git_askpass_script_never_contains_the_private_token(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("secret-token-value\n", encoding="utf-8")
    local = CatalogService(
        index_url="unused",
        index_ref="main",
        cache_dir=tmp_path / "cache",
        index_dir=tmp_path / "index",
        github_token_file=token_file,
    )
    environment = local._git_environment()
    assert environment["GIT_PASSWORD"] == "secret-token-value"
    assert "secret-token-value" not in local.git_askpass.read_text(encoding="utf-8")


def test_guest_cannot_trigger_a_private_repository_clone(monkeypatch):
    package = Package(
        id="private-project-guard",
        path="//private/projects/guarded",
        name="guarded",
        description="Private project",
        source_url="https://github.com/NarysAI/guarded.git",
        access="private",
        entry_type="project",
    )
    service._packages[package.id] = package
    called = False

    def guarded_load(_: str):
        nonlocal called
        called = True

    monkeypatch.setattr(service, "load_package", guarded_load)
    try:
        assert client.get(f"/api/v1/packages/{package.id}").status_code == 404
        assert called is False
    finally:
        service._packages.pop(package.id, None)
