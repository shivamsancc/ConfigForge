"""SQLAlchemy implementation of IListRepository."""
import json
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.repositories.interfaces import IListRepository

if TYPE_CHECKING:
    from core.storage.provider import StorageProvider

# The single fixed list that remains after the tag-system migration.
FIXED_LISTS: tuple[str, ...] = ("collectorRegions",)


class SQLAlchemyListRepository(IListRepository):
    """Persists managed dropdown lists in the ``lists`` table."""

    def __init__(self, provider: "StorageProvider") -> None:
        self._provider = provider

    @property
    def _engine(self):
        return self._provider.get_engine()

    def get_all(self) -> dict:
        with Session(self._engine) as session:
            rows = session.execute(
                text("SELECT list_name, items FROM lists")
            ).all()
        return {r[0]: json.loads(r[1]) for r in rows}

    def set_list(self, list_name: str, items: list) -> None:
        with Session(self._engine) as session:
            session.execute(
                text(
                    "INSERT INTO lists (list_name, items) VALUES (:name, :items) "
                    "ON CONFLICT(list_name) DO UPDATE SET items = excluded.items"
                ),
                {"name": list_name, "items": json.dumps(items)},
            )
            session.commit()
