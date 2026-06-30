"""
SQLite storage provider — fully functional implementation.

Schema management is delegated entirely to Alembic via
``core.migrations.runner.run_migrations(engine)``.  This provider no
longer contains migration logic of its own.

Startup sequence
----------------
1. Build a SQLAlchemy engine (WAL mode enabled).
2. Run ``core.migrations.runner.run_migrations(engine)``.
   - Fresh databases: ``alembic upgrade head`` creates all tables.
   - Legacy databases (pre-Alembic): stamped at head, no DDL changes.
   - Alembic-managed databases: ``alembic upgrade head`` is a no-op
     if already at head, or applies pending migrations.
3. Seed fixed Collector Region list row (``INSERT OR IGNORE``).
4. Build a reusable session factory.

Thread safety
-------------
SQLAlchemy's connection pool handles threading.  ``check_same_thread=False``
is set on the DBAPI connection so the pool can hand it to any thread, but
the pool itself serialises concurrent access correctly.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from core.logging import get_logger
from core.migrations.runner import run_migrations
from core.storage.config import DatabaseConfig
from core.storage.provider import (
    HealthCheckResult,
    HealthStatus,
    ProviderCapabilities,
    ProviderMetadata,
    StorageProvider,
)

_logger = get_logger(__name__)

# Fixed lists that must always exist in the ``lists`` table.
# Imported here to stay co-located with seeding logic.
from core.repositories.sqlite.list import FIXED_LISTS


class SQLiteProvider(StorageProvider):
    """
    Fully functional SQLite storage provider.

    Supports ``":memory:"`` databases for in-process testing (each
    ``ServiceContainer`` instance gets a fully initialised, isolated
    in-memory database).

    Parameters
    ----------
    config:
        A ``DatabaseConfig`` with ``provider="sqlite"``.
        ``config.sqlite_path`` is the file path (or ``":memory:"``).
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: Optional[Engine] = None
        self._session_factory_obj: Optional[sessionmaker] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Build the engine, run Alembic migrations, and seed fixed data.

        Idempotent: calling ``initialize()`` more than once re-initialises
        the engine (safe for test fixtures that call it repeatedly).
        """
        db_path = self._config.sqlite_path

        # Step 1: Build the SQLAlchemy engine.
        # Engine is built FIRST so we can pass it to the migration runner,
        # which reuses the same connection pool (essential for :memory: DBs).
        self._engine = self._build_engine(db_path)

        # Step 2: Run Alembic migrations.
        # - Fresh DBs: creates all tables via baseline migration.
        # - Legacy DBs (meta table exists, no alembic_version): stamps head.
        # - Managed DBs: upgrade head (no-op or applies pending revisions).
        _logger.info("Running database migrations for %s", db_path)
        run_migrations(self._engine)

        # Step 3: Build a reusable session factory.
        self._session_factory_obj = sessionmaker(bind=self._engine)

        # Step 4: Seed fixed lists (idempotent — INSERT OR IGNORE).
        self._seed_fixed_lists()

    def shutdown(self) -> None:
        """Dispose the connection pool and release all file handles."""
        if self._engine is not None:
            _logger.info("Shutting down SQLiteProvider for %s", self._config.sqlite_path)
            self._engine.dispose()
            self._engine = None
            self._session_factory_obj = None

    # ------------------------------------------------------------------
    # Engine / session access
    # ------------------------------------------------------------------

    def get_engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError(
                "SQLiteProvider has not been initialised.  "
                "Call initialize() before get_engine()."
            )
        return self._engine

    def get_session_factory(self) -> sessionmaker:
        if self._session_factory_obj is None:
            raise RuntimeError(
                "SQLiteProvider has not been initialised.  "
                "Call initialize() before get_session_factory()."
            )
        return self._session_factory_obj

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """
        Execute ``SELECT 1`` and measure round-trip latency.

        Returns ``UNHEALTHY`` if the engine is not initialised or if the
        probe fails — never raises an exception.
        """
        if self._engine is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="Provider not initialised — call initialize() first.",
            )
        try:
            start = time.perf_counter()
            with Session(self._engine) as session:
                session.execute(text("SELECT 1"))
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="OK",
                latency_ms=round(latency_ms, 3),
                details={"path": self._config.sqlite_path},
            )
        except Exception as exc:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=str(exc),
                details={"path": self._config.sqlite_path},
            )

    def get_metadata(self) -> ProviderMetadata:
        version = self._query_version()
        return ProviderMetadata(
            name="sqlite",
            version=version,
            driver="sqlite3",
            dialect="sqlite",
            capabilities=self.get_capabilities(),
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            transactions=True,
            migrations=True,
            full_text_search=True,      # SQLite FTS5
            json_columns=True,          # JSON1 extension (built-in since 3.38)
            array_columns=False,
            schemas=False,              # no multi-schema
            read_replicas=False,
            row_level_security=False,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_engine(self, db_path: str) -> Engine:
        """Create the SQLAlchemy engine with WAL mode and correct connect args."""
        connect_args = {"check_same_thread": False}
        connect_args.update(self._config.connect_args)

        if db_path == ":memory:":
            # In-memory databases require StaticPool so all connections
            # (including Alembic's) share the same underlying DBAPI connection.
            from sqlalchemy.pool import StaticPool
            engine = create_engine(
                "sqlite:///:memory:",
                connect_args=connect_args,
                poolclass=StaticPool,
                echo=self._config.echo,
            )
        else:
            engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args=connect_args,
                echo=self._config.echo,
            )

        # Enable WAL journal mode on every new DBAPI connection.
        @event.listens_for(engine, "connect")
        def _set_wal(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

        return engine

    def _seed_fixed_lists(self) -> None:
        """
        Ensure the Collector Region managed list row exists.

        Uses ``INSERT OR IGNORE`` semantics via SQLAlchemy so it is safe
        to call on every startup without duplicating data.
        """
        from models.inventory import ListModel

        with Session(self._engine) as session:
            for name in FIXED_LISTS:
                if session.get(ListModel, name) is None:
                    session.add(ListModel(list_name=name, items=json.dumps([])))
            session.commit()

    def _query_version(self) -> str:
        """Return the SQLite library version string, or ``"unknown"``."""
        if self._engine is None:
            return sqlite3.sqlite_version
        try:
            with Session(self._engine) as session:
                row = session.execute(text("SELECT sqlite_version()")).fetchone()
            return row[0] if row else "unknown"
        except Exception:
            return "unknown"
