"""
Bandwidth service — business logic for bandwidth cap CRUD operations.
"""
from typing import Optional

from core.logic import is_valid_ip
from core.repositories.interfaces import IBandwidthRepository, IAuditRepository


class BandwidthService:
    """Orchestrates bandwidth cap CRUD with validation and audit logging."""

    def __init__(
        self,
        bandwidth_repo: IBandwidthRepository,
        audit_repo: IAuditRepository,
    ) -> None:
        self._bandwidth_repo = bandwidth_repo
        self._audit_repo = audit_repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_bandwidth(self) -> list[dict]:
        return self._bandwidth_repo.list_all()

    def get_bandwidth(self, row_id: str) -> Optional[dict]:
        return self._bandwidth_repo.get(row_id)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_or_update(self, row: dict, actor: Optional[str]) -> dict:
        """Validate and persist a bandwidth cap record.

        Raises
        ------
        ValueError
            When the supplied IP address string is not a valid IP.
        """
        ip = (row.get("IP") or "").strip()
        if ip and not is_valid_ip(ip):
            raise ValueError(f"'{ip}' is not a valid IP address")
        is_create = not row.get("id")
        saved = self._bandwidth_repo.upsert(row)
        self._audit_repo.log(
            actor,
            "create_bandwidth" if is_create else "update_bandwidth",
            {"id": saved["id"], "ip": saved.get("IP")},
        )
        return saved

    def delete(self, row_id: str, actor: Optional[str]) -> None:
        self._bandwidth_repo.delete(row_id)
        self._audit_repo.log(actor, "delete_bandwidth", {"id": row_id})

    def replace_all(self, rows: list[dict], actor: Optional[str]) -> None:
        self._bandwidth_repo.replace_all(rows)
        self._audit_repo.log(
            actor, "import_bandwidth", {"count": len(rows), "mode": "replace"}
        )

    def merge(self, rows: list[dict], actor: Optional[str]) -> None:
        self._bandwidth_repo.merge(rows)
        self._audit_repo.log(
            actor, "import_bandwidth", {"count": len(rows), "mode": "merge"}
        )
