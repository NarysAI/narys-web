from __future__ import annotations

import argparse
import os
from pathlib import Path

from .auth import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="NarysAI local administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-key")
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=("user", "admin"), required=True)
    args = parser.parse_args()
    database = Path(os.getenv("NARYS_CACHE_DIR", ".cache/narys")) / "catalog.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    auth = AuthService(database)
    if args.command == "create-key":
        plaintext, metadata = auth.create_key(args.name, args.role)
        print(f"key_id={metadata['key_id']}")
        print(f"role={metadata['role']}")
        print(f"key={plaintext}")
        print("The plaintext key will not be shown again.")


if __name__ == "__main__":
    main()
