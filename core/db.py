"""
SQLAlchemy 2.x database initialisation for ConfigForge.

``init_db(db_path)`` is the single entry-point.  It:
  1. Runs pending schema migrations via the existing ``core.migrations``
     module (which still uses the raw sqlite3 API — we extract a raw
     connection from the SQLAlchemy engine for this step only).
  2. Ensures the fixed Collector-Region list row exists.
  3. Sets WAL journal mode for better concurrent read performance.
  4. Returns a configured ``Engine`` that the rest of the application uses.

Usage::

    from core.db import init_db
    engine = init_db("/path/to/configforge.db")
"""
import json
import sqlite3

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session

from core import migrations
from core.repositories.sqlite.list import FIXED_LISTS  # canonical constant


def init_db(db_path: str) -> Engine:
    """Open (or create) the SQLite database, run migrations, return engine."""

    # ------------------------------------------------------------------
    # Step 1: Run migrations using a raw sqlite3 connection.
    # migrations.py was written against the sqlite3 API; re-using it here
    # is simpler than rewriting every migration with SQLAlchemy Core.
    # ------------------------------------------------------------------
    raw_conn = sqlite3.connect(db_path)
    raw_conn.row_factory = sqlite3.Row
    try:
        migrations.run_pending_migrations(raw_conn)
        # Ensure the Collector Region list row exists.
        for name in FIXED_LISTS:
            raw_conn.execute(
                "INSERT OR IGNORE INTO lists (list_name, items) VALUES (?, ?)",
                (name, json.dumps([])),
            )
        raw_conn.commit()
    finally:
        raw_conn.close()

    # ------------------------------------------------------------------
    # Step 2: Create the SQLAlchemy engine.
    # ``check_same_thread=False`` is required for SQLite when the same
    # engine is shared across multiple threads (e.g. uvicorn workers).
    # ------------------------------------------------------------------
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    # Enable WAL journal mode on every new connection.
    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    return engine
