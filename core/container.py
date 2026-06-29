"""
Dependency injection container for ConfigFoundry.

``ServiceContainer`` is the single place where the active ``StorageProvider``
is wired to repositories, and repositories are wired to services.

v0.5 Storage Abstraction changes
---------------------------------
* The container no longer creates a SQLAlchemy engine directly.
* Instead it delegates to ``StorageFactory.create(config.database)`` to
  obtain the correct ``StorageProvider`` for the configured backend.
* All eight repositories receive the provider (not the engine) via
  constructor injection.
* The public interface is identical to the pre-abstraction version so
  ``core/storage.py``, tests, and ``app.py`` require no changes.

Backward compatibility
-----------------------
Passing a plain ``db_path`` string still works::

    container = ServiceContainer(db_path="/path/to/configforge.db")

This is equivalent to::

    config = AppConfig.for_sqlite("/path/to/configforge.db")
    container = ServiceContainer(config=config)

Usage (in app.py / tests)::

    container = ServiceContainer(config=AppConfig.from_yaml("config.yaml"))
    container = ServiceContainer(db_path="db/configforge.db")   # compat
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Engine

from core.storage.config import AppConfig
from core.storage.factory import StorageFactory
from core.storage.provider import StorageProvider

# --- SQLAlchemy repository implementations ---
from core.repositories.sqlalchemy.device import SQLAlchemyDeviceRepository
from core.repositories.sqlalchemy.bandwidth import SQLAlchemyBandwidthRepository
from core.repositories.sqlalchemy.subnet import SQLAlchemySubnetRepository
from core.repositories.sqlalchemy.tag import SQLAlchemyTagRepository
from core.repositories.sqlalchemy.audit import SQLAlchemyAuditRepository
from core.repositories.sqlalchemy.history import SQLAlchemyHistoryRepository
from core.repositories.sqlalchemy.list import SQLAlchemyListRepository
from core.repositories.sqlalchemy.meta import SQLAlchemyMetaRepository

# --- Services (unchanged) ---
from core.services.device_service import DeviceService
from core.services.bandwidth_service import BandwidthService
from core.services.subnet_service import SubnetService
from core.services.tag_service import TagService
from core.services.list_service import ListService
from core.services.generate_service import GenerateService
from core.services.export_service import ExportService
from core.services.import_service import ImportService
from core.services.audit_service import AuditService
from core.services.history_service import HistoryService
from core.services.meta_service import MetaService


class ServiceContainer:
    """
    Constructs and owns all repositories and services for one database.

    Attributes are intentionally public so the HTTP layer can access them
    as ``container.<service_name>`` or ``container.<repo_name>``.

    Parameters
    ----------
    db_path:
        Backward-compatible shortcut: creates a SQLite provider from this
        path.  Mutually exclusive with *config* and *provider*.
    config:
        Full ``AppConfig``.  The factory selects the correct provider from
        ``config.database.provider``.  Mutually exclusive with *db_path*
        and *provider*.
    provider:
        An already-constructed and initialised ``StorageProvider``.
        Use this in tests or when you need direct control over the provider.
        Mutually exclusive with *db_path* and *config*.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        config: Optional[AppConfig] = None,
        provider: Optional[StorageProvider] = None,
    ) -> None:
        # ------------------------------------------------------------------
        # Resolve the storage provider
        # ------------------------------------------------------------------
        _given = sum(x is not None for x in (db_path, config, provider))
        if _given == 0:
            raise ValueError(
                "ServiceContainer requires one of: db_path, config, or provider."
            )
        if _given > 1:
            raise ValueError(
                "ServiceContainer accepts only one of: db_path, config, or provider."
            )

        if provider is not None:
            # Caller supplies a ready-made provider (tests / advanced usage).
            self._provider: StorageProvider = provider
        elif config is not None:
            self._provider = StorageFactory.create(config.database)
            self._provider.initialize()
        else:
            # Backward-compatible path: db_path string → SQLite provider.
            self._provider = StorageFactory.create(
                AppConfig.for_sqlite(db_path).database
            )
            self._provider.initialize()

        # ------------------------------------------------------------------
        # Backward-compat accessors
        # ------------------------------------------------------------------
        # Tests and legacy code may read container._engine.
        # Delegate to the provider rather than storing a direct reference.

        # ------------------------------------------------------------------
        # Repositories  (all receive the provider, not the engine)
        # ------------------------------------------------------------------
        self.device_repo = SQLAlchemyDeviceRepository(self._provider)
        self.bandwidth_repo = SQLAlchemyBandwidthRepository(self._provider)
        self.subnet_repo = SQLAlchemySubnetRepository(self._provider)
        self.tag_repo = SQLAlchemyTagRepository(self._provider)
        self.audit_repo = SQLAlchemyAuditRepository(self._provider)
        self.history_repo = SQLAlchemyHistoryRepository(self._provider)
        self.list_repo = SQLAlchemyListRepository(self._provider)
        self.meta_repo = SQLAlchemyMetaRepository(self._provider)

        # ------------------------------------------------------------------
        # Services  (repositories injected via constructors — unchanged)
        # ------------------------------------------------------------------
        self.audit_service = AuditService(self.audit_repo)

        self.device_service = DeviceService(self.device_repo, self.audit_repo)
        self.bandwidth_service = BandwidthService(self.bandwidth_repo, self.audit_repo)
        self.subnet_service = SubnetService(self.subnet_repo, self.audit_repo)

        self.tag_service = TagService(self.tag_repo, self.audit_repo)

        self.list_service = ListService(
            self.list_repo, self.device_repo, self.audit_repo
        )

        self.generate_service = GenerateService(
            self.device_repo,
            self.bandwidth_repo,
            self.subnet_repo,
            self.tag_repo,
            self.history_repo,
            self.meta_repo,
            self.audit_repo,
        )

        self.export_service = ExportService(
            self.device_repo,
            self.bandwidth_repo,
            self.subnet_repo,
            self.tag_repo,
        )

        self.import_service = ImportService(
            self.device_service,
            self.bandwidth_service,
            self.subnet_service,
            self.device_repo,
            self.bandwidth_repo,
            self.subnet_repo,
            self.tag_repo,
        )

        self.history_service = HistoryService(self.history_repo)

        self.meta_service = MetaService(
            self.device_repo,
            self.bandwidth_repo,
            self.subnet_repo,
            self.meta_repo,
        )

    # ------------------------------------------------------------------
    # Backward-compatibility properties
    # ------------------------------------------------------------------

    @property
    def _engine(self) -> Engine:
        """
        Expose the underlying SQLAlchemy engine.

        Kept for backward compatibility with tests that access
        ``container._engine`` directly (e.g. to inspect raw DB rows).
        New code should use ``container._provider.get_engine()`` instead.
        """
        return self._provider.get_engine()

    @property
    def _conn(self):
        """
        Legacy stub — always returns None.

        The raw sqlite3 connection is no longer held by the container.
        Tests that previously accessed ``container._conn`` have been updated
        to use ``container._engine``.  This property prevents AttributeError
        on any remaining call sites.
        """
        return None
