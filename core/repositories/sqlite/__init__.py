"""
SQLite implementations of the ConfigForge repository interfaces.

Each concrete class in this package accepts a ``sqlite3.Connection`` and a
``threading.Lock`` at construction time, keeping the global-connection
strategy that the existing ``storage.py`` uses while making it injectable
and therefore testable.
"""
from core.repositories.sqlite.device import SQLiteDeviceRepository
from core.repositories.sqlite.bandwidth import SQLiteBandwidthRepository
from core.repositories.sqlite.subnet import SQLiteSubnetRepository
from core.repositories.sqlite.tag import SQLiteTagRepository
from core.repositories.sqlite.audit import SQLiteAuditRepository
from core.repositories.sqlite.history import SQLiteHistoryRepository
from core.repositories.sqlite.list import SQLiteListRepository
from core.repositories.sqlite.meta import SQLiteMetaRepository

__all__ = [
    "SQLiteDeviceRepository",
    "SQLiteBandwidthRepository",
    "SQLiteSubnetRepository",
    "SQLiteTagRepository",
    "SQLiteAuditRepository",
    "SQLiteHistoryRepository",
    "SQLiteListRepository",
    "SQLiteMetaRepository",
]
