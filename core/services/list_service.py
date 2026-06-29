"""
List service — business logic for managed dropdown lists.

Only Collector Region remains a hardcoded, mandatory list concept; all
other categorisations live in the tag system.  The service enforces the
FIXED_LISTS allowlist and provides cross-referencing usage counts.
"""
from typing import Optional

from core.repositories.interfaces import IListRepository, IDeviceRepository, IAuditRepository
from core.repositories.sqlite.list import FIXED_LISTS

# Re-export so callers can import from the service layer without knowing
# which repository module defines the constant.
__all__ = ["ListService", "FIXED_LISTS"]


class ListService:
    """Orchestrates managed-list operations with validation and audit logging."""

    # Same constant the original storage.py exposed as FIXED_LISTS.
    FIXED_LISTS: tuple[str, ...] = FIXED_LISTS

    def __init__(
        self,
        list_repo: IListRepository,
        device_repo: IDeviceRepository,
        audit_repo: IAuditRepository,
    ) -> None:
        self._list_repo = list_repo
        self._device_repo = device_repo
        self._audit_repo = audit_repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_lists(self) -> dict:
        return self._list_repo.get_all()

    def usage_count(self, list_name: str, value: str) -> int:
        """How many devices currently have *value* set for this list's field.

        Collector Region is the only fixed list — it maps directly to the
        ``Collector Region`` device field.
        """
        field_map: dict[str, str] = {"collectorRegions": "Collector Region"}
        field = field_map.get(list_name)
        if not field:
            return 0
        return sum(
            1 for d in self._device_repo.list_all() if d.get(field) == value
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def set_list(
        self, list_name: str, items: list, actor: Optional[str]
    ) -> list:
        """Replace the items for a managed list.

        Raises
        ------
        ValueError
            When *list_name* is not in FIXED_LISTS.
        """
        if list_name not in FIXED_LISTS:
            raise ValueError(f"unknown list '{list_name}'")
        self._list_repo.set_list(list_name, items)
        self._audit_repo.log(
            actor,
            "update_list",
            {"list": list_name, "items": items},
        )
        return items
