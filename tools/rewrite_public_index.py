from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path)
    args = parser.parse_args()
    for config in args.index.rglob("partcad.yaml"):
        category = config.parent.relative_to(args.index).as_posix()
        if category == ".":
            category = ""
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        for section in ("import", "dependencies"):
            imports = data.get(section)
            if not isinstance(imports, dict):
                continue
            for name, spec in imports.items():
                if not isinstance(spec, dict) or spec.get("type") != "git":
                    continue
                rel_path = "/".join(filter(None, (category, str(name))))
                spec["url"] = "https://github.com/NarysAI/PUB.git"
                spec["web"] = f"https://github.com/NarysAI/PUB/tree/main/{rel_path}"
                spec["revision"] = "main"
                spec["relPath"] = rel_path
        config.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


if __name__ == "__main__":
    main()
