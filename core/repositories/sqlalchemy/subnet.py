"""SQLAlchemy implementation of ISubnetRepository."""
import ipaddress
from typing import Optional

from core.repositories.interfaces import ISubnetRepository
from core.repositories.sqlalchemy.base import SQLAlchemyBaseRepository
from core.storage.provider import StorageProvider


class SQLAlchemySubnetRepository(SQLAlchemyBaseRepository, ISubnetRepository):
    """Persists subnet records in the ``subnets`` table."""

    def __init__(self, provider: StorageProvider) -> None:
        super().__init__(provider)

    def list_all(self) -> list[dict]:
        return self._list_rows("subnets")

    def get(self, row_id: str) -> Optional[dict]:
        return self._get_row("subnets", row_id)

    def upsert(self, subnet: dict) -> dict:
        return self._upsert_row("subnets", subnet)

    def delete(self, row_id: str) -> None:
        self._delete_row("subnets", row_id)

    def replace_all(self, subnets: list[dict]) -> None:
        self._replace_all("subnets", subnets)

    def merge(self, subnets: list[dict]) -> None:
        self._merge_rows("subnets", subnets)

    def find_for_ip(
        self,
        ip_str: str,
        subnets: Optional[list[dict]] = None,
    ) -> Optional[dict]:
        """Return the most-specific subnet containing *ip_str*, or None."""
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return None
        all_subnets = subnets if subnets is not None else self.list_all()
        best = None
        best_prefix = -1
        for s in all_subnets:
            try:
                net = ipaddress.ip_network(s.get("CIDR", ""), strict=False)
            except ValueError:
                continue
            if ip in net and net.prefixlen > best_prefix:
                best = s
                best_prefix = net.prefixlen
        return best
