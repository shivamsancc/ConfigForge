"""SQLite implementation of IHistoryRepository (YAML generation history)."""
import json
import sqlite3
import threading
import time
import uuid
from typing import Optional

from core.repositories.interfaces import IHistoryRepository
from core.repositories.sqlite.base import now_iso_from_unix


class SQLiteHistoryRepository(IHistoryRepository):
    """Persists YAML generation snapshots in the ``yaml_history`` SQLite table."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    def save(self, actor: Optional[str], summary: str, files: dict) -> str:
        entry_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO yaml_history (id, ts, actor, summary, files) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    entry_id,
                    time.time(),
                    actor or "unknown",
                    summary,
                    json.dumps(files),
                ),
            )
            self._conn.commit()
        return entry_id

    def list_recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, actor, summary "
                "FROM yaml_history ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "ts": now_iso_from_unix(r["ts"]),
                "actor": r["actor"],
                "summary": r["summary"],
            }
            for r in rows
        ]

    def get(self, entry_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, ts, actor, summary, files "
                "FROM yaml_history WHERE id = ?",
                (entry_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "ts": now_iso_from_unix(row["ts"]),
            "actor": row["actor"],
            "summary": row["summary"],
            "files": json.loads(row["files"]),
        }
