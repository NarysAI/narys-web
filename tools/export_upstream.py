"""Export one PUB package to an upstream-compatible branch and optional PR."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--title", default="Update PartCAD package from NarysAI")
    parser.add_argument("--create-pr", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    manifest = yaml.safe_load((package / ".narys-upstream.yaml").read_text(encoding="utf-8"))
    upstream = manifest["upstream_url"]
    revision = manifest["upstream_revision"]
    checkout = Path(tempfile.mkdtemp(prefix="narys-export-"))
    run("git", "clone", upstream, str(checkout))
    run("git", "checkout", "-b", args.branch, revision, cwd=checkout)
    for source in package.rglob("*"):
        relative = source.relative_to(package)
        if ".git" in relative.parts or source.name.startswith(".narys-"):
            continue
        target = checkout / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    run("git", "add", ".", cwd=checkout)
    run("git", "commit", "-m", args.title, cwd=checkout)
    print(f"Prepared upstream-compatible branch at {checkout}")
    if args.create_pr:
        run("gh", "repo", "fork", upstream, "--remote", cwd=checkout)
        run("git", "push", "fork", args.branch, cwd=checkout)
        run("gh", "pr", "create", "--repo", upstream, "--head", args.branch, "--title", args.title, "--body", "Exported from NarysAI PUB; provenance files excluded.", cwd=checkout)


if __name__ == "__main__":
    main()
