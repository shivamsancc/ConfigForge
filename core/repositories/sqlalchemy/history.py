"""SQLAlchemy implementation of IHistoryRepository (YAML generation history)."""
import json
import time
import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.repositories.interfaces import IHistoryRepository
from core.repositories.sqlalchemy.base import now_iso_from_unix

if TYPE_CHECKING:
    from core.storage.provider import StorageProvider


class SQLAlchemyHistoryRepository(IHistoryRepository):
    """Persists YAML generation snapshots in the ``yaml_history`` table."""

    def __init__(self, provider: "StorageProvider") -> None:
        self._provider = provider

    @property
    def _engine(self):
        return self._provider.get_engine()

    def save(self, actor: Optional[str], summary: str, files: dict) -> str:
        entry_id = str(uuid.uuid4())
        with Session(self._engine) as session:
            session.execute(
                text(
                    "INSERT INTO yaml_history (id, ts, actor, summary, files) "
                    "VALUES (:id, :ts, :actor, :summary, :files)"
                ),
                {
                    "id": entry_id,
                    "ts": time.time(),
                    "actor": actor or "unknown",
                    "summary": summary,
                    "files": json.dumps(files),
                },
            )
            session.commit()
        return entry_id

    def list_recent(self, limit: int = 50) -> list[dict]:
        with Session(self._engine) as session:
            rows = session.execute(
                text(
                    "SELECT id, ts, actor, summary "
                    "FROM yaml_history ORDER BY ts DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).all()
        return [
            {
                "id": r[0],
                "ts": now_iso_from_unix(r[1]),
                "actor": r[2],
                "summary": r[3],
            }
            for r in rows
        ]

    def get(self, entry_id: str) -> Optional[dict]:
        with Session(self._engine) as session:
            row = session.execute(
                text(
                    "SELECT id, ts, actor, summary, files "
                    "FROM yaml_history WHERE id = :id"
                ),
                {"id": entry_id},
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "ts": now_iso_from_unix(row[1]),
            "actor": row[2],
            "summary": row[3],
            "files": json.loads(row[4]),
        }
