from __future__ import annotations

import base64
import hashlib
import math
import shutil
import sqlite3
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import trimesh
import yaml
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined
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
    revision: str | None = None
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
    semantic_path: str
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
        self.database_path = cache_dir / "catalog.sqlite3"
        self._packages: dict[str, Package] = {}
        self._objects: dict[str, CatalogObject] = {}
        self._object_roots: dict[str, Path] = {}
        self._lock = threading.RLock()
        for directory in (cache_dir, self.package_dir, self.preview_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._init_database()
        self._load_database()

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
            root_packages = list(self.packages)
        errors = 0
        for package in root_packages:
            try:
                self.load_package(package.id)
            except Exception:
                package.status = "error"
                errors += 1
        self._save_database()
        return {"packages": len(self._packages), "objects": len(self._objects), "errors": errors}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS packages (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
                    description TEXT NOT NULL, source_url TEXT NOT NULL, web_url TEXT,
                    rel_path TEXT, revision TEXT, category TEXT NOT NULL, status TEXT NOT NULL
                )"""
            )
            package_columns = {row[1] for row in connection.execute("PRAGMA table_info(packages)")}
            if "revision" not in package_columns:
                connection.execute("ALTER TABLE packages ADD COLUMN revision TEXT")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS objects (
                    id TEXT PRIMARY KEY, package_id TEXT NOT NULL, package_path TEXT NOT NULL,
                    name TEXT NOT NULL, kind TEXT NOT NULL, description TEXT NOT NULL,
                    source_type TEXT NOT NULL, source_path TEXT, source_url TEXT NOT NULL,
                    semantic_path TEXT NOT NULL, license TEXT, object_root TEXT,
                    FOREIGN KEY(package_id) REFERENCES packages(id)
                )"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_objects_package_id ON objects(package_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_objects_kind_name ON objects(kind, name)")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_objects_semantic_path ON objects(kind, semantic_path)"
            )
            connection.execute("PRAGMA optimize")

    def _load_database(self) -> None:
        with self._connect() as connection:
            for row in connection.execute("SELECT * FROM packages ORDER BY path"):
                package = Package(**dict(row))
                self._packages[package.id] = package
            for row in connection.execute("SELECT * FROM objects ORDER BY package_path, kind, name"):
                values = dict(row)
                object_root = values.pop("object_root")
                item = CatalogObject(**values)
                self._objects[item.id] = item
                if object_root:
                    self._object_roots[item.id] = Path(object_root)

    def _save_database(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM objects")
            connection.execute("DELETE FROM packages")
            connection.executemany(
                """INSERT INTO packages
                (id,path,name,description,source_url,web_url,rel_path,revision,category,status)
                VALUES (:id,:path,:name,:description,:source_url,:web_url,:rel_path,:revision,:category,:status)""",
                [asdict(package) for package in self.packages],
            )
            rows = []
            for item in self.objects:
                row = asdict(item)
                row["object_root"] = str(self._object_roots.get(item.id, ""))
                rows.append(row)
            connection.executemany(
                """INSERT INTO objects VALUES (
                    :id,:package_id,:package_path,:name,:kind,:description,:source_type,
                    :source_path,:source_url,:semantic_path,:license,:object_root
                )""",
                rows,
            )
            connection.execute("PRAGMA optimize")

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
                    revision=spec.get("revision"),
                    category=relative.parts[0] if relative.parts else "root",
                )

    def load_package(self, package_id: str) -> dict[str, Any]:
        with self._lock:
            package = self._packages.get(package_id)
            if not package:
                raise KeyError(package_id)
        checkout_key = f"{package.source_url}@{package.revision or 'HEAD'}"
        checkout = self.package_dir / hashlib.sha256(checkout_key.encode()).hexdigest()[:16]
        if not (checkout / ".git").exists():
            clone_args = ["git", "clone", "--depth", "1"]
            if package.revision:
                clone_args.extend(["--branch", package.revision])
            clone_args.extend([package.source_url, str(checkout)])
            _run(*clone_args)
        requested_path = checkout / package.rel_path if package.rel_path else checkout
        if requested_path.is_file():
            config_path = requested_path
            root = config_path.parent
            scan_nested = False
        else:
            root = requested_path
            config_path = root / "partcad.yaml"
            scan_nested = True
        if not config_path.exists():
            candidates = [path for path in root.rglob("partcad.yaml") if ".git" not in path.parts]
            if not candidates:
                raise CatalogError(f"Package {package.path} has no partcad.yaml")
            config_path = candidates[0]
            root = config_path.parent

        configs = [config_path]
        if scan_nested:
            configs.extend(
                path for path in root.rglob("partcad.yaml") if path != config_path and ".git" not in path.parts
            )
        with self._lock:
            for current_config in configs:
                data = self._load_package_yaml(current_config)
                current_root = current_config.parent
                if current_config == config_path:
                    current_package = package
                else:
                    relative = current_root.relative_to(root).as_posix()
                    declared_path = str(data.get("name", ""))
                    nested_path = declared_path if declared_path.startswith("//") else f"{package.path}/{relative}"
                    nested_id = _token(nested_path)
                    combined_rel_path = "/".join(filter(None, (package.rel_path, relative)))
                    current_package = self._packages.get(nested_id) or Package(
                        id=nested_id,
                        path=nested_path,
                        name=nested_path.rsplit("/", 1)[-1],
                        description=str(data.get("desc", f"Subpackage of {package.name}")),
                        source_url=package.source_url,
                        web_url=package.web_url,
                        rel_path=combined_rel_path,
                        revision=package.revision,
                        category=package.category,
                        status="loaded",
                    )
                    self._packages[nested_id] = current_package
                self._register_objects(current_package, current_root, data)
                current_package.status = "loaded"
            return self.package_detail(package_id)

    @staticmethod
    def _load_package_yaml(config_path: Path) -> dict[str, Any]:
        try:
            source = config_path.read_text(encoding="utf-8")
            if "{%" in source or "{{" in source:
                search_dirs = [config_path.parent, *list(config_path.parents)[:4]]
                environment = Environment(
                    loader=ChoiceLoader([FileSystemLoader(str(path)) for path in search_dirs]),
                    undefined=StrictUndefined,
                    autoescape=False,
                )
                source = environment.from_string(source).render(
                    package_name=config_path.parent.name,
                    M_PI=math.pi,
                    PI=math.pi,
                    SQRT_2=math.sqrt(2),
                    SQRT_3=math.sqrt(3),
                    SQRT_5=math.sqrt(5),
                    INCH=25.4,
                    INCHES=25.4,
                    FOOT=304.8,
                    FEET=304.8,
                    get_from_config=lambda: None,
                )
            data = yaml.safe_load(source) or {}
        except Exception as exc:
            raise CatalogError(f"Cannot read PartCAD configuration {config_path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise CatalogError(f"Invalid PartCAD configuration: {config_path}")
        return data

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
                    semantic_path=f"{package.path.removeprefix('//pub/')}:{name}",
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

    def object_by_path(self, kind: str, semantic_path: str) -> dict[str, Any]:
        normalized_kind = kind.casefold().removesuffix("s")
        for item in self._objects.values():
            if item.kind == normalized_kind and item.semantic_path == semantic_path:
                return asdict(item)
        raise KeyError(f"{kind}/{semantic_path}")

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
