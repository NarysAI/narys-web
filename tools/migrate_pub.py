"""Materialize the public PartCAD registry into the NarysAI/PUB monorepository."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

MAX_FILE_SIZE = 100 * 1024 * 1024
IGNORED = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def revision(root: Path, fallback: str | None) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return fallback or "unknown"


def roots_from_index(index: Path) -> list[str]:
    paths: list[str] = []
    for config in index.rglob("partcad.yaml"):
        category = config.parent.relative_to(index).as_posix()
        if category == ".":
            category = ""
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        imports = data.get("import", {}) | data.get("dependencies", {})
        if not isinstance(imports, dict):
            continue
        for name, spec in imports.items():
            if isinstance(spec, dict) and spec.get("type") == "git" and spec.get("url"):
                paths.append("/".join(filter(None, ("//pub", category, str(name)))))
    return sorted(set(paths))


def copy_package(source: Path, destination: Path) -> tuple[dict[str, str], list[str]]:
    checksums: dict[str, str] = {}
    blocked: list[str] = []
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if any(part in IGNORED for part in relative.parts):
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if path.stat().st_size > MAX_FILE_SIZE:
            blocked.append(relative.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        checksums[relative.as_posix()] = sha256(path)
    return checksums, blocked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    packages = {row["path"]: row for row in connection.execute("SELECT * FROM packages")}
    object_roots: dict[str, str] = {}
    for row in connection.execute("SELECT package_path, object_root FROM objects WHERE object_root IS NOT NULL"):
        object_roots.setdefault(row["package_path"], row["object_root"])

    report: dict[str, list] = {"migrated": [], "blocked": [], "missing": []}
    for package_path in roots_from_index(args.index):
        row = packages.get(package_path)
        old_root = object_roots.get(package_path)
        if not old_root:
            old_root = next(
                (root for path, root in object_roots.items() if path.startswith(package_path + "/")), None
            )
        if not row:
            report["missing"].append(package_path)
            continue
        source: Path | None = None
        if old_root:
            marker = "/packages/"
            normalized = old_root.replace("\\", "/")
            if marker in normalized:
                checkout_relative = normalized.split(marker, 1)[1].split("/", 1)[0]
                checkout = args.packages / checkout_relative
                source = checkout / row["rel_path"] if row["rel_path"] else checkout
                if source.is_file():
                    source = source.parent
        if source is None or not source.is_dir():
            clone_dir = Path(tempfile.mkdtemp(prefix="narys-migrate-"))
            try:
                subprocess.run(["git", "clone", "--filter=blob:none", row["source_url"], str(clone_dir)], check=True)
                if row["revision"]:
                    subprocess.run(["git", "-C", str(clone_dir), "checkout", row["revision"]], check=True)
                source = clone_dir / row["rel_path"] if row["rel_path"] else clone_dir
                if source.is_file():
                    source = source.parent
                if not source.is_dir():
                    report["missing"].append(package_path)
                    continue
            except subprocess.CalledProcessError:
                report["missing"].append(package_path)
                continue
        destination = args.output / package_path.removeprefix("//pub/")
        if destination.exists():
            for child in destination.iterdir():
                if child.name != ".git":
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
        destination.mkdir(parents=True, exist_ok=True)
        checksums, blocked_files = copy_package(source, destination)
        config = destination / "partcad.yaml"
        rel_path = row["rel_path"]
        if rel_path and Path(rel_path).suffix in {".yaml", ".yml"}:
            candidate = destination / Path(rel_path).name
            if candidate.is_file():
                shutil.copy2(candidate, config)
                checksums["partcad.yaml"] = sha256(config)
        metadata = {
            "upstream_url": row["source_url"],
            "upstream_revision": revision(source, row["revision"]),
            "synchronized_at": datetime.now(timezone.utc).isoformat(),
            "license_status": "verified" if any((destination / name).is_file() for name in ("LICENSE", "LICENSE.md", "COPYING")) else "unverified",
            "checksums": checksums,
        }
        (destination / ".narys-upstream.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        report["migrated"].append({"path": package_path, "files": len(checksums)})
        if blocked_files:
            report["blocked"].append({"path": package_path, "files": blocked_files})

    (args.output / "sync-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: len(value) for key, value in report.items()}))
    return 1 if report["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
