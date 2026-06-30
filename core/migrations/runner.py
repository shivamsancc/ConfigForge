"""
Alembic migration runner for ConfigFoundry.

All storage providers call ``run_migrations(engine)`` during their
``initialize()`` method to apply any pending database schema migrations.
No provider contains migration logic of its own.

Migration flow
--------------
::

    StorageProvider.initialize()
            │
            ▼
    run_migrations(engine)
            │
            ├─ alembic_version table exists?
            │       └─ YES → alembic upgrade head   (normal: no-op or applies pending)
            │
            ├─ app tables exist but no alembic_version?
            │       └─ YES → alembic stamp head     (legacy DB, already up to date)
            │
            └─ no app tables, no alembic_version?
                    └─ YES → alembic upgrade head   (fresh DB, creates all tables)

Legacy database detection
-------------------------
Databases created by the legacy ``core/migrations_legacy.py`` system (present
before Alembic was introduced) have all application tables but no
``alembic_version`` table.  Detecting the ``meta`` table (created by the very
first migration) is a reliable proxy for "this DB was already set up."

Stamping writes the baseline revision ID to ``alembic_version`` without
running any DDL.  Subsequent calls see ``alembic_version`` and treat the DB
as Alembic-managed.

SQLite ``:memory:`` support
----------------------------
The runner always uses the **existing** SQLAlchemy connection from the
provided engine rather than constructing a second engine from the URL.
This guarantees that ``:memory:`` databases, which are private to the
connection that created them, work correctly in tests.

Thread safety
-------------
``run_migrations`` is called once during startup before any request is
served.  Multiple concurrent calls are safe because Alembic serialises
``alembic_version`` writes using ``BEGIN EXCLUSIVE`` on SQLite and
advisory locks on PostgreSQL.

CLI equivalents
---------------
::

    alembic upgrade head                 # apply pending migrations
    alembic current                      # show current version
    alembic history --indicate-current   # show full history
    alembic downgrade -1                 # roll back one migration
    alembic stamp head                   # mark DB as current (no DDL)
    alembic revision --autogenerate \\
        -m "add column foo to devices"   # generate new migration from model diff
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy import Engine, inspect, text

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _alembic_ini_path() -> str:
    """
    Return the absolute path to ``alembic.ini`` at the project root.

    Works regardless of the current working directory, which may vary
    between production startup, test runs, and CLI invocations.
    """
    # runner.py is at: <project>/core/migrations/runner.py
    # alembic.ini is at: <project>/alembic.ini
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "alembic.ini"))


def _make_alembic_config(url: Optional[str] = None):
    """
    Build an Alembic ``Config`` object pointing at the project's ``alembic.ini``.

    ``url`` is set as ``sqlalchemy.url`` when provided, but is overridden
    at runtime by the connection passed via ``config.attributes["connection"]``.
    """
    from alembic.config import Config

    ini_path = _alembic_ini_path()
    cfg = Config(ini_path)

    if url is not None:
        cfg.set_main_option("sqlalchemy.url", str(url))

    return cfg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_migrations(engine: Engine) -> None:
    """
    Apply all pending Alembic migrations to the database reached by *engine*.

    This is the single entry point for all storage providers.  It handles
    three cases transparently:

    1. **Fresh database** — no tables exist → runs ``upgrade head``,
       creating all tables defined in the Alembic migration history.

    2. **Legacy database** — app tables exist but no ``alembic_version``
       table (database was set up by the old ``core/migrations_legacy.py``
       system) → runs ``stamp head``, marking the database as current
       without any DDL changes.

    3. **Alembic-managed database** — ``alembic_version`` already exists
       → runs ``upgrade head``, which is a no-op if already at head or
       applies any pending revisions.

    Parameters
    ----------
    engine:
        A connected SQLAlchemy ``Engine``.  The runner reuses the engine's
        connection pool; it does NOT create a second engine from a URL.

    Raises
    ------
    Exception
        Propagates any exception raised by Alembic during migration
        execution.  The caller (storage provider) is responsible for
        aborting startup on failure.
    """
    from alembic import command

    cfg = _make_alembic_config(str(engine.url))

    with engine.connect() as conn:
        insp = inspect(engine)
        table_names = set(insp.get_table_names())

        has_alembic_version = "alembic_version" in table_names
        has_app_tables = "meta" in table_names   # proxy for "legacy DB"

        if not has_alembic_version and has_app_tables:
            # ----------------------------------------------------------------
            # Legacy database (pre-Alembic, already fully migrated by the
            # old custom system).  Stamp it at head so Alembic knows it's
            # up-to-date without touching any data or schema.
            # ----------------------------------------------------------------
            _logger.info(
                "Existing database detected (no alembic_version table). "
                "Stamping at Alembic head revision — no schema changes will be made."
            )
            cfg.attributes["connection"] = conn
            command.stamp(cfg, "head")
            _logger.info("Database stamped at head — Alembic tracking is now active.")
            return

        # -------------------------------------------------------------------
        # Fresh DB (no tables) or already Alembic-managed DB.
        # upgrade head: runs all pending migrations, or is a no-op if current.
        # -------------------------------------------------------------------
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def get_current_revision(engine: Engine) -> Optional[str]:
    """
    Return the current Alembic revision string for *engine*, or ``None``
    if the database has no ``alembic_version`` table.

    Useful for health checks and startup diagnostics.
    """
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        heads = ctx.get_current_heads()
        return heads[0] if heads else None


def get_pending_revisions(engine: Engine) -> list[str]:
    """
    Return a list of revision IDs that have not yet been applied to *engine*.

    An empty list means the database is at head.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = _make_alembic_config(str(engine.url))
    script = ScriptDirectory.from_config(cfg)

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current = set(ctx.get_current_heads())

    pending = []
    for rev in script.walk_revisions():
        if rev.revision not in current:
            pending.append(rev.revision)

    return list(reversed(pending))
