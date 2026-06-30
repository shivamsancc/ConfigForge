"""
Tests for the Alembic baseline migration and migration runner.

Contracts verified
------------------
1.  Fresh database — upgrade head creates all 8 expected tables.
2.  Fresh database — alembic_version table is created with correct revision.
3.  Fresh database — downgrade to base removes all application tables.
4.  Fresh database — upgrade is idempotent (running twice is safe).
5.  Legacy database — has app tables but no alembic_version → stamp, no DDL.
6.  Legacy database — after stamping, alembic_version exists at head.
7.  Legacy database — data is preserved after stamping.
8.  Alembic-managed database — upgrade head is a no-op (already at head).
9.  Runner — get_current_revision returns head revision after upgrade.
10. Runner — get_pending_revisions returns empty list after upgrade.
11. Runner — get_pending_revisions returns baseline revision on fresh DB.
12. SQLiteProvider — initialize() produces all expected tables.
13. SQLiteProvider — initialize() seeds fixed Collector Region list.
14. SQLiteProvider — initialize() is idempotent (safe to call twice).

Run from repository root::

    python3 -m pytest tests/migrations/ -v
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from core.migrations.runner import (
    get_current_revision,
    get_pending_revisions,
    run_migrations,
)

# The revision ID defined in alembic/versions/0001_baseline_schema.py
BASELINE_REVISION = "c1f4e7a8b2d0"

# All tables that should exist after a full migration.
EXPECTED_TABLES = {
    "devices",
    "bandwidth_caps",
    "subnets",
    "tag_defs",
    "audit_log",
    "yaml_history",
    "lists",
    "meta",
}


def _make_engine(path: str):
    """Create a SQLAlchemy engine for a SQLite file."""
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )


def _make_memory_engine():
    """Create a SQLAlchemy engine for an in-memory SQLite database."""
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _table_names(engine) -> set:
    return set(inspect(engine).get_table_names())


# ---------------------------------------------------------------------------
# Fresh database tests
# ---------------------------------------------------------------------------

class TestFreshDatabaseUpgrade(unittest.TestCase):
    """run_migrations() on a completely empty database."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "fresh.db")
        self._engine = _make_engine(self._db_path)

    def tearDown(self):
        self._engine.dispose()

    def test_upgrade_creates_all_expected_tables(self):
        run_migrations(self._engine)
        tables = _table_names(self._engine)
        for table in EXPECTED_TABLES:
            self.assertIn(table, tables, f"Table '{table}' missing after upgrade head")

    def test_upgrade_creates_alembic_version_table(self):
        run_migrations(self._engine)
        self.assertIn("alembic_version", _table_names(self._engine))

    def test_current_revision_is_baseline_after_upgrade(self):
        run_migrations(self._engine)
        rev = get_current_revision(self._engine)
        self.assertEqual(rev, BASELINE_REVISION)

    def test_pending_revisions_empty_after_upgrade(self):
        run_migrations(self._engine)
        pending = get_pending_revisions(self._engine)
        self.assertEqual(pending, [], f"Unexpected pending: {pending}")

    def test_upgrade_is_idempotent(self):
        """Calling run_migrations twice does not raise or duplicate tables."""
        run_migrations(self._engine)
        tables_after_first = _table_names(self._engine)
        run_migrations(self._engine)
        tables_after_second = _table_names(self._engine)
        self.assertEqual(tables_after_first, tables_after_second)


# ---------------------------------------------------------------------------
# Downgrade tests
# ---------------------------------------------------------------------------

