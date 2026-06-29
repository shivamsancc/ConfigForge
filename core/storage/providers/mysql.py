"""
MySQL / MariaDB storage provider — scaffold implementation.

Status: SCAFFOLD — interface complete, not yet functional.

To implement
------------
1. Add ``mysqlclient`` or ``PyMySQL`` to requirements.
2. Implement ``_build_engine()`` using ``config.connection_url``.
3. Wire migrations (Alembic or adapt migrations.py).
4. Remove the ``NotImplementedError`` from ``initialize()``.
5. Update driver / dialect strings in ``get_metadata()``.

Recommended connection URL format::

    mysql+pymysql://user:pass@host:3306/configfoundry
    mysql+mysqlconnector://user:pass@host:3306/configfoundry

MariaDB note
------------
MariaDB is largely compatible; use ``mariadb+mariadbconnector://`` dialect
or point ``mysql+pymysql://`` at MariaDB (it works for most operations).
The ``json_columns`` capability was introduced in MySQL 5.7 / MariaDB 10.2.
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


class MySQLProvider(StorageProvider):
    """
    MySQL / MariaDB storage provider scaffold.

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
            "MySQLProvider is not yet implemented.  "
            "See core/storage/providers/mysql.py for the implementation guide."
        )

    def shutdown(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Engine / session  (scaffold)
    # ------------------------------------------------------------------

    def get_engine(self) -> "Engine":
        raise RuntimeError(
            "MySQLProvider is not initialised.  "
            "Call initialize() first — but note this provider is a scaffold."
        )

    def get_session_factory(self) -> "sessionmaker":
        raise RuntimeError(
            "MySQLProvider is not initialised.  "
            "Call initialize() first — but note this provider is a scaffold."
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message=(
                "MySQLProvider is a scaffold and has no active connection.  "
                "Implement initialize() to enable health checks."
            ),
            details={"provider": "mysql", "status": "scaffold"},
        )

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="mysql",
            version="unknown",
            driver="pymysql",           # recommended driver
            dialect="mysql",
            capabilities=self.get_capabilities(),
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            transactions=True,          # InnoDB engine
            migrations=True,
            full_text_search=True,      # FULLTEXT index (InnoDB 5.6+)
            json_columns=True,          # JSON type (MySQL 5.7+, MariaDB 10.2+)
            array_columns=False,        # no native ARRAY type
            schemas=True,               # MySQL databases as pseudo-schemas
            read_replicas=True,         # MySQL replication
            row_level_security=False,   # no native RLS (use views / plugins)
        )
