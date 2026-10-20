"""SQLite 持久化：记忆行存储 + request_id 幂等去重。"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any


class Storage:
    def __init__(self, db_path: str):
        db_path = os.path.abspath(db_path)
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    request_id TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    embedding BLOB
                );
                CREATE INDEX IF NOT EXISTS idx_mem_user_ts
                    ON memories(user_id, created_ts, id);
                CREATE TABLE IF NOT EXISTS processed (
                    request_id TEXT PRIMARY KEY,
                    created_ts REAL NOT NULL
                );
                """
            )

    def is_processed(self, request_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM processed WHERE request_id = ?", (request_id,)
            )
            return cur.fetchone() is not None

    def mark_processed(self, request_id: str, created_ts: float) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO processed(request_id, created_ts) VALUES(?, ?)",
                (request_id, created_ts),
            )

    def insert_memories(self, rows: list[dict[str, Any]]) -> list[int]:
        with self._lock, self._conn:
            ids: list[int] = []
            for r in rows:
                cur = self._conn.execute(
                    "INSERT INTO memories"
                    "(user_id, session_id, request_id, content, created_at, created_ts, embedding)"
                    " VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (
                        r["user_id"],
                        r["session_id"],
                        r["request_id"],
                        r["content"],
                        r["created_at"],
                        r["created_ts"],
                        r["embedding"],
                    ),
                )
                ids.append(cur.lastrowid)
            return ids

    def get_user_memories(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, content, created_at, created_ts, embedding"
                " FROM memories WHERE user_id = ?"
                " ORDER BY created_ts ASC, id ASC",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