class TestDowngrade(unittest.TestCase):
    """Verify the downgrade path for the baseline migration."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "downgrade.db")
        self._engine = _make_engine(self._db_path)
        run_migrations(self._engine)

    def tearDown(self):
        self._engine.dispose()

    def _alembic_cfg(self):
        from alembic.config import Config
        from core.migrations.runner import _alembic_ini_path
        cfg = Config(_alembic_ini_path())
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self._db_path}")
        return cfg

    def test_downgrade_base_removes_application_tables(self):
        from alembic import command
        cfg = self._alembic_cfg()
        with self._engine.connect() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "base")

        tables = _table_names(self._engine)
        app_tables = EXPECTED_TABLES & tables
        self.assertEqual(
            app_tables, set(),
            f"Tables still present after downgrade to base: {app_tables}",
        )

    def test_downgrade_and_upgrade_roundtrip(self):
        """Downgrade to base then upgrade head restores the full schema."""
        from alembic import command
        cfg = self._alembic_cfg()
        with self._engine.connect() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "base")

        tables_after_downgrade = _table_names(self._engine)
        self.assertNotIn("devices", tables_after_downgrade)

        run_migrations(self._engine)
        for table in EXPECTED_TABLES:
            self.assertIn(table, _table_names(self._engine))


# ---------------------------------------------------------------------------
# Legacy (pre-Alembic) database tests
# ---------------------------------------------------------------------------

class TestLegacyDatabaseCompatibility(unittest.TestCase):
    """
    Databases created by core/migrations_legacy.py have all application
    tables and a meta.schema_version key, but NO alembic_version table.
    run_migrations() must stamp them at head without touching the data.
    """

    def _build_legacy_db(self, path: str, schema_version: int = 4) -> None:
        """
        Create a database exactly as the old custom migration system would:
        all tables created via raw sqlite3, schema_version stored in meta.
        """
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bandwidth_caps (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subnets (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tag_defs (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY, ts REAL NOT NULL, actor TEXT,
                action TEXT NOT NULL, details TEXT
            );
            CREATE TABLE IF NOT EXISTS yaml_history (
                id TEXT PRIMARY KEY, ts REAL NOT NULL, actor TEXT,
                summary TEXT, files TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lists (
                list_name TEXT PRIMARY KEY, items TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT
            );
        """)
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(schema_version),),
        )
        conn.execute(
            "INSERT INTO devices (id, data, updated_at) VALUES (?, ?, ?)",
            ("dev-001", json.dumps({"id": "dev-001", "name": "router-1"}), 1700000000.0),
        )
        conn.execute(
            "INSERT INTO lists (list_name, items) VALUES ('collectorRegions', ?)",
            (json.dumps(["us-east"]),),
        )
        conn.commit()
        conn.close()

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "legacy.db")
        self._build_legacy_db(self._db_path)
        self._engine = _make_engine(self._db_path)

    def tearDown(self):
        self._engine.dispose()

    def test_legacy_db_has_no_alembic_version_before_migration(self):
        self.assertNotIn("alembic_version", _table_names(self._engine))

    def test_run_migrations_stamps_legacy_db(self):
        run_migrations(self._engine)
        self.assertIn("alembic_version", _table_names(self._engine))

    def test_legacy_db_is_at_head_after_stamp(self):
        run_migrations(self._engine)
        rev = get_current_revision(self._engine)
        self.assertEqual(rev, BASELINE_REVISION)

    def test_legacy_data_preserved_after_stamp(self):
        """No data should be modified by stamping."""
        run_migrations(self._engine)
        with self._engine.connect() as conn:
            row = conn.execute(text("SELECT data FROM devices WHERE id = 'dev-001'")).fetchone()
        self.assertIsNotNone(row)
        device = json.loads(row[0])
        self.assertEqual(device["name"], "router-1")

    def test_legacy_lists_preserved_after_stamp(self):
        run_migrations(self._engine)
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT items FROM lists WHERE list_name = 'collectorRegions'")
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("us-east", json.loads(row[0]))

    def test_legacy_schema_version_preserved(self):
        """meta.schema_version must not be altered by stamping."""
        run_migrations(self._engine)
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM meta WHERE key = 'schema_version'")
            ).fetchone()
        self.assertEqual(row[0], "4")

    def test_legacy_no_additional_tables_created(self):
        """Stamping must not create or drop any application tables."""
        tables_before = _table_names(self._engine)
        run_migrations(self._engine)
        tables_after = _table_names(self._engine)
        # Only alembic_version should be added
        added = tables_after - tables_before
        self.assertEqual(added, {"alembic_version"})
        self.assertEqual(tables_before - tables_after, set())

    def test_run_migrations_on_legacy_db_is_idempotent(self):
        """Calling run_migrations twice on a legacy DB is safe."""
        run_migrations(self._engine)
        rev_first = get_current_revision(self._engine)
        run_migrations(self._engine)
        rev_second = get_current_revision(self._engine)
        self.assertEqual(rev_first, rev_second)


# ---------------------------------------------------------------------------
# Already-managed database tests
# ---------------------------------------------------------------------------

