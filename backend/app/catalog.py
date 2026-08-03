from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import trimesh
import yaml
from PIL import Image, ImageDraw


class CatalogError(RuntimeError):
    pass


@dataclass
class Package:
    id: str
    path: str
    name: str
    description: str
    source_url: str
    web_url: str | None = None
    rel_path: str | None = None
    category: str = "other"
    status: str = "available"


@dataclass
class CatalogObject:
    id: str
    package_id: str
    package_path: str
    name: str
    kind: str
    description: str
    source_type: str
    source_path: str | None
    source_url: str
    license: str | None = None


def _token(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _run(*args: str, cwd: Path | None = None) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise CatalogError((result.stderr or result.stdout).strip())


class CatalogService:
    def __init__(self, index_url: str, index_ref: str, cache_dir: Path):
        self.index_url = index_url
        self.index_ref = index_ref
        self.cache_dir = cache_dir
        self.index_dir = cache_dir / "index"
        self.package_dir = cache_dir / "packages"
        self.preview_dir = cache_dir / "previews"
        self._packages: dict[str, Package] = {}
        self._objects: dict[str, CatalogObject] = {}
        self._object_roots: dict[str, Path] = {}
        self._lock = threading.RLock()
        for directory in (cache_dir, self.package_dir, self.preview_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def packages(self) -> list[Package]:
        return sorted(self._packages.values(), key=lambda item: item.path)

    @property
    def objects(self) -> list[CatalogObject]:
        return sorted(self._objects.values(), key=lambda item: (item.package_path, item.kind, item.name))

    def refresh(self) -> dict[str, int]:
        with self._lock:
            self._sync_index()
            self._packages.clear()
            self._objects.clear()
            self._object_roots.clear()
            self._read_index()
            for package in self.packages:
                if "NarysAI/" in package.source_url:
                    try:
                        self.load_package(package.id)
                    except CatalogError:
                        package.status = "error"
            return {"packages": len(self._packages), "objects": len(self._objects)}

    def _sync_index(self) -> None:
        if self.index_dir.exists() and (self.index_dir / ".git").exists():
            _run("git", "fetch", "origin", self.index_ref, cwd=self.index_dir)
            _run("git", "reset", "--hard", "FETCH_HEAD", cwd=self.index_dir)
        else:
            if self.index_dir.exists():
                shutil.rmtree(self.index_dir)
            _run("git", "clone", "--depth", "1", "--branch", self.index_ref, self.index_url, str(self.index_dir))

    def _read_index(self) -> None:
        for config_path in self.index_dir.rglob("partcad.yaml"):
            relative = config_path.parent.relative_to(self.index_dir)
            category_path = "/".join(relative.parts)
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            imports = data.get("import", {}) | data.get("dependencies", {})
            if not isinstance(imports, dict):
                continue
            for name, spec in imports.items():
                if not isinstance(spec, dict) or spec.get("type") != "git" or not spec.get("url"):
                    continue
                path = "/".join(filter(None, ("//pub", category_path, str(name))))
                package_id = _token(path)
                self._packages[package_id] = Package(
                    id=package_id,
                    path=path,
                    name=str(name),
                    description=str(spec.get("desc", "PartCAD package")),
                    source_url=str(spec["url"]),
                    web_url=spec.get("web"),
                    rel_path=spec.get("relPath"),
                    category=relative.parts[0] if relative.parts else "root",
                )

    def load_package(self, package_id: str) -> dict[str, Any]:
        with self._lock:
            package = self._packages.get(package_id)
            if not package:
                raise KeyError(package_id)
            checkout = self.package_dir / hashlib.sha256(package.source_url.encode()).hexdigest()[:16]
            if not (checkout / ".git").exists():
                _run("git", "clone", "--depth", "1", package.source_url, str(checkout))
            root = checkout / package.rel_path if package.rel_path else checkout
            config_path = root / "partcad.yaml"
            if not config_path.exists():
                candidates = list(root.rglob("partcad.yaml"))
                if len(candidates) != 1:
                    raise CatalogError(f"Package {package.path} has no unambiguous partcad.yaml")
                config_path = candidates[0]
                root = config_path.parent
            self._register_objects(package, root, yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})
            package.status = "loaded"
            return self.package_detail(package_id)

    def _register_objects(self, package: Package, root: Path, data: dict[str, Any]) -> None:
        license_name = data.get("license")
        for kind, key in (("part", "parts"), ("assembly", "assemblies"), ("sketch", "sketches")):
            entries = data.get(key, {}) or {}
            for name, raw in entries.items():
                spec = raw if isinstance(raw, dict) else {}
                source_type = str(spec.get("type", "native"))
                default_ext = "3mf" if source_type == "3mf" else source_type
                source_path = spec.get("path") or (f"{name}.{default_ext}" if source_type not in {"native", "ai"} else None)
                object_id = _token(f"{package.id}|{kind}|{name}")
                self._objects[object_id] = CatalogObject(
                    id=object_id,
                    package_id=package.id,
                    package_path=package.path,
                    name=str(name),
                    kind=kind,
                    description=str(spec.get("desc", f"{kind.title()} from {package.name}")),
                    source_type=source_type,
                    source_path=str(source_path) if source_path else None,
                    source_url=package.web_url or package.source_url.removesuffix(".git"),
                    license=str(license_name) if license_name else None,
                )
                self._object_roots[object_id] = root

    def package_detail(self, package_id: str) -> dict[str, Any]:
        package = self._packages[package_id]
        objects = [asdict(item) for item in self.objects if item.package_id == package_id]
        return {**asdict(package), "objects": objects}

    def catalog(self) -> dict[str, Any]:
        categories: dict[str, list[dict[str, Any]]] = {}
        for package in self.packages:
            categories.setdefault(package.category, []).append(asdict(package))
        return {
            "name": "NarysAI Registry",
            "package_count": len(self._packages),
            "object_count": len(self._objects),
            "categories": [{"name": name, "packages": items} for name, items in sorted(categories.items())],
            "featured": [asdict(item) for item in self.objects[:12]],
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        needle = query.casefold().strip()
        values: list[dict[str, Any]] = []
        for package in self.packages:
            if needle in f"{package.name} {package.description} {package.path}".casefold():
                values.append({"result_type": "package", **asdict(package)})
        for item in self.objects:
            if needle in f"{item.name} {item.description} {item.package_path}".casefold():
                values.append({"result_type": "object", **asdict(item)})
        return values[:100]

    def object_detail(self, object_id: str) -> dict[str, Any]:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        return asdict(item)

    def preview(self, object_id: str) -> Path:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        output = self.preview_dir / f"{object_id}.glb"
        if output.exists():
            return output
        root = self._object_roots.get(object_id)
        if not root or not item.source_path:
            raise CatalogError("This object does not expose a directly convertible source file")
        source = (root / item.source_path).resolve()
        if not source.is_relative_to(root.resolve()) or not source.exists():
            raise CatalogError(f"Source model is unavailable: {item.source_path}")
        try:
            mesh = trimesh.load(source, force="scene")
            mesh.export(output, file_type="glb")
        except Exception as exc:
            raise CatalogError(f"Preview conversion failed: {exc}") from exc
        return output

    def thumbnail(self, object_id: str) -> Path:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        output = self.preview_dir / f"{object_id}.png"
        if not output.exists():
            image = Image.new("RGB", (960, 600), "#101a18")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((110, 90, 850, 510), radius=48, fill="#172824", outline="#6ee7b7", width=4)
            draw.text((160, 150), "NarysAI", fill="#6ee7b7", font_size=42)
            draw.text((160, 260), item.name[:34], fill="#f1f5f3", font_size=44)
            draw.text((160, 340), f"{item.kind.upper()} · {item.source_type.upper()}", fill="#9fb4ae", font_size=25)
            image.save(output)
        return output
