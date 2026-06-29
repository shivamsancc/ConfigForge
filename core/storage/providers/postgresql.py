"""
PostgreSQL storage provider — scaffold implementation.

Status: SCAFFOLD — interface complete, not yet functional.

This provider satisfies the ``StorageProvider`` interface so it can be
registered in the factory, introspected for capabilities, and used as
a target in integration tests once a PostgreSQL connection is available.

To implement
------------
1. Add ``psycopg2`` (or ``asyncpg``) to requirements.
2. Implement ``_build_engine()`` using the URL from ``config.connection_url``.
3. Replace the ``core.migrations`` sqlite3 runner with an Alembic runner
   (or adapt migrations.py to accept a SQLAlchemy connection).
4. Remove the ``NotImplementedError`` from ``initialize()``.
5. Update the ``driver`` / ``dialect`` in ``get_metadata()``.
6. Write integration tests against a real PostgreSQL instance (docker-compose).

Recommended connection URL format::

    postgresql+psycopg2://user:pass@host:5432/configfoundry

For async workloads::

    postgresql+asyncpg://user:pass@host:5432/configfoundry
"""
from __future__ import annotations

from core.storage.config import DatabaseConfig
from core.storage.provider import (
    HealthCheckResult,
    HealthStatus,
    ProviderCapabilities,
    ProviderMetadata,
    StorageProvider,
)

try:
    from sqlalchemy import Engine
    from sqlalchemy.orm import sessionmaker
except ImportError:
    Engine = None  # type: ignore[assignment,misc]
    sessionmaker = None  # type: ignore[assignment,misc]


class PostgreSQLProvider(StorageProvider):
    """
    PostgreSQL storage provider scaffold.

    Raises ``NotImplementedError`` when ``initialize()`` is called.
    All metadata and capability queries work without a live connection.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Lifecycle  (scaffold — not yet functional)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        raise NotImplementedError(
            "PostgreSQLProvider is not yet implemented.  "
            "See core/storage/providers/postgresql.py for the implementation guide."
        )

    def shutdown(self) -> None:
        pass  # nothing to release

    # ------------------------------------------------------------------
    # Engine / session  (scaffold)
    # ------------------------------------------------------------------

    def get_engine(self) -> "Engine":
        raise RuntimeError(
            "PostgreSQLProvider is not initialised.  "
            "Call initialize() first — but note this provider is a scaffold."
        )

    def get_session_factory(self) -> "sessionmaker":
        raise RuntimeError(
            "PostgreSQLProvider is not initialised.  "
            "Call initialize() first — but note this provider is a scaffold."
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message=(
                "PostgreSQLProvider is a scaffold and has no active connection.  "
                "Implement initialize() to enable health checks."
            ),
            details={"provider": "postgresql", "status": "scaffold"},
        )

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="postgresql",
            version="unknown",        # requires live connection
            driver="psycopg2",        # recommended driver
            dialect="postgresql",
            capabilities=self.get_capabilities(),
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            transactions=True,
            migrations=True,
            full_text_search=True,      # tsvector / tsquery
            json_columns=True,          # jsonb
            array_columns=True,         # native ARRAY type
            schemas=True,               # pg search_path / schemas
            read_replicas=True,         # streaming replication
            row_level_security=True,    # native RLS policies
        )
