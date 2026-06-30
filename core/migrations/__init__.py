"""
ConfigFoundry migration framework.

Public API::

    from core.migrations.runner import run_migrations

    run_migrations(engine)   # apply pending Alembic migrations
"""
from core.migrations.runner import run_migrations

__all__ = ["run_migrations"]