class TestAlembicManagedDatabase(unittest.TestCase):
    """Databases that already have alembic_version (previously upgraded)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "managed.db")
        self._engine = _make_engine(self._db_path)
        run_migrations(self._engine)   # first run upgrades

    def tearDown(self):
        self._engine.dispose()

    def test_second_run_is_noop(self):
        tables_before = _table_names(self._engine)
        run_migrations(self._engine)
        tables_after = _table_names(self._engine)
        self.assertEqual(tables_before, tables_after)

    def test_revision_unchanged_after_second_run(self):
        rev_before = get_current_revision(self._engine)
        run_migrations(self._engine)
        rev_after = get_current_revision(self._engine)
        self.assertEqual(rev_before, rev_after)


# ---------------------------------------------------------------------------
# In-memory database tests (StaticPool)
# ---------------------------------------------------------------------------

class TestInMemoryDatabase(unittest.TestCase):
    """
    :memory: databases require StaticPool so all connections share the same
    underlying DBAPI connection.  The runner must work correctly with them.
    """

    def test_fresh_memory_db_upgrade(self):
        engine = _make_memory_engine()
        try:
            run_migrations(engine)
            for table in EXPECTED_TABLES:
                self.assertIn(table, _table_names(engine))
        finally:
            engine.dispose()

    def test_memory_db_current_revision(self):
        engine = _make_memory_engine()
        try:
            run_migrations(engine)
            self.assertEqual(get_current_revision(engine), BASELINE_REVISION)
        finally:
            engine.dispose()

    def test_multiple_memory_dbs_are_independent(self):
        """Each engine gets its own independent in-memory database."""
        engine_a = _make_memory_engine()
        engine_b = _make_memory_engine()
        try:
            run_migrations(engine_a)
            # Engine B starts fresh — no tables
            self.assertNotIn("devices", _table_names(engine_b))
            run_migrations(engine_b)
            # Now both are migrated
            self.assertIn("devices", _table_names(engine_a))
            self.assertIn("devices", _table_names(engine_b))
        finally:
            engine_a.dispose()
            engine_b.dispose()


# ---------------------------------------------------------------------------
# SQLiteProvider integration tests
# ---------------------------------------------------------------------------

class TestSQLiteProviderIntegration(unittest.TestCase):
    """
    Verify that SQLiteProvider.initialize() produces a fully-migrated
    database with the expected tables and seed data.
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "provider.db")

    def _make_provider(self):
        from core.storage.config import DatabaseConfig
        from core.storage.providers.sqlite import SQLiteProvider
        cfg = DatabaseConfig(provider="sqlite", sqlite_path=self._db_path)
        return SQLiteProvider(cfg)

    def test_initialize_creates_all_tables(self):
        provider = self._make_provider()
        try:
            provider.initialize()
            tables = _table_names(provider.get_engine())
            for table in EXPECTED_TABLES:
                self.assertIn(table, tables)
        finally:
            provider.shutdown()

    def test_initialize_creates_alembic_version_table(self):
        provider = self._make_provider()
        try:
            provider.initialize()
            self.assertIn("alembic_version", _table_names(provider.get_engine()))
        finally:
            provider.shutdown()

    def test_initialize_seeds_collector_regions_list(self):
        provider = self._make_provider()
        try:
            provider.initialize()
            with provider.get_engine().connect() as conn:
                row = conn.execute(
                    text("SELECT items FROM lists WHERE list_name = 'collectorRegions'")
                ).fetchone()
            self.assertIsNotNone(row, "collectorRegions row must be seeded")
        finally:
            provider.shutdown()

    def test_initialize_idempotent(self):
        """Calling initialize() twice must not raise or duplicate data."""
        provider = self._make_provider()
        try:
            provider.initialize()
            tables_first = _table_names(provider.get_engine())

            # Reinitialise — simulates restart
            provider.initialize()
            tables_second = _table_names(provider.get_engine())

            self.assertEqual(tables_first, tables_second)
        finally:
            provider.shutdown()

    def test_initialize_on_legacy_db(self):
        """
        SQLiteProvider.initialize() must handle a legacy (pre-Alembic) database
        by stamping it rather than re-running migrations.
        """
        # First, create a legacy-style database with the old schema
        legacy_conn = sqlite3.connect(self._db_path)
        legacy_conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE devices (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE bandwidth_caps (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE subnets (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE tag_defs (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE audit_log (id TEXT PRIMARY KEY, ts REAL NOT NULL, actor TEXT, action TEXT NOT NULL, details TEXT);
            CREATE TABLE yaml_history (id TEXT PRIMARY KEY, ts REAL NOT NULL, actor TEXT, summary TEXT, files TEXT NOT NULL);
            CREATE TABLE lists (list_name TEXT PRIMARY KEY, items TEXT NOT NULL);
        """)
        legacy_conn.execute(
            "INSERT INTO meta VALUES ('schema_version', '4')"
        )
        legacy_conn.execute(
            "INSERT INTO devices VALUES ('dev-1', ?, 1700000000.0)",
            (json.dumps({"id": "dev-1", "name": "sw-core"}),),
        )
        legacy_conn.commit()
        legacy_conn.close()

        provider = self._make_provider()
        try:
            provider.initialize()

            # Alembic version should now exist
            self.assertIn("alembic_version", _table_names(provider.get_engine()))

            # Existing device must be untouched
            with provider.get_engine().connect() as conn:
                row = conn.execute(
                    text("SELECT data FROM devices WHERE id = 'dev-1'")
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(json.loads(row[0])["name"], "sw-core")
        finally:
            provider.shutdown()


# ---------------------------------------------------------------------------
# runner utility function tests
# ---------------------------------------------------------------------------

class TestRunnerUtilities(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "utils.db")
        self._engine = _make_engine(self._db_path)

    def tearDown(self):
        self._engine.dispose()

    def test_get_current_revision_none_on_fresh_db(self):
        # Fresh DB has no alembic_version table
        rev = get_current_revision(self._engine)
        self.assertIsNone(rev)

    def test_get_pending_revisions_contains_baseline_on_fresh_db(self):
        pending = get_pending_revisions(self._engine)
        self.assertIn(BASELINE_REVISION, pending)

    def test_get_pending_revisions_empty_after_upgrade(self):
        run_migrations(self._engine)
        pending = get_pending_revisions(self._engine)
        self.assertEqual(pending, [])

    def test_get_current_revision_after_upgrade(self):
        run_migrations(self._engine)
        rev = get_current_revision(self._engine)
        self.assertEqual(rev, BASELINE_REVISION)


if __name__ == "__main__":
    unittest.main()
