from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any

from .models import now_iso

SCOPED_TABLES = {"tool_calls", "approvals", "runs", "model_calls"}
TABLES = {"incidents", "events", "tool_calls", "approvals", "evaluations", "runs", "model_calls"}


class Store:
    """Small repository supporting SQLite offline and PostgreSQL in Compose."""

    def __init__(self, path: str | None = None):
        database_url = None if path else os.getenv("DATABASE_URL")
        self.backend = "postgres" if database_url and database_url.startswith("postgres") else "sqlite"
        self.path = path or os.getenv("AGENTOPS_DB_PATH", "agentops.db")
        self.database_url = database_url
        self.lock = threading.RLock()
        self._init()

    @contextmanager
    def connect(self):
        if self.backend == "postgres":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError("psycopg is required when DATABASE_URL is configured") from exc
            with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
                yield connection
        else:
            connection = sqlite3.connect(self.path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def _init(self):
        serial = "BIGSERIAL" if self.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        seq_column = f"seq {serial} PRIMARY KEY" if self.backend == "postgres" else f"seq {serial}"
        statements = [
            "CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, data TEXT NOT NULL)",
            f"CREATE TABLE IF NOT EXISTS events ({seq_column}, incident_id TEXT, data TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS tool_calls (id TEXT PRIMARY KEY, incident_id TEXT, data TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, incident_id TEXT, data TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY, data TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, incident_id TEXT, data TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS model_calls (id TEXT PRIMARY KEY, incident_id TEXT, data TEXT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS idx_events_incident_seq ON events (incident_id, seq)",
        ]
        with self.connect() as db:
            for statement in statements:
                db.execute(statement)

    @property
    def placeholder(self) -> str:
        return "%s" if self.backend == "postgres" else "?"

    def _table(self, table: str) -> str:
        if table not in TABLES:
            raise ValueError("unknown store table")
        return table

    def put(self, table: str, key: str, data: dict[str, Any]):
        table = self._table(table)
        scoped = table in SCOPED_TABLES
        columns = "id, incident_id, data" if scoped else "id, data"
        marks = ", ".join([self.placeholder] * (3 if scoped else 2))
        update = "incident_id=excluded.incident_id, data=excluded.data" if scoped else "data=excluded.data"
        values = (key, data["incident_id"], json.dumps(data)) if scoped else (key, json.dumps(data))
        with self.lock, self.connect() as db:
            db.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks}) ON CONFLICT(id) DO UPDATE SET {update}", values)

    def get(self, table: str, key: str) -> dict[str, Any] | None:
        table = self._table(table)
        with self.connect() as db:
            row = db.execute(f"SELECT data FROM {table} WHERE id={self.placeholder}", (key,)).fetchone()
        if not row:
            return None
        raw = row["data"] if self.backend == "postgres" else row[0]
        return json.loads(raw)

    def list(self, table: str, incident_id: str | None = None) -> list[dict[str, Any]]:
        table = self._table(table)
        with self.connect() as db:
            if incident_id and table in SCOPED_TABLES:
                rows = db.execute(f"SELECT data FROM {table} WHERE incident_id={self.placeholder}", (incident_id,)).fetchall()
            else:
                rows = db.execute(f"SELECT data FROM {table}").fetchall()
        return [json.loads(row["data"] if self.backend == "postgres" else row[0]) for row in rows]

    def event(self, incident_id: str, type_: str, message: str, data: dict[str, Any] | None = None):
        value = {"schema_version": 1, "incident_id": incident_id, "type": type_, "node": type_, "status": "completed", "message": message, "data": data or {}, "created_at": now_iso()}
        with self.lock, self.connect() as db:
            db.execute(f"INSERT INTO events (incident_id,data) VALUES ({self.placeholder},{self.placeholder})", (incident_id, json.dumps(value)))
        return value

    def events(self, incident_id: str, after: int = 0):
        with self.connect() as db:
            rows = db.execute(f"SELECT seq,data FROM events WHERE incident_id={self.placeholder} AND seq>{self.placeholder} ORDER BY seq", (incident_id, after)).fetchall()
        if self.backend == "postgres":
            return [{"seq": row["seq"], **json.loads(row["data"])} for row in rows]
        return [{"seq": row[0], **json.loads(row[1])} for row in rows]
