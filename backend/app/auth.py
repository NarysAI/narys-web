from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Principal:
    key_id: str
    name: str
    role: str


class AuthService:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self._init_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _init_database(self) -> None:
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY, name TEXT NOT NULL, digest TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('user','admin')), created_at INTEGER NOT NULL,
                revoked_at INTEGER
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS download_tickets (
                digest TEXT PRIMARY KEY, object_id TEXT NOT NULL, key_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL, used_at INTEGER
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY, occurred_at INTEGER NOT NULL, key_id TEXT,
                action TEXT NOT NULL, resource TEXT, outcome TEXT NOT NULL
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY, started_at INTEGER NOT NULL, finished_at INTEGER,
                status TEXT NOT NULL, details TEXT NOT NULL DEFAULT ''
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_digest ON api_keys(digest)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tickets_expires ON download_tickets(expires_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_log(occurred_at)")
            connection.execute("PRAGMA optimize")

    def create_key(self, name: str, role: str) -> tuple[str, dict]:
        if role not in {"user", "admin"}:
            raise ValueError("Role must be user or admin")
        key_id = secrets.token_hex(8)
        plaintext = f"narys_{key_id}_{secrets.token_urlsafe(32)}"
        created_at = int(time.time())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO api_keys VALUES (?,?,?,?,?,NULL)",
                (key_id, name.strip() or key_id, self._digest(plaintext), role, created_at),
            )
        return plaintext, {"key_id": key_id, "name": name, "role": role, "created_at": created_at}

    def authenticate(self, plaintext: str | None) -> Principal | None:
        if not plaintext:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT key_id,name,role FROM api_keys WHERE digest=? AND revoked_at IS NULL",
                (self._digest(plaintext),),
            ).fetchone()
        return Principal(**dict(row)) if row else None

    def list_keys(self) -> list[dict]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT key_id,name,role,created_at,revoked_at FROM api_keys ORDER BY created_at DESC"
            )]

    def revoke_key(self, key_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE api_keys SET revoked_at=? WHERE key_id=? AND revoked_at IS NULL",
                (int(time.time()), key_id),
            )
            return result.rowcount == 1

    def create_ticket(self, object_id: str, principal: Principal, ttl: int = 60) -> str:
        ticket = secrets.token_urlsafe(32)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO download_tickets VALUES (?,?,?,?,NULL)",
                (self._digest(ticket), object_id, principal.key_id, int(time.time()) + ttl),
            )
        self.audit(principal.key_id, "ticket.create", object_id, "ok")
        return ticket

    def consume_ticket(self, ticket: str) -> tuple[str, str] | None:
        now = int(time.time())
        digest = self._digest(ticket)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT object_id,key_id,expires_at,used_at FROM download_tickets WHERE digest=?", (digest,)
            ).fetchone()
            if not row or row["used_at"] is not None or row["expires_at"] < now:
                return None
            connection.execute("UPDATE download_tickets SET used_at=? WHERE digest=?", (now, digest))
        self.audit(row["key_id"], "download", row["object_id"], "ok")
        return row["object_id"], row["key_id"]

    def audit(self, key_id: str | None, action: str, resource: str | None, outcome: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log(occurred_at,key_id,action,resource,outcome) VALUES (?,?,?,?,?)",
                (int(time.time()), key_id, action, resource, outcome),
            )

    def audit_entries(self, limit: int = 200) -> list[dict]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 1000),)
            )]

    def start_sync(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO sync_runs(started_at,status) VALUES (?,'running')", (int(time.time()),)
            )
            return int(cursor.lastrowid)

    def finish_sync(self, run_id: int, status: str, details: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sync_runs SET finished_at=?,status=?,details=? WHERE id=?",
                (int(time.time()), status, json.dumps(details), run_id),
            )

    def sync_runs(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 500),)
            )]
