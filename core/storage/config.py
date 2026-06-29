"""
Centralised database configuration for ConfigFoundry.

``DatabaseConfig`` holds all connection parameters for a single storage
backend.  ``AppConfig`` is the application-level configuration root.

Loading priority (highest wins)
---------------------------------
1. Explicit constructor kwargs / ``from_dict()``
2. Environment variables (``CONFIGFORGE_DB_*``, ``CONFIGFORGE_LOG_*``)
3. YAML configuration file (``--config`` flag or ``CONFIGFORGE_CONFIG`` env var)
4. Built-in defaults

Environment variables
---------------------
``CONFIGFORGE_DB_PROVIDER``     — sqlite | postgresql | mysql | sqlserver
``CONFIGFORGE_DB_SQLITE_PATH``  — path to .db file (SQLite only)
``CONFIGFORGE_DB_URL``          — full connection URL (non-SQLite providers)
``CONFIGFORGE_DB_POOL_SIZE``    — integer, connection pool size (default 5)
``CONFIGFORGE_DB_MAX_OVERFLOW`` — integer, pool overflow (default 10)
``CONFIGFORGE_DB_ECHO``         — true | false, SQLAlchemy statement logging

See ``core/logging/config.py`` for ``CONFIGFORGE_LOG_*`` variables.

YAML example
------------
::

    database:
      provider: sqlite
      sqlite_path: ./db/configforge.db

    logging:
      level: INFO
      file: logs/configfoundry.log
      console: true
      rotation: daily
      backup_count: 7

    # or for PostgreSQL (future):
    database:
      provider: postgresql
      connection_url: postgresql+psycopg2://user:pass@host:5432/configforge
      pool_size: 10
      max_overflow: 20
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from core.logging.config import LoggingConfig


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

@dataclass
class DatabaseConfig:
    """
    All parameters needed to create a ``StorageProvider``.

    Attributes
    ----------
    provider:
        Backend name.  Must match a key registered in ``StorageFactory``.
        Case-insensitive.  Default: ``"sqlite"``.
    sqlite_path:
        File path for the SQLite database.  Use ``":memory:"`` for tests.
        Ignored for non-SQLite providers.
    connection_url:
        Full SQLAlchemy URL for non-SQLite providers.
        E.g. ``"postgresql+psycopg2://user:pass@host:5432/db"``.
    pool_size:
        Number of persistent connections in the pool (non-SQLite only).
    max_overflow:
        Extra connections allowed above *pool_size* under high load.
    echo:
        When ``True`` SQLAlchemy logs every SQL statement.  Useful for
        debugging, never enable in production.
    connect_args:
        Driver-specific keyword arguments passed to ``create_engine()``
        via ``connect_args``.  Providers may merge their own defaults.
    """

    provider: str = "sqlite"
    sqlite_path: str = "db/configforge.db"
    connection_url: Optional[str] = None
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False
    connect_args: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory class-methods
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "DatabaseConfig":
        """
        Build a ``DatabaseConfig`` from a plain dictionary.

        Unknown keys are silently ignored so YAML files can contain
        comments or future fields without breaking older code.
        """
        known = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """
        Build a ``DatabaseConfig`` from ``CONFIGFORGE_DB_*`` environment
        variables.  Missing variables fall back to dataclass defaults.
        """
        kwargs: dict = {}

        if v := os.environ.get("CONFIGFORGE_DB_PROVIDER"):
            kwargs["provider"] = v
        if v := os.environ.get("CONFIGFORGE_DB_SQLITE_PATH"):
            kwargs["sqlite_path"] = v
        if v := os.environ.get("CONFIGFORGE_DB_URL"):
            kwargs["connection_url"] = v
        if v := os.environ.get("CONFIGFORGE_DB_POOL_SIZE"):
            kwargs["pool_size"] = int(v)
        if v := os.environ.get("CONFIGFORGE_DB_MAX_OVERFLOW"):
            kwargs["max_overflow"] = int(v)
        if v := os.environ.get("CONFIGFORGE_DB_ECHO"):
            kwargs["echo"] = v.strip().lower() in ("true", "1", "yes")

        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Application-level configuration root
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    """
    Top-level configuration object for ConfigFoundry.

    Attributes
    ----------
    database:
        Database connection parameters.
    logging:
        Logging framework configuration (level, file, rotation, etc.).
        Parsed from the ``logging:`` section of the YAML config file or
        ``CONFIGFORGE_LOG_*`` environment variables.
    """

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # ------------------------------------------------------------------
    # Factory class-methods
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """Build an ``AppConfig`` from a nested dictionary."""
        db_data  = data.get("database", {})
        log_data = data.get("logging", {})
        return cls(
            database=DatabaseConfig.from_dict(db_data),
            logging=LoggingConfig.from_dict(log_data),
        )

    @classmethod
    def from_env(cls) -> "AppConfig":
        """
        Build an ``AppConfig`` from environment variables.

        Reads ``CONFIGFORGE_DB_*`` for the database section and
        ``CONFIGFORGE_LOG_*`` for the logging section.
        """
        return cls(
            database=DatabaseConfig.from_env(),
            logging=LoggingConfig.from_env(),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "AppConfig":
        """
        Load configuration from a YAML file.

        Requires PyYAML (``pip install pyyaml``).  Raises ``ImportError``
        with a clear message if it is not installed.

        Example YAML::

            database:
              provider: sqlite
              sqlite_path: ./db/configforge.db
        """
        try:
            import yaml  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load YAML configuration files.  "
                "Install it with: pip install pyyaml"
            ) from exc

        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        return cls.from_dict(data)

    @classmethod
    def for_sqlite(cls, db_path: str) -> "AppConfig":
        """
        Convenience constructor: build an ``AppConfig`` for a SQLite file.

        Used internally by ``ServiceContainer`` for backward-compatible
        ``ServiceContainer(db_path="...")`` call sites.
        """
        return cls(database=DatabaseConfig(provider="sqlite", sqlite_path=db_path))
