"""SQLite implementation of IBandwidthRepository."""
import sqlite3
import threading
from typing import Optional

from core.repositories.interfaces import IBandwidthRepository
from core.repositories.sqlite.base import SQLiteBaseRepository


class SQLiteBandwidthRepository(SQLiteBaseRepository, IBandwidthRepository):
    """Persists bandwidth cap records in the ``bandwidth_caps`` SQLite table."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        super().__init__(conn, lock)

    def list_all(self) -> list[dict]:
        return self._list_rows("bandwidth_caps")

    def get(self, row_id: str) -> Optional[dict]:
        return self._get_row("bandwidth_caps", row_id)

    def upsert(self, row: dict) -> dict:
        return self._upsert_row("bandwidth_caps", row)

    def delete(self, row_id: str) -> None:
        self._delete_row("bandwidth_caps", row_id)

    def replace_all(self, rows: list[dict]) -> None:
        self._replace_all("bandwidth_caps", rows)

    def merge(self, rows: list[dict]) -> None:
        self._merge_rows("bandwidth_caps", rows)
