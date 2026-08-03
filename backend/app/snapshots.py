from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class SnapshotManager:
    """Create immutable, atomically activated copies of Git working trees."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def commit(repository: Path) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
        ).strip()

    def activate(self, name: str, repository: Path) -> Path:
        commit = self.commit(repository)
        destination = self.root / name / commit
        if not destination.is_dir():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=f".{commit}-", dir=destination.parent))
            try:
                for child in repository.iterdir():
                    if child.name == ".git":
                        continue
                    target = temporary / child.name
                    shutil.copytree(child, target) if child.is_dir() else shutil.copy2(child, target)
                os.replace(temporary, destination)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        active = self.root / name / "active.json"
        pending = active.with_suffix(".tmp")
        pending.write_text(json.dumps({"commit": commit, "path": str(destination)}), encoding="utf-8")
        os.replace(pending, active)
        return destination
