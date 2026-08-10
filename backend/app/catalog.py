from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
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


SCAD_MATERIAL_PATTERN = re.compile(
    r"^\s*//\s*NARYS_MATERIAL:\s*([A-Za-z0-9_-]+)\s*=\s*(#[0-9A-Fa-f]{6})\s*$",
    re.MULTILINE,
)
SCAD_PARAMETER_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def scad_materials(source: Path) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Read opt-in material declarations used for color-preserving SCAD previews."""
    text = source.read_text(encoding="utf-8")
    materials: list[tuple[str, tuple[int, int, int, int]]] = []
    for name, color in SCAD_MATERIAL_PATTERN.findall(text):
        rgb = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
        materials.append((name, (*rgb, 255)))
    return materials


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
    entry_type: str = "package"
    access: str | None = None
    canonical_repo_url: str | None = None
    contribution_url: str | None = None
    issues_url: str | None = None
    default_branch: str = "main"
    current_drawing: str | None = None
    pub_url: str | None = None


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
    model_role: str | None = None
    spec_json: str = "{}"


SKETCH_PREVIEW_THICKNESS = 0.08
SKETCH_PREVIEW_COLOR = (110, 231, 183, 255)


def _shape_value(value: Any, key: str, fallback: float = 0.0) -> float:
    if isinstance(value, dict):
        value = value.get(key, fallback)
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _convex_profile_mesh(points: list[tuple[float, float]], thickness: float = SKETCH_PREVIEW_THICKNESS) -> trimesh.Trimesh:
    """Extrude a counter-clockwise convex 2D profile without optional CAD engines."""
    if len(points) < 3:
        raise CatalogError("A generated sketch preview needs at least three profile points")
    half = thickness / 2.0
    count = len(points)
    vertices = [(x, y, -half) for x, y in points] + [(x, y, half) for x, y in points]
    faces: list[tuple[int, int, int]] = []
    for index in range(1, count - 1):
        faces.append((0, index + 1, index))
        faces.append((count, count + index, count + index + 1))
    for index in range(count):
        next_index = (index + 1) % count
        faces.append((index, next_index, count + next_index))
        faces.append((index, count + next_index, count + index))
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.visual.face_colors = SKETCH_PREVIEW_COLOR
    return mesh


def _basic_sketch_mesh(spec: dict[str, Any]) -> trimesh.Trimesh:
    if "circle" in spec:
        circle = spec["circle"]
        radius = _shape_value(circle, "radius")
        x = _shape_value(circle, "x") if isinstance(circle, dict) else 0.0
        y = _shape_value(circle, "y") if isinstance(circle, dict) else 0.0
        if radius <= 0:
            raise CatalogError("Basic circle preview requires a positive radius")
        points = [
            (x + radius * math.cos(angle), y + radius * math.sin(angle))
            for angle in (2.0 * math.pi * index / 64 for index in range(64))
        ]
        return _convex_profile_mesh(points)
    if "square" in spec:
        square = spec["square"]
        side = _shape_value(square, "side")
        x = _shape_value(square, "x") if isinstance(square, dict) else 0.0
        y = _shape_value(square, "y") if isinstance(square, dict) else 0.0
        side_x = side_y = side
    elif "rectangle" in spec:
        rectangle = spec["rectangle"]
        side_x = _shape_value(rectangle, "side-x")
        side_y = _shape_value(rectangle, "side-y")
        x = _shape_value(rectangle, "x")
        y = _shape_value(rectangle, "y")
    else:
        raise CatalogError("Basic sketch preview has no supported outer shape")
    if side_x <= 0 or side_y <= 0:
        raise CatalogError("Basic rectangular preview requires positive dimensions")
    half_x, half_y = side_x / 2.0, side_y / 2.0
    return _convex_profile_mesh([
        (x - half_x, y - half_y),
        (x + half_x, y - half_y),
        (x + half_x, y + half_y),
        (x - half_x, y + half_y),
    ])


def _coerce_parameter(name: str, declaration: dict[str, Any], value: Any) -> bool | int | float | str:
    parameter_type = str(declaration.get("type", "float")).casefold()
    try:
        if parameter_type == "float":
            converted: bool | int | float | str = float(value)
            if not math.isfinite(converted):
                raise ValueError
        elif parameter_type == "int":
            numeric = float(value)
            if not math.isfinite(numeric) or not numeric.is_integer():
                raise ValueError
            converted = int(numeric)
        elif parameter_type == "bool":
            if isinstance(value, bool):
                converted = value
            elif str(value).casefold() in {"true", "1"}:
                converted = True
            elif str(value).casefold() in {"false", "0"}:
                converted = False
            else:
                raise ValueError
        elif parameter_type in {"str", "string"}:
            converted = str(value)
        else:
            raise CatalogError(f"Unsupported parameter type for {name}: {parameter_type}")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CatalogError(f"Invalid value for parameter {name}") from exc
    if isinstance(converted, (int, float)) and not isinstance(converted, bool):
        if "min" in declaration and converted < float(declaration["min"]):
            raise CatalogError(f"Parameter {name} must be at least {declaration['min']}")
        if "max" in declaration and converted > float(declaration["max"]):
            raise CatalogError(f"Parameter {name} must be at most {declaration['max']}")
    return converted


def _scad_literal(value: bool | int | float | str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


def _is_bounded_numeric_parameter(declaration: Any) -> bool:
    if not isinstance(declaration, dict) or str(declaration.get("type", "")).casefold() not in {"float", "int"}:
        return False
    if not all(key in declaration for key in ("default", "min", "max")):
        return False
    try:
        values = [float(declaration[key]) for key in ("default", "min", "max")]
    except (TypeError, ValueError, OverflowError):
        return False
    if not all(math.isfinite(value) for value in values) or not values[1] <= values[0] <= values[2]:
        return False
    return str(declaration.get("type", "")).casefold() != "int" or all(value.is_integer() for value in values)


def _configurable_scad_parameters(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = spec.get("narys") if isinstance(spec.get("narys"), dict) else {}
    raw_options = metadata.get("parameter_options", {}) if isinstance(metadata, dict) else {}
    hidden_parameters = {
        str(name) for name in metadata.get("hidden_parameters", [])
    } if isinstance(metadata.get("hidden_parameters", []), list) else set()
    raw_parameters = spec.get("parameters")
    if not isinstance(raw_parameters, dict) or not isinstance(raw_options, dict):
        return {}
    parameters: dict[str, dict[str, Any]] = {}
    for raw_name, raw_declaration in raw_parameters.items():
        name = str(raw_name)
        options = raw_options.get(name)
        if (
            not SCAD_PARAMETER_NAME_PATTERN.fullmatch(name)
            or not _is_bounded_numeric_parameter(raw_declaration)
            or not isinstance(options, list)
            or not 1 <= len(options) <= 100
        ):
            continue
        try:
            normalized_options = [
                _coerce_parameter(name, raw_declaration, option)
                for option in options
            ]
            default = _coerce_parameter(name, raw_declaration, raw_declaration["default"])
        except CatalogError:
            continue
        normalized_options = list(dict.fromkeys(normalized_options))
        if default not in normalized_options:
            continue
        parameter_type = str(raw_declaration.get("type", "float")).casefold()
        declaration: dict[str, Any] = {
            "type": parameter_type,
            "default": default,
            "min": int(raw_declaration["min"]) if parameter_type == "int" else float(raw_declaration["min"]),
            "max": int(raw_declaration["max"]) if parameter_type == "int" else float(raw_declaration["max"]),
            "options": normalized_options,
            "hidden": name in hidden_parameters,
        }
        parameters[name] = declaration
    return parameters


def _token(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, **(env or {})},
    )
    if result.returncode:
        raise CatalogError((result.stderr or result.stdout).strip())


class CatalogService:
    def __init__(
        self,
        index_url: str,
        index_ref: str,
        cache_dir: Path,
        private_repo_dir: Path | None = None,
        public_repo_dir: Path | None = None,
        index_dir: Path | None = None,
        github_token_file: Path | None = None,
    ):
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
        self.github_token_file = github_token_file
        self.git_askpass = cache_dir / ".git-askpass.sh"
        self._packages: dict[str, Package] = {}
        self._objects: dict[str, CatalogObject] = {}
        self._object_roots: dict[str, Path] = {}
        self._lock = threading.RLock()
        self._preview_lock = threading.Lock()
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
        private = self._is_private_path(package.path) or package.access == "private"
        return {
            **asdict(package),
            "namespace": "//private" if private else "//pub",
            "visibility": "private" if private else "public",
            "repository": "indra" if private else "git" if package.entry_type == "project" else "PUB",
            "git_commit": package.revision or package.default_branch,
            "upstream_url": package.canonical_repo_url or package.source_url,
            "license_status": "unverified",
        }

    def _object_payload(self, item: CatalogObject) -> dict[str, Any]:
        package = self._packages.get(item.package_id)
        private = self._is_private_path(item.package_path) or package is not None and package.access == "private"
        project = package is not None and package.entry_type == "project"
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
        item_payload = asdict(item)
        item_payload.pop("spec_json", None)
        configuration = self._object_configuration(item)
        return {
            **item_payload,
            **configuration,
            "namespace": "//private" if private else "//pub",
            "visibility": "private" if private else "public",
            "repository": "indra" if private else "git" if project else "PUB",
            "git_path": item.source_path if project else "/".join(filter(None, (package_relative, item.source_path))),
            "git_commit": package.revision or package.default_branch if package else "main",
            "upstream_url": package.canonical_repo_url if package and package.canonical_repo_url else item.source_url,
            "entry_type": package.entry_type if package else "package",
            "canonical_repo_url": package.canonical_repo_url if package else None,
            "default_branch": package.default_branch if package else "main",
            "checksum": checksum,
            "size": size,
            "license_status": "verified" if item.license else "unverified",
        }

    @staticmethod
    def _object_configuration(item: CatalogObject) -> dict[str, Any]:
        if item.source_type.casefold() != "scad":
            return {}
        try:
            spec = json.loads(item.spec_json or "{}")
        except json.JSONDecodeError:
            return {}
        metadata = spec.get("narys") if isinstance(spec.get("narys"), dict) else {}
        parameters = _configurable_scad_parameters(spec)
        if not parameters:
            return {}
        raw_presets = metadata.get("presets", {}) if isinstance(metadata, dict) else {}
        presets: list[dict[str, Any]] = []
        linked_parameters = {
            str(name)
            for name in metadata.get("hidden_parameters", [])
            if str(name) in parameters and len(parameters[str(name)]["options"]) > 1
        } if isinstance(metadata.get("hidden_parameters", []), list) else set()
        if isinstance(raw_presets, dict):
            for preset_id, raw_preset in raw_presets.items():
                if not isinstance(raw_preset, dict):
                    continue
                raw_values = raw_preset.get("parameters", {})
                if not isinstance(raw_values, dict):
                    continue
                values: dict[str, bool | int | float | str] = {}
                valid = True
                for raw_name, raw_value in raw_values.items():
                    name = str(raw_name)
                    declaration = parameters.get(name)
                    if not declaration:
                        continue
                    try:
                        value = _coerce_parameter(name, declaration, raw_value)
                    except CatalogError:
                        valid = False
                        break
                    if value not in declaration["options"]:
                        valid = False
                        break
                    values[name] = value
                if valid and values and linked_parameters.issubset(values):
                    presets.append({
                        "id": str(preset_id),
                        "label": str(raw_preset.get("label", preset_id)),
                        "parameters": values,
                    })
        preset_ids = {preset["id"] for preset in presets}
        default_preset = metadata.get("default_preset") if isinstance(metadata, dict) else None
        default_preset = str(default_preset) if str(default_preset) in preset_ids else None
        return {
            "parameters": parameters,
            "parameter_presets": presets,
            "default_parameter_preset": default_preset,
        }

    @staticmethod
    def _resolved_scad_parameters(
        spec: dict[str, Any],
        overrides: dict[str, str],
    ) -> dict[str, bool | int | float | str]:
        configurable = _configurable_scad_parameters(spec)
        if len(overrides) > 32:
            raise CatalogError("Too many preview parameters")
        unknown = sorted(set(overrides) - set(configurable))
        if unknown:
            raise CatalogError(f"Unknown preview parameter: {unknown[0]}")
        resolved: dict[str, bool | int | float | str] = {}
        for raw_name, raw_declaration in configurable.items():
            name = str(raw_name)
            if not SCAD_PARAMETER_NAME_PATTERN.fullmatch(name) or not isinstance(raw_declaration, dict):
                continue
            if name in overrides:
                value = _coerce_parameter(name, raw_declaration, overrides[name])
                if value not in raw_declaration["options"]:
                    raise CatalogError(f"Unsupported value for parameter {name}")
                resolved[name] = value
            elif "default" in raw_declaration:
                resolved[name] = _coerce_parameter(name, raw_declaration, raw_declaration["default"])
        metadata = spec.get("narys") if isinstance(spec.get("narys"), dict) else {}
        hidden = {
            str(name)
            for name in metadata.get("hidden_parameters", [])
            if str(name) in configurable and len(configurable[str(name)]["options"]) > 1
        } if isinstance(metadata.get("hidden_parameters", []), list) else set()
        raw_presets = metadata.get("presets", {}) if isinstance(metadata, dict) else {}
        if hidden and isinstance(raw_presets, dict):
            matches_preset = False
            for raw_preset in raw_presets.values():
                values = raw_preset.get("parameters", {}) if isinstance(raw_preset, dict) else {}
                if not isinstance(values, dict) or not hidden.issubset(values):
                    continue
                try:
                    matches_preset = all(
                        _coerce_parameter(name, configurable[name], values[name]) == resolved[name]
                        for name in hidden
                    )
                except CatalogError:
                    matches_preset = False
                if matches_preset:
                    break
            if not matches_preset:
                raise CatalogError("Thread dimensions must match a declared preset")
        return resolved

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
                    rel_path TEXT, revision TEXT, category TEXT NOT NULL, status TEXT NOT NULL,
                    entry_type TEXT NOT NULL DEFAULT 'package', access TEXT,
                    canonical_repo_url TEXT, contribution_url TEXT, issues_url TEXT,
                    default_branch TEXT NOT NULL DEFAULT 'main', current_drawing TEXT,
                    pub_url TEXT
                )"""
            )
            package_columns = {row[1] for row in connection.execute("PRAGMA table_info(packages)")}
            package_migrations = {
                "revision": "TEXT",
                "entry_type": "TEXT NOT NULL DEFAULT 'package'",
                "access": "TEXT",
                "canonical_repo_url": "TEXT",
                "contribution_url": "TEXT",
                "issues_url": "TEXT",
                "default_branch": "TEXT NOT NULL DEFAULT 'main'",
                "current_drawing": "TEXT",
                "pub_url": "TEXT",
            }
            for column, declaration in package_migrations.items():
                if column not in package_columns:
                    connection.execute(f"ALTER TABLE packages ADD COLUMN {column} {declaration}")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS objects (
                    id TEXT PRIMARY KEY, package_id TEXT NOT NULL, package_path TEXT NOT NULL,
                    name TEXT NOT NULL, kind TEXT NOT NULL, description TEXT NOT NULL,
                    source_type TEXT NOT NULL, source_path TEXT, source_url TEXT NOT NULL,
                    semantic_path TEXT NOT NULL, license TEXT, model_role TEXT,
                    spec_json TEXT NOT NULL DEFAULT '{}', object_root TEXT,
                    FOREIGN KEY(package_id) REFERENCES packages(id)
                )"""
            )
            object_columns = {row[1] for row in connection.execute("PRAGMA table_info(objects)")}
            if "model_role" not in object_columns:
                connection.execute("ALTER TABLE objects ADD COLUMN model_role TEXT")
            if "spec_json" not in object_columns:
                connection.execute("ALTER TABLE objects ADD COLUMN spec_json TEXT NOT NULL DEFAULT '{}'")
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
                (id,path,name,description,source_url,web_url,rel_path,revision,category,status,
                 entry_type,access,canonical_repo_url,contribution_url,issues_url,
                 default_branch,current_drawing,pub_url)
                VALUES (:id,:path,:name,:description,:source_url,:web_url,:rel_path,:revision,:category,:status,
                 :entry_type,:access,:canonical_repo_url,:contribution_url,:issues_url,
                 :default_branch,:current_drawing,:pub_url)""",
                [asdict(package) for package in self.packages],
            )
            rows = []
            for item in self.objects:
                row = asdict(item)
                row["object_root"] = str(self._object_roots.get(item.id, ""))
                rows.append(row)
            connection.executemany(
                """INSERT INTO objects (
                    id,package_id,package_path,name,kind,description,source_type,
                    source_path,source_url,semantic_path,license,model_role,spec_json,object_root
                ) VALUES (
                    :id,:package_id,:package_path,:name,:kind,:description,:source_type,
                    :source_path,:source_url,:semantic_path,:license,:model_role,:spec_json,:object_root
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
            _run("git", "fetch", "origin", self.index_ref, cwd=self.index_dir, env=self._git_environment())
            _run("git", "reset", "--hard", "FETCH_HEAD", cwd=self.index_dir, env=self._git_environment())
        else:
            if self.index_dir.exists():
                shutil.rmtree(self.index_dir)
            _run(
                "git", "clone", "--depth", "1", "--branch", self.index_ref,
                self.index_url, str(self.index_dir), env=self._git_environment()
            )

    def _git_environment(self) -> dict[str, str]:
        environment = {"GIT_TERMINAL_PROMPT": "0"}
        if not self.github_token_file or not self.github_token_file.is_file():
            return environment
        token = self.github_token_file.read_text(encoding="utf-8").strip()
        if not token:
            return environment
        if not self.git_askpass.exists():
            self.git_askpass.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  *Username*) printf '%s\\n' \"$GIT_USERNAME\" ;;\n"
                "  *) printf '%s\\n' \"$GIT_PASSWORD\" ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            self.git_askpass.chmod(0o700)
        return {
            **environment,
            "GIT_ASKPASS": str(self.git_askpass),
            "GIT_USERNAME": "x-access-token",
            "GIT_PASSWORD": token,
        }

    @staticmethod
    def _project_metadata(data: dict[str, Any]) -> dict[str, Any]:
        metadata = data.get("narys_project", {})
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def _package_project_fields(cls, data: dict[str, Any], default_access: str) -> dict[str, Any]:
        metadata = cls._project_metadata(data)
        kind = str(metadata.get("kind", "package"))
        return {
            "entry_type": "project" if kind == "project" else "package",
            "access": str(metadata.get("access", default_access)),
            "canonical_repo_url": metadata.get("canonical_repo"),
            "contribution_url": metadata.get("contribution_url"),
            "issues_url": metadata.get("issues_url"),
            "default_branch": str(metadata.get("default_branch", "main")),
            "current_drawing": metadata.get("current_drawing"),
            "pub_url": metadata.get("pub_url"),
        }

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
                project_fields = self._package_project_fields(spec, "public")
                self._packages[package_id] = Package(
                    id=package_id,
                    path=path,
                    name=str(spec.get("display_name", name)),
                    description=str(spec.get("desc", "PartCAD package")),
                    source_url=str(spec["url"]),
                    web_url=spec.get("web"),
                    rel_path=spec.get("relPath"),
                    revision=spec.get("revision"),
                    category=relative.parts[0] if relative.parts else "root",
                    **project_fields,
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
            if not isinstance(spec, dict):
                continue
            is_git = spec.get("type") == "git" and spec.get("url")
            if not is_git and not spec.get("path"):
                continue
            relative = str(spec.get("catalog_path") or spec.get("path") or name).strip("/")
            package_path = f"//private/{relative}"
            package_id = _token(package_path)
            project_fields = self._package_project_fields(spec, "private")
            if is_git and project_fields["entry_type"] == "package":
                project_fields["entry_type"] = "project"
            project_fields["access"] = "private"
            self._packages[package_id] = Package(
                id=package_id,
                path=package_path,
                name=str(spec.get("display_name", name)),
                description=str(spec.get("desc", "Private NarysAI package")),
                source_url=str(spec["url"]) if is_git else self.private_repo_dir.as_uri(),
                web_url=spec.get("web"),
                rel_path=spec.get("relPath") if is_git else relative,
                revision=str(spec.get("revision", "main")),
                category=str(spec.get("category", "private")),
                **project_fields,
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
            _run(*clone_args, env=self._git_environment())
            try:
                temporary.rename(checkout)
            except FileExistsError:
                shutil.rmtree(temporary, ignore_errors=True)
        if not local_repository and checkout not in self._updated_checkouts:
            _run("git", "fetch", "origin", package.revision or "HEAD", cwd=checkout, env=self._git_environment())
            _run("git", "reset", "--hard", "FETCH_HEAD", cwd=checkout, env=self._git_environment())
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
                    metadata = self._package_project_fields(data, package.access or "public")
                    if metadata["entry_type"] == "project":
                        for field, value in metadata.items():
                            if value is not None:
                                setattr(current_package, field, value)
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
                        access=package.access,
                        entry_type=package.entry_type,
                        canonical_repo_url=package.canonical_repo_url,
                        contribution_url=package.contribution_url,
                        issues_url=package.issues_url,
                        default_branch=package.default_branch,
                        current_drawing=package.current_drawing,
                        pub_url=package.pub_url,
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
                default_ext = "FCStd" if source_type == "freecad" else "3mf" if source_type == "3mf" else source_type
                source_path = spec.get("path") or (
                    f"{name}.{default_ext}" if source_type not in {"native", "ai", "basic"} else None
                )
                model_role = str(spec["model_role"]) if spec.get("model_role") else None
                self._validate_model_role(name, source_type, str(source_path) if source_path else None, model_role)
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
                    model_role=model_role,
                    spec_json=json.dumps(spec, sort_keys=True, separators=(",", ":")),
                )
                self._object_roots[object_id] = root

    @staticmethod
    def _validate_model_role(name: str, source_type: str, source_path: str | None, model_role: str | None) -> None:
        # Released objects without a role remain readable until controlled migration.
        if model_role is None:
            return
        suffix = Path(source_path or "").suffix
        if model_role == "electronic_component":
            if source_type.casefold() != "scad" or suffix != ".scad":
                raise CatalogError(f"{name}: electronic_component requires exactly one .scad source")
            return
        if model_role == "printable_part":
            if source_type.casefold() != "freecad" or suffix != ".FCStd":
                raise CatalogError(f"{name}: printable_part requires exactly one .FCStd source with type: freecad")
            return
        raise CatalogError(f"{name}: unsupported model_role: {model_role}")

    def package_detail(self, package_id: str, include_private: bool = False) -> dict[str, Any]:
        package = self._packages[package_id]
        if self._is_private_path(package.path) and not include_private:
            raise KeyError(package_id)
        objects = [self._object_payload(item) for item in self.objects if item.package_id == package_id]
        return {**self._package_payload(package), "objects": objects}

    def catalog(self, include_private: bool = False) -> dict[str, Any]:
        categories: dict[str, list[dict[str, Any]]] = {}
        populated_package_ids = {item.package_id for item in self.objects}
        for package in self.packages:
            if self._is_private_path(package.path) and not include_private:
                continue
            if package.entry_type != "project" and package.id not in populated_package_ids:
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
        populated_package_ids = {item.package_id for item in self.objects}
        for package in self.packages:
            if self._is_private_path(package.path) and not include_private:
                continue
            if package.entry_type != "project" and package.id not in populated_package_ids:
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

    def _generated_sketch_preview(
        self,
        item: CatalogObject,
        spec: dict[str, Any],
    ) -> Path:
        digest_builder = hashlib.sha256(item.spec_json.encode())
        digest = digest_builder.hexdigest()[:16]
        output = self.preview_dir / f"{item.id}-{digest}.glb"
        if output.exists():
            return output
        if item.source_type.casefold() == "basic":
            mesh = _basic_sketch_mesh(spec)
        else:
            raise CatalogError(f"No generated sketch preview is available for {item.source_type}")
        scene = trimesh.Scene()
        scene.add_geometry(mesh, geom_name=item.name, node_name=item.name)
        scene.export(output, file_type="glb")
        return output

    def preview(self, object_id: str, overrides: dict[str, str] | None = None) -> Path:
        with self._preview_lock:
            return self._preview_unlocked(object_id, overrides)

    def _preview_unlocked(self, object_id: str, overrides: dict[str, str] | None = None) -> Path:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        overrides = overrides or {}
        try:
            spec = json.loads(item.spec_json or "{}")
        except json.JSONDecodeError as exc:
            raise CatalogError(f"Invalid stored object specification for {item.name}") from exc
        if item.kind == "sketch" and item.source_type.casefold() == "basic":
            if overrides:
                raise CatalogError("This generated sketch does not support preview parameters")
            return self._generated_sketch_preview(item, spec)
        root = self._object_roots.get(object_id)
        if not root or not item.source_path:
            raise CatalogError("This object does not expose a directly convertible source file")
        source = (root / item.source_path).resolve()
        if not source.is_relative_to(root.resolve()) or not source.exists():
            raise CatalogError(f"Source model is unavailable: {item.source_path}")
        if overrides and source.suffix.casefold() != ".scad":
            raise CatalogError("Preview parameters are currently supported for OpenSCAD objects")
        resolved_parameters = (
            self._resolved_scad_parameters(spec, overrides)
            if source.suffix.casefold() == ".scad"
            else {}
        )
        digest_builder = hashlib.sha256(source.read_bytes())
        digest_builder.update(json.dumps(resolved_parameters, sort_keys=True, separators=(",", ":")).encode())
        digest = digest_builder.hexdigest()[:16]
        output = self.preview_dir / f"{object_id}-{digest}.glb"
        if output.exists():
            return output
        try:
            render_source = source
            if source.suffix.casefold() == ".scad":
                parameter_args = [
                    argument
                    for name, value in sorted(resolved_parameters.items())
                    for argument in ("-D", f"{name}={_scad_literal(value)}")
                ]
                materials = scad_materials(source)
                if materials:
                    scene = trimesh.Scene()
                    for name, color in materials:
                        material_source = self.preview_dir / f"{object_id}-{digest}-{name}.stl"
                        if not material_source.exists():
                            result = subprocess.run(
                                [
                                    "openscad",
                                    *parameter_args,
                                    "-D",
                                    f'narys_material="{name}"',
                                    "-o",
                                    str(material_source),
                                    str(source),
                                ],
                                capture_output=True,
                                text=True,
                                timeout=180,
                            )
                            if result.returncode:
                                raise CatalogError(result.stderr.strip() or "OpenSCAD conversion failed")
                        geometry = trimesh.load(material_source, force="mesh")
                        if isinstance(geometry, trimesh.Trimesh) and len(geometry.faces):
                            geometry.visual = trimesh.visual.ColorVisuals(
                                mesh=geometry,
                                face_colors=color,
                            )
                            scene.add_geometry(geometry, geom_name=name, node_name=name)
                    if not scene.geometry:
                        raise CatalogError("OpenSCAD material preview produced no geometry")
                    scene.export(output, file_type="glb")
                    return output
                render_source = self.preview_dir / f"{object_id}-{digest}.stl"
                if not render_source.exists():
                    result = subprocess.run(
                        ["openscad", *parameter_args, "-o", str(render_source), str(source)],
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                    if result.returncode:
                        raise CatalogError(result.stderr.strip() or "OpenSCAD conversion failed")
            elif source.suffix.casefold() == ".fcstd":
                render_source = self.preview_dir / f"{object_id}-{digest}.stl"
                if not render_source.exists():
                    result = subprocess.run(
                        ["/usr/bin/python3", "/app/app/freecad_export.py", str(source), str(render_source)],
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                    if result.returncode:
                        raise CatalogError(result.stderr.strip() or "FreeCAD conversion failed")
            mesh = trimesh.load(render_source, force="scene")
            mesh.export(output, file_type="glb")
        except Exception as exc:
            raise CatalogError(f"Preview conversion failed: {exc}") from exc
        return output

    def _release_thumbnail(self, object_id: str) -> Path | None:
        """Return a checked-in PNG next to the versioned CAD release, if present."""
        item = self._objects.get(object_id)
        root = self._object_roots.get(object_id)
        if not item or not root or not item.source_path:
            return None
        root = root.resolve()
        source = (root / item.source_path).resolve()
        if not source.is_relative_to(root):
            return None
        candidates = (
            source.with_suffix(".png"),
            source.parent.parent / f"{source.stem}.png",
            root / f"{source.stem}.png",
        )
        for candidate in candidates:
            candidate = candidate.resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                try:
                    with Image.open(candidate) as image:
                        if image.format == "PNG":
                            return candidate
                except OSError:
                    continue
        return None

    def thumbnail(self, object_id: str) -> Path:
        item = self._objects.get(object_id)
        if not item:
            raise KeyError(object_id)
        release_thumbnail = self._release_thumbnail(object_id)
        if release_thumbnail is not None:
            return release_thumbnail
        output = self.preview_dir / f"{object_id}-fallback-v2.png"
        try:
            preview = self.preview(object_id)
            output = self.preview_dir / f"{preview.stem}-v2.png"
            if not output.exists():
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
            if not output.exists():
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
