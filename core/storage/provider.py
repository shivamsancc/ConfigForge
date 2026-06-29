"""
Storage Provider interface.

``StorageProvider`` is the single abstraction between the repository layer
and any concrete database backend.  Repositories call ``provider.get_engine()``
and never import a database-specific library directly.

Design principles
-----------------
* **Inversion of Control**: repositories depend on this interface, not on
  SQLite/PostgreSQL/MySQL/SQL Server.
* **Capability introspection**: callers can ask a provider what it supports
  (JSON columns, FTS, read-replicas, etc.) without knowing its concrete type.
* **Health observability**: the ``health_check()`` method enables liveness/
  readiness probes without coupling monitoring code to any DB driver.
* **Lifecycle management**: ``initialize()`` / ``shutdown()`` give providers
  control over migration, pooling, and clean teardown.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class HealthStatus(Enum):
    """Coarse health signal returned by ``StorageProvider.health_check()``."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"       # connected but slow / degraded
    UNHEALTHY = "unhealthy"     # cannot connect or not implemented


@dataclass
class HealthCheckResult:
    """Full result of a health probe."""
    status: HealthStatus
    message: str
    latency_ms: Optional[float] = None
    details: Optional[dict] = None

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY


# ---------------------------------------------------------------------------
# Provider capabilities
# ---------------------------------------------------------------------------

@dataclass
class ProviderCapabilities:
    """
    Feature matrix for a storage backend.

    Repositories and services must never branch on these flags — they are
    exposed purely for observability, documentation, and future enterprise
    feature gates.
    """
    transactions: bool = True
    migrations: bool = True
    full_text_search: bool = False
    json_columns: bool = False      # native JSON column type / operators
    array_columns: bool = False     # native ARRAY column type
    schemas: bool = False           # multi-schema / multi-catalog support
    read_replicas: bool = False     # built-in read-replica routing
    row_level_security: bool = False  # database-native RLS


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------

@dataclass
class ProviderMetadata:
    """
    Static and runtime information about a storage provider.

    ``version`` may be ``"unknown"`` for scaffold providers that are not yet
    connected to a live database.
    """
    name: str                       # e.g. "sqlite", "postgresql"
    version: str                    # e.g. "3.42.0", "16.1", "unknown"
    driver: str                     # e.g. "aiosqlite", "psycopg2", "pyodbc"
    dialect: str                    # SQLAlchemy dialect string
    capabilities: ProviderCapabilities = field(
        default_factory=ProviderCapabilities
    )


# ---------------------------------------------------------------------------
# Abstract storage provider
# ---------------------------------------------------------------------------

class StorageProvider(ABC):
    """
    Abstract interface every database backend must satisfy.

    Lifecycle
    ---------
    1. Instantiate with a ``DatabaseConfig``.
    2. Call ``initialize()`` — runs migrations, sets up the engine.
    3. Inject into repositories / ``ServiceContainer``.
    4. Call ``shutdown()`` on application exit (releases connection pool).

    Repositories only ever call ``get_engine()`` (and optionally
    ``get_session_factory()``); everything else is infrastructure.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def initialize(self) -> None:
        """
        Prepare the storage backend for use.

        Implementations must:
        - Create / open the database connection.
        - Run any pending schema migrations.
        - Ensure required seed rows exist (e.g. fixed dropdown lists).

        Raises ``NotImplementedError`` for scaffold providers that are not
        yet fully implemented.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Release the connection pool and free all resources."""

    # ------------------------------------------------------------------
    # Engine / session access  (called by repositories)
    # ------------------------------------------------------------------

    @abstractmethod
    def get_engine(self) -> Engine:
        """
        Return the active SQLAlchemy ``Engine``.

        Must be called after ``initialize()``.  Repositories use this engine
        to open short-lived ``Session`` objects per operation.
        """

    @abstractmethod
    def get_session_factory(self) -> sessionmaker:
        """
        Return a ``sessionmaker`` bound to the active engine.

        Useful when a caller needs explicit session lifecycle control
        (e.g. Unit of Work spanning multiple repository calls in a single
        request).  Prefer ``get_engine()`` for simple per-operation sessions.
        """

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @abstractmethod
    def health_check(self) -> HealthCheckResult:
        """
        Perform a lightweight connectivity probe and return the result.

        Must not raise exceptions — failure is encoded in the returned
        ``HealthCheckResult`` with ``status=HealthStatus.UNHEALTHY``.
        """

    @abstractmethod
    def get_metadata(self) -> ProviderMetadata:
        """
        Return static and runtime metadata about this provider.

        Safe to call before ``initialize()``; ``version`` will be
        ``"unknown"`` if no live connection exists.
        """

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """
        Return the feature matrix for this backend.

        Safe to call before ``initialize()`` — capabilities are a static
        property of the backend type, not the connection state.
        """

    # ------------------------------------------------------------------
    # Convenience helpers (concrete, non-abstract)
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Short provider name — delegates to ``get_metadata().name``."""
        return self.get_metadata().name

    def __repr__(self) -> str:
        return f"<{type(self).__name__} provider={self.name!r}>"
