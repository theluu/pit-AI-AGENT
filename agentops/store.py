from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any

from .models import now_iso


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("AGENTOPS_DB_PATH", "agentops.db")
        self.lock = threading.RLock()
        self._init()

    def connect(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tool_calls (id TEXT PRIMARY KEY, incident_id TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, incident_id TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            """)

    def put(self, table: str, key: str, data: dict[str, Any]):
        with self.lock, self.connect() as db:
            db.execute(f"INSERT OR REPLACE INTO {table} (id, {'incident_id, ' if table in ('tool_calls','approvals') else ''}data) VALUES (?, {'?, ' if table in ('tool_calls','approvals') else ''}?)", (key, data["incident_id"], json.dumps(data)) if table in ("tool_calls", "approvals") else (key, json.dumps(data)))

    def get(self, table: str, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, table: str, incident_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            if incident_id and table in ("tool_calls", "approvals"):
                rows = db.execute(f"SELECT data FROM {table} WHERE incident_id=?", (incident_id,)).fetchall()
            else: rows = db.execute(f"SELECT data FROM {table}").fetchall()
        return [json.loads(r[0]) for r in rows]

    def event(self, incident_id: str, type_: str, message: str, data: dict[str, Any] | None = None):
        value = {"incident_id": incident_id, "type": type_, "message": message, "data": data or {}, "created_at": now_iso()}
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO events (incident_id,data) VALUES (?,?)", (incident_id, json.dumps(value)))
        return value

    def events(self, incident_id: str, after: int = 0):
        with self.connect() as db:
            rows = db.execute("SELECT seq,data FROM events WHERE incident_id=? AND seq>? ORDER BY seq", (incident_id, after)).fetchall()
        return [{"seq": r[0], **json.loads(r[1])} for r in rows]

