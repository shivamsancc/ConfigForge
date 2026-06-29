"""
Shared SQLite CRUD helpers for JSON-blob tables.

Every entity table has the same physical shape::

    CREATE TABLE <name> (
        id         TEXT PRIMARY KEY,
        data       TEXT NOT NULL,    -- JSON blob of the domain record
        updated_at REAL NOT NULL     -- Unix timestamp, used for ordering
    )

``SQLiteBaseRepository`` provides generic list/get/upsert/delete/replace/merge
operations on top of this shape.  Concrete repositories extend this class
and supply the table name plus optional encode/decode hooks.
"""
import json
import sqlite3
import threading
import time
import uuid
from typing import Callable, Optional


def now_iso() -> str:
    """Return the current local time as 'YYYY-MM-DD HH:MM:SS'."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def now_iso_from_unix(ts: float) -> str:
    """Convert a Unix timestamp to 'YYYY-MM-DD HH:MM:SS' in local time."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


class SQLiteBaseRepository:
    """
    Generic CRUD mixin for single-table, JSON-blob SQLite repositories.

    Subclasses set ``_TABLE`` and optionally override ``_encode`` / ``_decode``
    to apply per-entity transformation (e.g., credential encryption).
    """

    _TABLE: str = ""  # subclasses must override

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    # ------------------------------------------------------------------
    # Generic helpers — called by concrete subclasses
    # ------------------------------------------------------------------

    def _list_rows(
        self,
        table: str,
        decode: Optional[Callable[[dict], dict]] = None,
    ) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT data FROM {table} ORDER BY updated_at ASC"
            ).fetchall()
        out = [json.loads(r["data"]) for r in rows]
        return [decode(r) for r in out] if decode else out

    def _get_row(
        self,
        table: str,
        row_id: str,
        decode: Optional[Callable[[dict], dict]] = None,
    ) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                f"SELECT data FROM {table} WHERE id = ?", (row_id,)
            ).fetchone()
        if not row:
            return None
        data = json.loads(row["data"])
        return decode(data) if decode else data

    def _upsert_row(
        self,
        table: str,
        row: dict,
        encode: Optional[Callable[[dict], dict]] = None,
    ) -> dict:
        if not row.get("id"):
            row["id"] = str(uuid.uuid4())
        row.setdefault("tags", {})
        encoded = encode(row) if encode else row
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {table} (id, data, updated_at) VALUES (?, ?, ?) "
                f"ON CONFLICT(id) DO UPDATE SET data = excluded.data, "
                f"updated_at = excluded.updated_at",
                (row["id"], json.dumps(encoded), time.time()),
            )
            self._conn.commit()
        return row

    def _delete_row(self, table: str, row_id: str) -> None:
        with self._lock:
            self._conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
            self._conn.commit()

    def _replace_all(
        self,
        table: str,
        rows: list[dict],
        encode: Optional[Callable[[dict], dict]] = None,
    ) -> None:
        with self._lock:
            self._conn.execute(f"DELETE FROM {table}")
            now = time.time()
            for r in rows:
                if not r.get("id"):
                    r["id"] = str(uuid.uuid4())
                r.setdefault("tags", {})
                encoded = encode(r) if encode else r
                self._conn.execute(
                    f"INSERT INTO {table} (id, data, updated_at) VALUES (?, ?, ?)",
                    (r["id"], json.dumps(encoded), now),
                )
            self._conn.commit()

    def _merge_rows(
        self,
        table: str,
        rows: list[dict],
        encode: Optional[Callable[[dict], dict]] = None,
    ) -> None:
        for r in rows:
            self._upsert_row(table, r, encode=encode)
