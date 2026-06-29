"""
Shared SQLAlchemy CRUD helpers for JSON-blob entity tables.

Physical schema for every entity table::

    id         TEXT PRIMARY KEY
    data       TEXT NOT NULL     -- JSON blob of the domain record
    updated_at REAL NOT NULL     -- Unix timestamp, used for ordering

Design change (v0.5 Storage Abstraction)
-----------------------------------------
Repositories now receive a ``StorageProvider`` rather than a bare
SQLAlchemy ``Engine``.  The provider is the single point of truth for the
active engine; switching from SQLite to PostgreSQL requires only a config
change and no repository modifications.

The ``_engine`` property surfaces the engine from the provider so all
existing query helpers (``_list_rows``, ``_upsert_row``, etc.) remain
unchanged — they simply call ``Session(self._engine)`` as before.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING, Callable, Optional

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from core.storage.provider import StorageProvider


def now_iso_from_unix(ts: float) -> str:
    import time as _t
    return _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(ts))


class SQLAlchemyBaseRepository:
    """
    Generic CRUD mixin for JSON-blob entity tables.

    Concrete repositories extend this class and supply the table name plus
    optional encode/decode hooks for per-entity transformation (e.g.
    credential encryption for devices).

    Parameters
    ----------
    provider:
        The active ``StorageProvider``.  Repositories call
        ``provider.get_engine()`` at query time rather than holding a
        direct reference to the engine; this means a provider swap (e.g.
        in tests or at runtime) is reflected immediately without
        recreating the repository.
    """

    def __init__(self, provider: "StorageProvider") -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # Engine accessor — repositories NEVER import a DB driver directly
    # ------------------------------------------------------------------

    @property
    def _engine(self) -> Engine:
        """
        Return the engine from the active storage provider.

        Repositories read through this property; they have no direct
        knowledge of SQLite, PostgreSQL, or any other backend.
        """
        return self._provider.get_engine()

    # ------------------------------------------------------------------
    # Generic CRUD helpers
    # ------------------------------------------------------------------

    def _list_rows(
        self,
        table: str,
        decode: Optional[Callable[[dict], dict]] = None,
    ) -> list[dict]:
        with Session(self._engine) as session:
            rows = session.execute(
                text(f"SELECT data FROM {table} ORDER BY updated_at ASC")
            ).all()
        out = [json.loads(r[0]) for r in rows]
        return [decode(r) for r in out] if decode else out

    def _get_row(
        self,
        table: str,
        row_id: str,
        decode: Optional[Callable[[dict], dict]] = None,
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            row = session.execute(
                text(f"SELECT data FROM {table} WHERE id = :id"),
                {"id": row_id},
            ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
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
        with Session(self._engine) as session:
            session.execute(
                text(
                    f"INSERT INTO {table} (id, data, updated_at) VALUES (:id, :data, :ts) "
                    f"ON CONFLICT(id) DO UPDATE SET "
                    f"data = excluded.data, updated_at = excluded.updated_at"
                ),
                {"id": row["id"], "data": json.dumps(encoded), "ts": time.time()},
            )
            session.commit()
        return row

    def _delete_row(self, table: str, row_id: str) -> None:
        with Session(self._engine) as session:
            session.execute(
                text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id}
            )
            session.commit()

    def _replace_all(
        self,
        table: str,
        rows: list[dict],
        encode: Optional[Callable[[dict], dict]] = None,
    ) -> None:
        now = time.time()
        with Session(self._engine) as session:
            session.execute(text(f"DELETE FROM {table}"))
            for r in rows:
                if not r.get("id"):
                    r["id"] = str(uuid.uuid4())
                r.setdefault("tags", {})
                encoded = encode(r) if encode else r
                session.execute(
                    text(
                        f"INSERT INTO {table} (id, data, updated_at) "
                        f"VALUES (:id, :data, :ts)"
                    ),
                    {"id": r["id"], "data": json.dumps(encoded), "ts": now},
                )
            session.commit()

    def _merge_rows(
        self,
        table: str,
        rows: list[dict],
        encode: Optional[Callable[[dict], dict]] = None,
    ) -> None:
        for r in rows:
            self._upsert_row(table, r, encode=encode)
