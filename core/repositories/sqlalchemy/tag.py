"""
SQLAlchemy implementation of ITagRepository.

Tag usage counts require cross-table reads (devices, bandwidth_caps, subnets).
They are performed inline using raw SQL via the engine — same approach as
the SQLite implementation, avoiding circular repo dependencies.

The ``_engine`` property comes from the inherited ``StorageProvider`` — no
direct SQLAlchemy or SQLite imports are needed here.
"""
import json
import time
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.repositories.interfaces import ITagRepository
from core.repositories.sqlalchemy.base import SQLAlchemyBaseRepository
from core.storage.provider import StorageProvider

_SCOPE_TABLE: dict[str, str] = {
    "devices": "devices",
    "bandwidth": "bandwidth_caps",
    "subnets": "subnets",
}


class SQLAlchemyTagRepository(SQLAlchemyBaseRepository, ITagRepository):
    """Persists tag definitions in the ``tag_defs`` table."""

    def __init__(self, provider: StorageProvider) -> None:
        super().__init__(provider)

    def list_all(self) -> list[dict]:
        with Session(self._engine) as session:
            rows = session.execute(
                text("SELECT data FROM tag_defs ORDER BY updated_at ASC")
            ).all()
        return [json.loads(r[0]) for r in rows]

    def get(self, tag_id: str) -> Optional[dict]:
        with Session(self._engine) as session:
            row = session.execute(
                text("SELECT data FROM tag_defs WHERE id = :id"), {"id": tag_id}
            ).fetchone()
        return json.loads(row[0]) if row else None

    def upsert(self, tag_def: dict) -> dict:
        if not tag_def.get("id"):
            tag_def["id"] = str(uuid.uuid4())
        tag_def.setdefault("scopes", [])
        tag_def.setdefault("values", [])
        with Session(self._engine) as session:
            session.execute(
                text(
                    "INSERT INTO tag_defs (id, data, updated_at) VALUES (:id, :data, :ts) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "data = excluded.data, updated_at = excluded.updated_at"
                ),
                {"id": tag_def["id"], "data": json.dumps(tag_def), "ts": time.time()},
            )
            session.commit()
        return tag_def

    def delete(self, tag_id: str) -> None:
        with Session(self._engine) as session:
            session.execute(
                text("DELETE FROM tag_defs WHERE id = :id"), {"id": tag_id}
            )
            session.commit()

    def usage_count(self, tag_id: str) -> int:
        tag_def = self.get(tag_id)
        if not tag_def:
            return 0
        count = 0
        for scope in tag_def.get("scopes", []):
            table = _SCOPE_TABLE.get(scope)
            if not table:
                continue
            with Session(self._engine) as session:
                rows = session.execute(text(f"SELECT data FROM {table}")).all()
            for r in rows:
                if (json.loads(r[0]).get("tags") or {}).get(tag_id):
                    count += 1
        return count

    def value_usage_count(self, tag_id: str, value: str) -> int:
        tag_def = self.get(tag_id)
        if not tag_def:
            return 0
        count = 0
        for scope in tag_def.get("scopes", []):
            table = _SCOPE_TABLE.get(scope)
            if not table:
                continue
            with Session(self._engine) as session:
                rows = session.execute(text(f"SELECT data FROM {table}")).all()
            for r in rows:
                if (json.loads(r[0]).get("tags") or {}).get(tag_id) == value:
                    count += 1
        return count
