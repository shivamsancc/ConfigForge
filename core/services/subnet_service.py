"""
Subnet service — business logic for subnet (CIDR) CRUD operations.
"""
import ipaddress
from typing import Optional

from core.repositories.interfaces import ISubnetRepository, IAuditRepository


class SubnetService:
    """Orchestrates subnet CRUD with CIDR validation and audit logging."""

    def __init__(
        self,
        subnet_repo: ISubnetRepository,
        audit_repo: IAuditRepository,
    ) -> None:
        self._subnet_repo = subnet_repo
        self._audit_repo = audit_repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_subnets(self) -> list[dict]:
        return self._subnet_repo.list_all()

    def get_subnet(self, row_id: str) -> Optional[dict]:
        return self._subnet_repo.get(row_id)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_or_update(self, subnet: dict, actor: Optional[str]) -> dict:
        """Validate and persist a subnet record.

        Raises
        ------
        ValueError
            When the supplied CIDR string is present but not a valid network.
        """
        cidr = (subnet.get("CIDR") or "").strip()
        if cidr:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                raise ValueError(f"'{cidr}' is not a valid CIDR")
        is_create = not subnet.get("id")
        saved = self._subnet_repo.upsert(subnet)
        self._audit_repo.log(
            actor,
            "create_subnet" if is_create else "update_subnet",
            {"id": saved["id"], "cidr": saved.get("CIDR")},
        )
        return saved

    def delete(self, row_id: str, actor: Optional[str]) -> None:
        self._subnet_repo.delete(row_id)
        self._audit_repo.log(actor, "delete_subnet", {"id": row_id})

    def replace_all(self, rows: list[dict], actor: Optional[str]) -> None:
        self._subnet_repo.replace_all(rows)
        self._audit_repo.log(
            actor, "import_subnets", {"count": len(rows), "mode": "replace"}
        )

    def merge(self, rows: list[dict], actor: Optional[str]) -> None:
        self._subnet_repo.merge(rows)
        self._audit_repo.log(
            actor, "import_subnets", {"count": len(rows), "mode": "merge"}
        )
