from __future__ import annotations

import base64
import hashlib
import math
import shutil
import sqlite3
import subprocess
import threading
import tempfile
import zipfile
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
    def __init__(self, index_url: str, index_ref: str, cache_dir: Path, private_repo_dir: Path | None = None, public_repo_dir: Path | None = None, index_dir: Path | None = None):
        self.index_url = index_url
        self.index_ref = index_ref
        self.cache_dir = cache_dir
        self.index_dir = index_dir or cache_dir / "index"
        self.managed_index = index_dir is None
        self.package_dir = cache_dir / "packages"
        self.preview_dir = cache_dir / "previews"
        self.database_path = cache_dir / "catalog.sqlite3"
        self.private_repo_dir = private_repo_dir
        self.public_repo_dir = public_repo_dir
        self._packages: dict[str, Package] = {}
        self._objects: dict[str, CatalogObject] = {}
        self._object_roots: dict[str, Path] = {}
        self._lock = threading.RLock()
        self._updated_checkouts: set[Path] = set()
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

    @staticmethod
    def _is_private_path(path: str) -> bool:
        return path == "//private" or path.startswith("//private/")

    def _package_payload(self, package: Package) -> dict[str, Any]:
        private = self._is_private_path(package.path)
        return {
            **asdict(package),
            "namespace": "//private" if private else "//pub",
            "visibility": "private" if private else "public",
            "repository": "indra" if private else "PUB",
            "git_commit": package.revision or "main",
            "upstream_url": package.source_url,
            "license_status": "unverified",
        }

    def _object_payload(self, item: CatalogObject) -> dict[str, Any]:
        private = self._is_private_path(item.package_path)
        source = self._object_roots.get(item.id)
        file_path = (source / item.source_path).resolve() if source and item.source_path else None
        checksum = None
        size = None
        if file_path and file_path.is_file() and file_path.is_relative_to(source.resolve()):
            size = file_path.stat().st_size
            digest = hashlib.sha256()
            with file_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            checksum = digest.hexdigest()
        package_relative = item.package_path.removeprefix("//pub/").removeprefix("//private/")
        return {
            **asdict(item),
            "namespace": "//private" if private else "//pub",
            "visibility": "private" if private else "public",
            "repository": "indra" if private else "PUB",
            "git_path": "/".join(filter(None, (package_relative, item.source_path))),
            "git_commit": "main",
            "upstream_url": item.source_url,
            "checksum": checksum,
            "size": size,
            "license_status": "verified" if item.license else "unverified",
        }

    def refresh(self) -> dict[str, int]:
        with self._lock:
            self._updated_checkouts.clear()
            self._sync_index()
            self._packages.clear()
            self._objects.clear()
            self._object_roots.clear()
            self._read_index()
            self._read_private_index()
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
        if not self.managed_index:
            if not self.index_dir.is_dir():
                raise CatalogError(f"Local index directory is unavailable: {self.index_dir}")
            return
        if self.index_dir.exists() and (self.index_dir / ".git").exists():
            _run("git", "remote", "set-url", "origin", self.index_url, cwd=self.index_dir)
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

    def _read_private_index(self) -> None:
        if not self.private_repo_dir:
            return
        config_path = self.private_repo_dir / "index" / "partcad.yaml"
        if not config_path.is_file():
            return
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        imports = data.get("import", {})
        if not isinstance(imports, dict):
            return
        for name, spec in imports.items():
            if not isinstance(spec, dict) or not spec.get("path"):
                continue
            relative = str(spec["path"]).strip("/")
            package_path = f"//private/{relative}"
            package_id = _token(package_path)
            self._packages[package_id] = Package(
                id=package_id,
                path=package_path,
                name=str(name),
                description=str(spec.get("desc", "Private NarysAI package")),
                source_url=self.private_repo_dir.as_uri(),
                rel_path=relative,
                revision="main",
                category="private",
            )

    def load_package(self, package_id: str) -> dict[str, Any]:
        with self._lock:
            package = self._packages.get(package_id)
            if not package:
                raise KeyError(package_id)
        checkout_key = f"{package.source_url}@{package.revision or 'HEAD'}"
        public_mirror = self.public_repo_dir if package.source_url.rstrip("/").removesuffix(".git") == "https://github.com/NarysAI/PUB" else None
        local_repository = package.source_url.startswith("file://") or public_mirror is not None
        checkout = public_mirror or (Path(package.source_url.removeprefix("file://")) if local_repository else self.package_dir / hashlib.sha256(checkout_key.encode()).hexdigest()[:16])
        if not local_repository and not (checkout / ".git").exists():
            temporary = Path(tempfile.mkdtemp(prefix=f".{checkout.name}-", dir=self.package_dir))
            shutil.rmtree(temporary)
            clone_args = ["git", "clone", "--depth", "1"]
            if package.revision:
                clone_args.extend(["--branch", package.revision])
            clone_args.extend([package.source_url, str(temporary)])
            _run(*clone_args)
            try:
                temporary.rename(checkout)
            except FileExistsError:
                shutil.rmtree(temporary, ignore_errors=True)
        if not local_repository and checkout not in self._updated_checkouts:
            _run("git", "fetch", "origin", package.revision or "HEAD", cwd=checkout)
            _run("git", "reset", "--hard", "FETCH_HEAD", cwd=checkout)
            self._updated_checkouts.add(checkout)
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
            # Refresh callers only need the package loaded. Building a full payload
            # here would re-hash every CAD file once per root package.
            return self._package_payload(package)

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
                    semantic_path=f"{package.path.removeprefix('//pub/') if not self._is_private_path(package.path) else package.path.removeprefix('//')}:{name}",
                    license=str(license_name) if license_name else None,
                )
                self._object_roots[object_id] = root

    def package_detail(self, package_id: str, include_private: bool = False) -> dict[str, Any]:
        package = self._packages[package_id]
        if self._is_private_path(package.path) and not include_private:
            raise KeyError(package_id)
        objects = [self._object_payload(item) for item in self.objects if item.package_id == package_id]
        return {**self._package_payload(package), "objects": objects}

    def catalog(self, include_private: bool = False) -> dict[str, Any]:
        categories: dict[str, list[dict[str, Any]]] = {}
        for package in self.packages:
            if self._is_private_path(package.path) and not include_private:
                continue
            categories.setdefault(package.category, []).append(self._package_payload(package))
        visible_objects = [item for item in self.objects if include_private or not self._is_private_path(item.package_path)]
        return {
            "name": "NarysAI Registry",
            "package_count": sum(len(items) for items in categories.values()),
            "object_count": len(visible_objects),
            "categories": [{"name": name, "packages": items} for name, items in sorted(categories.items())],
            "featured": [self._object_payload(item) for item in visible_objects[:12]],
        }

    def search(self, query: str, include_private: bool = False) -> list[dict[str, Any]]:
        needle = query.casefold().strip()
        values: list[dict[str, Any]] = []
        for package in self.packages:
            if self._is_private_path(package.path) and not include_private:
                continue
            if needle in f"{package.name} {package.description} {package.path}".casefold():
                values.append({"result_type": "package", **self._package_payload(package)})
        for item in self.objects:
            if self._is_private_path(item.package_path) and not include_private:
                continue
            if needle in f"{item.name} {item.description} {item.package_path}".casefold():
                values.append({"result_type": "object", **self._object_payload(item)})
        return values[:100]

    def object_detail(self, object_id: str, include_private: bool = False) -> dict[str, Any]:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        if self._is_private_path(item.package_path) and not include_private:
            raise KeyError(object_id)
        return self._object_payload(item)

    def object_by_path(self, kind: str, semantic_path: str, include_private: bool = False) -> dict[str, Any]:
        normalized_kind = kind.casefold().removesuffix("s")
        for item in self._objects.values():
            if item.kind == normalized_kind and item.semantic_path == semantic_path:
                if self._is_private_path(item.package_path) and not include_private:
                    break
                return self._object_payload(item)
        raise KeyError(f"{kind}/{semantic_path}")

    def source_file(self, object_id: str) -> Path:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        root = self._object_roots.get(object_id)
        if not root or not item.source_path:
            raise CatalogError("This object is generated and has no standalone source file")
        source = (root / item.source_path).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file():
            raise CatalogError(f"Source model is unavailable: {item.source_path}")
        return source

    def package_archive(self, package_id: str) -> Path:
        package = self._packages.get(package_id)
        if not package:
            raise KeyError(package_id)
        checkout_key = f"{package.source_url}@{package.revision or 'HEAD'}"
        checkout = self.package_dir / hashlib.sha256(checkout_key.encode()).hexdigest()[:16]
        requested = checkout / package.rel_path if package.rel_path else checkout
        root = requested if requested.is_dir() else checkout
        if not root.is_dir():
            raise CatalogError("The local package checkout is unavailable")
        output = self.preview_dir / f"package-{package_id}.zip"
        if output.exists():
            return output
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in root.rglob("*"):
                if path.is_file() and ".git" not in path.parts:
                    archive.write(path, Path(package.name) / path.relative_to(root))
        return output

    def preview(self, object_id: str) -> Path:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        root = self._object_roots.get(object_id)
        if not root or not item.source_path:
            raise CatalogError("This object does not expose a directly convertible source file")
        source = (root / item.source_path).resolve()
        if not source.is_relative_to(root.resolve()) or not source.exists():
            raise CatalogError(f"Source model is unavailable: {item.source_path}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        output = self.preview_dir / f"{object_id}-{digest}.glb"
        if output.exists():
            return output
        try:
            render_source = source
            if source.suffix.casefold() == ".scad":
                render_source = self.preview_dir / f"{object_id}-{digest}.stl"
                if not render_source.exists():
                    result = subprocess.run(
                        ["openscad", "-o", str(render_source), str(source)],
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                    if result.returncode:
                        raise CatalogError(result.stderr.strip() or "OpenSCAD conversion failed")
            mesh = trimesh.load(render_source, force="scene")
            mesh.export(output, file_type="glb")
        except Exception as exc:
            raise CatalogError(f"Preview conversion failed: {exc}") from exc
        return output

    def thumbnail(self, object_id: str) -> Path:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        preview = self.preview(object_id)
        output = self.preview_dir / f"{preview.stem}-v2.png"
        if not output.exists():
            try:
                scene = trimesh.load(preview, force="scene")
                vertices: list = []
                faces: list = []
                offset = 0
                for geometry in scene.geometry.values():
                    if not isinstance(geometry, trimesh.Trimesh) or not len(geometry.vertices):
                        continue
                    vertices.extend(geometry.vertices.tolist())
                    faces.extend((geometry.faces + offset).tolist())
                    offset += len(geometry.vertices)
                self._draw_mesh_thumbnail(vertices, faces, output)
            except Exception:
                image = Image.new("RGB", (960, 600), "#101a18")
                draw = ImageDraw.Draw(image)
                draw.rounded_rectangle((110, 90, 850, 510), radius=48, fill="#172824", outline="#6ee7b7", width=4)
                draw.text((160, 150), "NarysAI", fill="#6ee7b7", font_size=42)
                draw.text((160, 260), item.name[:34], fill="#f1f5f3", font_size=44)
                draw.text((160, 340), f"{item.kind.upper()} · {item.source_type.upper()}", fill="#9fb4ae", font_size=25)
                image.save(output)
        return output

    @staticmethod
    def _draw_mesh_thumbnail(vertices: list, faces: list, output: Path) -> None:
        import numpy as np

        points = np.asarray(vertices, dtype=float)
        triangles = np.asarray(faces, dtype=int)
        if not len(points) or not len(triangles):
            raise CatalogError("Preview has no mesh geometry")
        points -= (points.min(axis=0) + points.max(axis=0)) / 2
        yaw, pitch = np.deg2rad(35), np.deg2rad(25)
        rotation_y = np.array([[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
        rotation_x = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
        points = points @ rotation_y.T @ rotation_x.T
        xy = points[:, :2]
        scale = 440 / max(float(np.ptp(xy, axis=0).max()), 1e-9)
        xy = xy * scale + np.array([480, 300])
        image = Image.new("RGB", (960, 600), "#101a18")
        draw = ImageDraw.Draw(image)
        order = np.argsort(points[triangles].mean(axis=1)[:, 2])
        step = max(1, len(order) // 18000)
        light = np.array([0.35, -0.45, 0.82])
        for face_index in order[::step]:
            face = triangles[face_index]
            polygon = points[face]
            normal = np.cross(polygon[1] - polygon[0], polygon[2] - polygon[0])
            length = np.linalg.norm(normal)
            shade = 0.45 if length == 0 else 0.42 + 0.50 * abs(float(np.dot(normal / length, light)))
            color = tuple(int(channel * shade) for channel in (83, 232, 176))
            draw.polygon([tuple(xy[index]) for index in face], fill=color, outline="#183e33")
        image.save(output)
