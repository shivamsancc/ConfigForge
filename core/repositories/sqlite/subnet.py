"""SQLite implementation of ISubnetRepository."""
import ipaddress
import sqlite3
import threading
from typing import Optional

from core.repositories.interfaces import ISubnetRepository
from core.repositories.sqlite.base import SQLiteBaseRepository


class SQLiteSubnetRepository(SQLiteBaseRepository, ISubnetRepository):
    """Persists subnet records in the ``subnets`` SQLite table."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        super().__init__(conn, lock)

    def list_all(self) -> list[dict]:
        return self._list_rows("subnets")

    def get(self, row_id: str) -> Optional[dict]:
        return self._get_row("subnets", row_id)

    def upsert(self, row: dict) -> dict:
        return self._upsert_row("subnets", row)

    def delete(self, row_id: str) -> None:
        self._delete_row("subnets", row_id)

    def replace_all(self, rows: list[dict]) -> None:
        self._replace_all("subnets", rows)

    def merge(self, rows: list[dict]) -> None:
        self._merge_rows("subnets", rows)

    def find_for_ip(
        self, ip_str: str, subnets: Optional[list[dict]] = None
    ) -> Optional[dict]:
        """Return the most-specific subnet (longest prefix) containing ip_str.

        Accepts an optional pre-loaded list to avoid a redundant DB read when
        the caller already holds the full subnet list.  Returns None when
        ip_str is blank, unparseable, or no subnet matches.
        """
        if not ip_str:
            return None
        try:
            ip = ipaddress.ip_address(ip_str.strip())
        except ValueError:
            return None

        if subnets is None:
            subnets = self.list_all()

        best: Optional[dict] = None
        best_prefix = -1

        for s in subnets:
            cidr = (s.get("CIDR") or "").strip()
            if not cidr:
                continue
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if ip in net and net.prefixlen > best_prefix:
                best = s
                best_prefix = net.prefixlen

        return best
