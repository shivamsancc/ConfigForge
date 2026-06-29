"""
SQLite storage provider — fully functional implementation.

Absorbs the logic previously in ``core/db.py``:
- Run schema migrations via the existing ``core.migrations`` module
  (uses a raw sqlite3 connection — migrations.py pre-dates SQLAlchemy).
- Ensure the fixed Collector Region list row exists.
- Create a SQLAlchemy engine with WAL journal mode.
- Expose health checks with round-trip latency measurement.

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

from core.storage.config import DatabaseConfig
from core.storage.provider import (
    HealthCheckResult,
    HealthStatus,
    ProviderCapabilities,
    ProviderMetadata,
    StorageProvider,
)

# Fixed lists that must always exist in the ``lists`` table.
from core.repositories.sqlite.list import FIXED_LISTS


class SQLiteProvider(StorageProvider):
    """
    Fully functional SQLite storage provider.

    Supports ``":memory:"`` databases for in-process testing.

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
        Run migrations, ensure fixed seed rows, and create the engine.

        Safe to call multiple times — ``create_engine`` is idempotent when
        the engine already exists; migrations skip already-applied versions.
        """
        db_path = self._config.sqlite_path

        # Step 1: Run schema migrations using a raw sqlite3 connection.
        # migrations.py predates SQLAlchemy and must stay on the sqlite3 API.
        self._run_migrations(db_path)

        # Step 2: Create the SQLAlchemy engine.
        self._engine = self._build_engine(db_path)

        # Step 3: Build a reusable session factory.
        self._session_factory_obj = sessionmaker(bind=self._engine)

    def shutdown(self) -> None:
        """Dispose the connection pool and release all file handles."""
        if self._engine is not None:
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

    def _run_migrations(self, db_path: str) -> None:
        """Run pending migrations and seed fixed lists using raw sqlite3."""
        from core import migrations as _migrations

        raw = sqlite3.connect(db_path)
        raw.row_factory = sqlite3.Row
        try:
            _migrations.run_pending_migrations(raw)
            for name in FIXED_LISTS:
                raw.execute(
                    "INSERT OR IGNORE INTO lists (list_name, items) VALUES (?, ?)",
                    (name, json.dumps([])),
                )
            raw.commit()
        finally:
            raw.close()

    def _build_engine(self, db_path: str) -> Engine:
        """Create the SQLAlchemy engine with WAL mode and correct connect args."""
        connect_args = {"check_same_thread": False}
        connect_args.update(self._config.connect_args)

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

    def _query_version(self) -> str:
        """Return the SQLite library version string, or ``"unknown"``."""
        if self._engine is None:
            # Engine not yet built — ask the sqlite3 stdlib directly.
            return sqlite3.sqlite_version
        try:
            with Session(self._engine) as session:
                row = session.execute(text("SELECT sqlite_version()")).fetchone()
            return row[0] if row else "unknown"
        except Exception:
            return "unknown"
