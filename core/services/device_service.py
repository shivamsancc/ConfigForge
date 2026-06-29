"""
Device service — business logic for device CRUD operations.

Responsibilities
----------------
- Validate IP address format before persistence (raises ValueError on failure
  so that HTTP routes can map it to a 400 response uniformly).
- Delegate persistence to IDeviceRepository.
- Write an audit log entry for every mutation via IAuditRepository.
- Remain completely ignorant of SQLite, HTTP, or response encoding.
"""
from typing import Optional

from core.logic import is_valid_ip
from core.repositories.interfaces import IDeviceRepository, IAuditRepository


class DeviceService:
    """Orchestrates device CRUD with validation and audit logging."""

    def __init__(
        self,
        device_repo: IDeviceRepository,
        audit_repo: IAuditRepository,
    ) -> None:
        self._device_repo = device_repo
        self._audit_repo = audit_repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_devices(self) -> list[dict]:
        return self._device_repo.list_all()

    def get_device(self, device_id: str) -> Optional[dict]:
        return self._device_repo.get(device_id)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_or_update(self, device: dict, actor: Optional[str]) -> dict:
        """Validate and persist a device record.

        Raises
        ------
        ValueError
            When the supplied IP address string is not a valid IP.
        """
        ip = (device.get("IP") or "").strip()
        if ip and not is_valid_ip(ip):
            raise ValueError(f"'{ip}' is not a valid IP address")
        is_create = not device.get("id")
        saved = self._device_repo.upsert(device)
        self._audit_repo.log(
            actor,
            "create_device" if is_create else "update_device",
            {"id": saved["id"], "ip": saved.get("IP")},
        )
        return saved

    def delete(self, device_id: str, actor: Optional[str]) -> None:
        self._device_repo.delete(device_id)
        self._audit_repo.log(actor, "delete_device", {"id": device_id})

    def replace_all(self, devices: list[dict], actor: Optional[str]) -> None:
        self._device_repo.replace_all(devices)
        self._audit_repo.log(
            actor, "import_devices", {"count": len(devices), "mode": "replace"}
        )

    def merge(self, devices: list[dict], actor: Optional[str]) -> None:
        self._device_repo.merge(devices)
        self._audit_repo.log(
            actor, "import_devices", {"count": len(devices), "mode": "merge"}
        )
