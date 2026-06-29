"""SQLite implementation of IAuditRepository (append-only audit log)."""
import json
import sqlite3
import threading
import time
import uuid
from typing import Optional

from core.repositories.interfaces import IAuditRepository
from core.repositories.sqlite.base import now_iso_from_unix


class SQLiteAuditRepository(IAuditRepository):
    """Persists audit entries in the ``audit_log`` SQLite table."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    def log(
        self, actor: Optional[str], action: str, details=None
    ) -> str:
        entry_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_log (id, ts, actor, action, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    entry_id,
                    time.time(),
                    actor or "unknown",
                    action,
                    json.dumps(details) if details is not None else None,
                ),
            )
            self._conn.commit()
        return entry_id

    def list_recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, actor, action, details "
                "FROM audit_log ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "ts": now_iso_from_unix(r["ts"]),
                "actor": r["actor"],
                "action": r["action"],
                "details": json.loads(r["details"]) if r["details"] else None,
            }
            for r in rows
        ]
