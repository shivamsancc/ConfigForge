"""SQLAlchemy implementation of IMetaRepository (key-value metadata store)."""
from typing import Optional, TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.repositories.interfaces import IMetaRepository

if TYPE_CHECKING:
    from core.storage.provider import StorageProvider


class SQLAlchemyMetaRepository(IMetaRepository):
    """Persists key-value metadata in the ``meta`` table."""

    def __init__(self, provider: "StorageProvider") -> None:
        self._provider = provider

    @property
    def _engine(self):
        return self._provider.get_engine()

    def get_kv(self, key: str) -> Optional[str]:
        with Session(self._engine) as session:
            row = session.execute(
                text("SELECT value FROM meta WHERE key = :key"), {"key": key}
            ).fetchone()
        return row[0] if row else None

    def set_kv(self, key: str, value: str) -> None:
        with Session(self._engine) as session:
            session.execute(
                text(
                    "INSERT INTO meta (key, value) VALUES (:key, :value) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                ),
                {"key": key, "value": value},
            )
            session.commit()
