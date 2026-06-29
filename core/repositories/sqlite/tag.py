"""
SQLite implementation of ITagRepository.

Tag usage counts require cross-table lookups (devices, bandwidth_caps,
subnets) because a tag definition declares which scopes it applies to.
The repository receives the connection directly and performs those reads
in-process rather than calling back to sibling repositories — this avoids
circular dependencies and keeps the query cost visible.
"""
import json
import sqlite3
import threading
import time
import uuid
from typing import Optional

from core.repositories.interfaces import ITagRepository
from core.repositories.sqlite.base import SQLiteBaseRepository

_SCOPE_TABLE: dict[str, str] = {
    "devices": "devices",
    "bandwidth": "bandwidth_caps",
    "subnets": "subnets",
}


class SQLiteTagRepository(SQLiteBaseRepository, ITagRepository):
    """Persists tag definitions in the ``tag_defs`` SQLite table."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        super().__init__(conn, lock)

    def list_all(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM tag_defs ORDER BY updated_at ASC"
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def get(self, tag_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM tag_defs WHERE id = ?", (tag_id,)
            ).fetchone()
        return json.loads(row["data"]) if row else None

    def upsert(self, tag_def: dict) -> dict:
        """Insert or update a tag definition.
        Expected shape: {id?, name, scopes: [...], values: [...]}
        """
        if not tag_def.get("id"):
            tag_def["id"] = str(uuid.uuid4())
        tag_def.setdefault("scopes", [])
        tag_def.setdefault("values", [])
        with self._lock:
            self._conn.execute(
                "INSERT INTO tag_defs (id, data, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data, "
                "updated_at = excluded.updated_at",
                (tag_def["id"], json.dumps(tag_def), time.time()),
            )
            self._conn.commit()
        return tag_def

    def delete(self, tag_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tag_defs WHERE id = ?", (tag_id,))
            self._conn.commit()

    def usage_count(self, tag_id: str) -> int:
        """Total records across all applicable scopes with a non-empty value."""
        tag_def = self.get(tag_id)
        if not tag_def:
            return 0
        count = 0
        for scope in tag_def.get("scopes", []):
            table = _SCOPE_TABLE.get(scope)
            if not table:
                continue
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT data FROM {table}"
                ).fetchall()
            for r in rows:
                data = json.loads(r["data"])
                if (data.get("tags") or {}).get(tag_id):
                    count += 1
        return count

    def value_usage_count(self, tag_id: str, value: str) -> int:
        """Records across all applicable scopes that hold exactly *value*."""
        tag_def = self.get(tag_id)
        if not tag_def:
            return 0
        count = 0
        for scope in tag_def.get("scopes", []):
            table = _SCOPE_TABLE.get(scope)
            if not table:
                continue
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT data FROM {table}"
                ).fetchall()
            for r in rows:
                data = json.loads(r["data"])
                if (data.get("tags") or {}).get(tag_id) == value:
                    count += 1
        return count
