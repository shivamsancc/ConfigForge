"""
Import service — bulk import and validate-import for all inventory scopes.

Validate-import is a read-only preview operation: it runs the validation
engine and diff engine over the proposed payload without writing to the
database.  The actual import delegates to the respective CRUD services so
that audit logging and any per-record business rules apply uniformly.
"""
from typing import Optional

from core.validator import validate_inventory
from core import diff as differ
from core.repositories.interfaces import (
    IDeviceRepository,
    IBandwidthRepository,
    ISubnetRepository,
    ITagRepository,
    IAuditRepository,
)
from core.services.device_service import DeviceService
from core.services.bandwidth_service import BandwidthService
from core.services.subnet_service import SubnetService


class ImportService:
    """
    Orchestrates bulk import and validate-import for devices, bandwidth,
    and subnets.
    """

    def __init__(
        self,
        device_service: DeviceService,
        bandwidth_service: BandwidthService,
        subnet_service: SubnetService,
        device_repo: IDeviceRepository,
        bandwidth_repo: IBandwidthRepository,
        subnet_repo: ISubnetRepository,
        tag_repo: ITagRepository,
    ) -> None:
        self._device_service = device_service
        self._bandwidth_service = bandwidth_service
        self._subnet_service = subnet_service
        self._device_repo = device_repo
        self._bandwidth_repo = bandwidth_repo
        self._subnet_repo = subnet_repo
        self._tag_repo = tag_repo

    # ------------------------------------------------------------------
    # Import (write)
    # ------------------------------------------------------------------

    def import_devices(
        self, devices: list[dict], mode: str, actor: Optional[str]
    ) -> dict:
        """Bulk-import devices using the supplied *mode* ('merge' or 'replace')."""
        self._validate_mode(mode)
        if mode == "replace":
            self._device_service.replace_all(devices, actor)
        else:
            self._device_service.merge(devices, actor)
        return {"imported": len(devices), "mode": mode}

    def import_bandwidth(
        self, rows: list[dict], mode: str, actor: Optional[str]
    ) -> dict:
        self._validate_mode(mode)
        if mode == "replace":
            self._bandwidth_service.replace_all(rows, actor)
        else:
            self._bandwidth_service.merge(rows, actor)
        return {"imported": len(rows), "mode": mode}

    def import_subnets(
        self, rows: list[dict], mode: str, actor: Optional[str]
    ) -> dict:
        self._validate_mode(mode)
        if mode == "replace":
            self._subnet_service.replace_all(rows, actor)
        else:
            self._subnet_service.merge(rows, actor)
        return {"imported": len(rows), "mode": mode}

    # ------------------------------------------------------------------
    # Validate-import (read-only preview)
    # ------------------------------------------------------------------

    def validate_import_devices(
        self, incoming: list[dict], mode: str
    ) -> dict:
        """Validate and diff proposed device rows without writing to the DB.

        Validation scope: imported rows only (existing bandwidth and subnets
        are excluded so orphan checks do not produce noise about data outside
        this import).
        """
        tag_defs = self._tag_repo.list_all()
        existing = self._device_repo.list_all()
        findings = validate_inventory(incoming, [], [], tag_defs)
        diff_result = differ.diff_import("devices", incoming, existing, mode, tag_defs)
        return {"findings": findings, "diff": diff_result}

    def validate_import_bandwidth(
        self, incoming: list[dict], mode: str
    ) -> dict:
        """Validate and diff proposed bandwidth rows without writing to the DB.

        Cross-references against the live device inventory so BW_ORPHANED
        findings are meaningful.
        """
        tag_defs = self._tag_repo.list_all()
        existing_devices = self._device_repo.list_all()
        existing_bw = self._bandwidth_repo.list_all()
        findings = validate_inventory(existing_devices, incoming, [], tag_defs)
        diff_result = differ.diff_import(
            "bandwidth", incoming, existing_bw, mode, tag_defs
        )
        return {"findings": findings, "diff": diff_result}

    def validate_import_subnets(
        self, incoming: list[dict], mode: str
    ) -> dict:
        """Validate and diff proposed subnet rows without writing to the DB."""
        tag_defs = self._tag_repo.list_all()
        existing = self._subnet_repo.list_all()
        findings = validate_inventory([], [], incoming, tag_defs)
        diff_result = differ.diff_import(
            "subnets", incoming, existing, mode, tag_defs
        )
        return {"findings": findings, "diff": diff_result}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_mode(mode: str) -> None:
        if mode not in ("merge", "replace"):
            raise ValueError("'mode' must be 'merge' or 'replace'")
