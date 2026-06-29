"""SQLAlchemy implementation of IAuditRepository (append-only audit log)."""
import json
import time
import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.repositories.interfaces import IAuditRepository
from core.repositories.sqlalchemy.base import now_iso_from_unix

if TYPE_CHECKING:
    from core.storage.provider import StorageProvider


class SQLAlchemyAuditRepository(IAuditRepository):
    """Persists audit entries in the ``audit_log`` table."""

    def __init__(self, provider: "StorageProvider") -> None:
        self._provider = provider

    @property
    def _engine(self):
        return self._provider.get_engine()

    def log(self, actor: Optional[str], action: str, details=None) -> str:
        entry_id = str(uuid.uuid4())
        with Session(self._engine) as session:
            session.execute(
                text(
                    "INSERT INTO audit_log (id, ts, actor, action, details) "
                    "VALUES (:id, :ts, :actor, :action, :details)"
                ),
                {
                    "id": entry_id,
                    "ts": time.time(),
                    "actor": actor or "unknown",
                    "action": action,
                    "details": json.dumps(details) if details is not None else None,
                },
            )
            session.commit()
        return entry_id

    def list_recent(self, limit: int = 100) -> list[dict]:
        with Session(self._engine) as session:
            rows = session.execute(
                text(
                    "SELECT id, ts, actor, action, details "
                    "FROM audit_log ORDER BY ts DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).all()
        return [
            {
                "id": r[0],
                "ts": now_iso_from_unix(r[1]),
                "actor": r[2],
                "action": r[3],
                "details": json.loads(r[4]) if r[4] else None,
            }
            for r in rows
        ]
