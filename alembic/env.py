"""
Alembic migration environment for ConfigFoundry.

This file is called by Alembic for every migration command (upgrade,
downgrade, revision --autogenerate, etc.) and configures the database
connection and migration context.

Two operating modes
-------------------
Programmatic (from ``core.migrations.runner``)
    The caller builds a SQLAlchemy engine, opens a connection, and passes
    it via ``config.attributes["connection"]``.  This lets all providers
    (including SQLite ``:memory:`` databases) share the same DBAPI
    connection and avoids creating a second engine.

CLI (``alembic upgrade head``, ``alembic revision --autogenerate``, etc.)
    No pre-existing connection is available.  The URL is read from:
    1. ``CONFIGFORGE_DB_URL`` environment variable
    2. ``sqlalchemy.url`` in ``alembic.ini``
    3. The ``--url`` CLI flag (Alembic handles this automatically)

SQLite batch mode
-----------------
SQLite does not support ``ALTER TABLE ... ADD COLUMN`` or column drops via
SQL.  Alembic's ``render_as_batch=True`` option wraps these operations in a
table-copy dance that works around this limitation.  It is a no-op for
PostgreSQL, MySQL, and SQL Server, so it is always safe to enable.

Autogenerate
------------
``Base.metadata`` from ``models.base`` is set as ``target_metadata`` so
``alembic revision --autogenerate`` compares the ORM model definitions to
the live database and generates a diff-based migration.

Usage examples
--------------
::

    # Apply all pending migrations (programmatic — never call directly):
    # runner.run_migrations(engine)

    # Apply all pending migrations (CLI):
    alembic upgrade head

    # Generate a new migration from model changes:
    alembic revision --autogenerate -m "add column foo to devices"

    # Show current database migration state:
    alembic current

    # Show pending migrations:
    alembic history --indicate-current

    # Roll back one migration:
    alembic downgrade -1
"""
from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so application modules are importable.
# This is also configured in alembic.ini via prepend_sys_path, but we add it
# here defensively for programmatic use where the INI may not have been loaded.
# ---------------------------------------------------------------------------
_project_root = os.path.join(os.path.dirname(__file__), "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Import all ORM models so their __tablename__s are registered with Base.metadata
# before Alembic inspects it for autogenerate comparisons.
from models.base import Base        # noqa: E402
from models.inventory import (      # noqa: E402, F401
    AuditLogModel,
    BandwidthCapModel,
    DeviceModel,
    ListModel,
    MetaModel,
    SubnetModel,
    TagDefModel,
    YamlHistoryModel,
)

# ---------------------------------------------------------------------------
# Alembic Config object — provides access to values in alembic.ini.
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging, if present.
# disable_existing_loggers=False preserves any application logging already
# configured by configure_logging() (e.g. the configfoundry.* hierarchy).
# Without this, fileConfig() would kill all existing loggers — breaking
# the logging middleware and all structured log output during migrations.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The metadata used by --autogenerate to compare model definitions to the
# live database schema.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_url() -> str:
    """
    Resolve the database URL for CLI usage.

    Priority:
    1. ``CONFIGFORGE_DB_URL`` environment variable
    2. ``sqlalchemy.url`` in ``alembic.ini``
    """
    env_url = os.environ.get("CONFIGFORGE_DB_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url", "sqlite:///db/configforge.db")


def _configure_context(connection) -> None:
    """
    Configure the Alembic migration context for online (connected) use.

    ``render_as_batch=True`` enables SQLite-compatible ALTER TABLE operations
    via a table-copy strategy.  It is a no-op for other databases.

    ``compare_type=True`` enables column type comparison during autogenerate,
    so type changes (e.g. String → Text) are detected and included in diffs.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,       # SQLite ALTER TABLE compatibility
        compare_type=True,          # detect column type changes in autogenerate
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Offline mode: generates SQL script without a live database connection.
# Used by: ``alembic upgrade head --sql``
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL DDL as a script without connecting to the database.
    Useful for reviewing migrations before applying them, or for applying
    migrations through a DBA-controlled process.

    Usage::

        alembic upgrade head --sql > migration.sql
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode: runs migrations against a live database connection.
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (connected to a live database).

    If a pre-existing SQLAlchemy connection is available via
    ``config.attributes["connection"]`` (set by ``core.migrations.runner``),
    it is used directly.  This is the path taken for all programmatic
    invocations, including ``:memory:`` SQLite databases in tests.

    Otherwise, a new engine is created from the URL in ``alembic.ini`` or
    the ``CONFIGFORGE_DB_URL`` environment variable.  This is the path taken
    when running Alembic from the CLI.
    """
    # --- Programmatic mode: caller provides an existing connection ----------
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        _configure_context(connectable)
        return

    # --- CLI mode: create engine from URL -----------------------------------
    url = _get_url()

    # NullPool avoids holding connections between CLI commands.
    cfg_section = config.get_section(config.config_ini_section, {})
    cfg_section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _configure_context(connection)


# ---------------------------------------------------------------------------
# Entry point — Alembic calls this module and inspects context.is_offline_mode()
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
