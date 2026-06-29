"""
Microsoft SQL Server storage provider — scaffold (Enterprise tier).

Status: SCAFFOLD — interface complete, not yet functional.

This provider targets SQL Server 2019+ via pyodbc / ODBC Driver 18.
It is designed for enterprise deployments where Always On availability
groups, row-level security, and schema-based multi-tenancy are required.

To implement
------------
1. Install ODBC Driver 18 for SQL Server on the host OS.
2. Add ``pyodbc`` and ``mssql-pyodbc`` to requirements.
3. Implement ``_build_engine()`` using ``config.connection_url``.
4. Wire Alembic migrations (preferred for SQL Server).
5. Remove the ``NotImplementedError`` from ``initialize()``.

Recommended connection URL format::

    mssql+pyodbc://user:pass@host:1433/configfoundry?driver=ODBC+Driver+18+for+SQL+Server

Windows Authentication::

    mssql+pyodbc://@host/configfoundry?driver=ODBC+Driver+18+for+SQL+Server&Trusted_Connection=yes

Azure SQL::

    mssql+pyodbc://user:pass@server.database.windows.net/db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes

Enterprise features
-------------------
- Always On Availability Groups → read replica routing via
  ``ApplicationIntent=ReadOnly`` in the connection string.
- Row-Level Security → native SQL Server RLS policies.
- Schema-based multi-tenancy → per-tenant schemas within one database.
- Transparent Data Encryption (TDE) → at-rest encryption.
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


class SQLServerProvider(StorageProvider):
    """
    SQL Server storage provider scaffold (Enterprise tier).

    Raises ``NotImplementedError`` when ``initialize()`` is called.
    All metadata and capability queries work without a live connection.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Lifecycle  (scaffold)
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        raise NotImplementedError(
            "SQLServerProvider is not yet implemented.  "
            "See core/storage/providers/sqlserver.py for the implementation guide."
        )

    def shutdown(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Engine / session  (scaffold)
    # ------------------------------------------------------------------

    def get_engine(self) -> "Engine":
        raise RuntimeError(
            "SQLServerProvider is not initialised.  "
            "Call initialize() first — but note this provider is a scaffold."
        )

    def get_session_factory(self) -> "sessionmaker":
        raise RuntimeError(
            "SQLServerProvider is not initialised.  "
            "Call initialize() first — but note this provider is a scaffold."
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message=(
                "SQLServerProvider is a scaffold and has no active connection.  "
                "Implement initialize() to enable health checks."
            ),
            details={"provider": "sqlserver", "status": "scaffold"},
        )

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="sqlserver",
            version="unknown",
            driver="pyodbc",
            dialect="mssql",
            capabilities=self.get_capabilities(),
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            transactions=True,
            migrations=True,
            full_text_search=True,      # Full-Text Search (FTS)
            json_columns=True,          # OPENJSON / FOR JSON
            array_columns=False,        # no native ARRAY (use table-valued params)
            schemas=True,               # multi-schema (dbo, etc.)
            read_replicas=True,         # Always On AG read-replicas
            row_level_security=True,    # native RLS (SQL Server 2016+)
        )
