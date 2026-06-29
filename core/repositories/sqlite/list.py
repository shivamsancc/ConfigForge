"""
SQLite implementation of IListRepository.

Only Collector Region remains a hardcoded, mandatory managed list — see the
original storage.py module docstring for the rationale.  All other
categorisations live in the tag system.
"""
import json
import sqlite3
import threading

from core.repositories.interfaces import IListRepository

# The single fixed list that remains after the tag-system migration.
FIXED_LISTS: tuple[str, ...] = ("collectorRegions",)


class SQLiteListRepository(IListRepository):
    """Persists managed dropdown lists in the ``lists`` SQLite table."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    def get_all(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT list_name, items FROM lists"
            ).fetchall()
        return {r["list_name"]: json.loads(r["items"]) for r in rows}

    def set_list(self, list_name: str, items: list) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO lists (list_name, items) VALUES (?, ?) "
                "ON CONFLICT(list_name) DO UPDATE SET items = excluded.items",
                (list_name, json.dumps(items)),
            )
            self._conn.commit()
