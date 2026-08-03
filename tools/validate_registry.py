from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml

MAX_FILE_SIZE = 100 * 1024 * 1024


def main(root: Path) -> int:
    errors: list[str] = []
    manifests = list(root.rglob(".narys-upstream.yaml"))
    for manifest in manifests:
        package = manifest.parent
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            errors.append(f"{manifest}: invalid YAML: {exc}")
            continue
        if not data.get("upstream_url") or not data.get("upstream_revision"):
            errors.append(f"{manifest}: missing upstream metadata")
        if not (package / "partcad.yaml").is_file():
            errors.append(f"{package}: missing partcad.yaml")
        for relative, expected in (data.get("checksums") or {}).items():
            path = (package / relative).resolve()
            if not path.is_relative_to(package.resolve()) or not path.is_file():
                errors.append(f"{manifest}: unsafe or missing path {relative}")
                continue
            if path.stat().st_size > MAX_FILE_SIZE:
                errors.append(f"{path}: exceeds 100 MiB")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != expected:
                errors.append(f"{path}: checksum mismatch")
    if not manifests:
        errors.append("No package manifests found")
    print("\n".join(errors) if errors else f"Validated {len(manifests)} packages")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".")))
