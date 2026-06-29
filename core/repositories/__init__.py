"""
Repository layer: abstract interfaces for all ConfigForge persistence entities.

Import the interfaces from here; import concrete SQLite implementations from
core.repositories.sqlite when you need to wire up the actual implementations.

Usage example (in container.py)::

    from core.repositories.interfaces import IDeviceRepository
    from core.repositories.sqlite.device import SQLiteDeviceRepository

    device_repo: IDeviceRepository = SQLiteDeviceRepository(conn, lock)
"""
from core.repositories.interfaces import (
    IDeviceRepository,
    IBandwidthRepository,
    ISubnetRepository,
    ITagRepository,
    IAuditRepository,
    IHistoryRepository,
    IListRepository,
    IMetaRepository,
)

__all__ = [
    "IDeviceRepository",
    "IBandwidthRepository",
    "ISubnetRepository",
    "ITagRepository",
    "IAuditRepository",
    "IHistoryRepository",
    "IListRepository",
    "IMetaRepository",
]
