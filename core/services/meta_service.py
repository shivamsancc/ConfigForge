"""
Meta service — assembles the dashboard metadata summary.

Combines live record counts from the inventory repositories with the
lastSavedAt / lastSavedBy timestamps stored in the meta key-value table.
"""
from core.repositories.interfaces import (
    IDeviceRepository,
    IBandwidthRepository,
    ISubnetRepository,
    IMetaRepository,
)


class MetaService:
    """Assembles the /api/meta response from multiple repositories."""

    def __init__(
        self,
        device_repo: IDeviceRepository,
        bandwidth_repo: IBandwidthRepository,
        subnet_repo: ISubnetRepository,
        meta_repo: IMetaRepository,
    ) -> None:
        self._device_repo = device_repo
        self._bandwidth_repo = bandwidth_repo
        self._subnet_repo = subnet_repo
        self._meta_repo = meta_repo

    def get_meta(self) -> dict:
        return {
            "deviceCount": len(self._device_repo.list_all()),
            "bandwidthCount": len(self._bandwidth_repo.list_all()),
            "subnetCount": len(self._subnet_repo.list_all()),
            "lastSavedAt": self._meta_repo.get_kv("lastSavedAt"),
            "lastSavedBy": self._meta_repo.get_kv("lastSavedBy"),
        }
