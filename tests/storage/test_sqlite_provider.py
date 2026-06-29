"""
Unit tests for SQLiteProvider.

Contracts verified
------------------
1.  initialize() creates a working SQLAlchemy engine.
2.  get_engine() raises RuntimeError before initialize().
3.  get_session_factory() raises RuntimeError before initialize().
4.  health_check() before initialize() returns UNHEALTHY.
5.  health_check() after initialize() returns HEALTHY with non-negative latency_ms.
6.  get_metadata() returns name="sqlite", driver="sqlite3", dialect="sqlite".
7.  get_capabilities() matches SQLite feature set.
8.  shutdown() disposes the engine (subsequent get_engine raises RuntimeError).
9.  In-memory SQLite (:memory:) works end-to-end.
10. Multiple initialize() calls are idempotent (no crash).
11. provider.name property matches get_metadata().name.

Run from repository root::

    python3 -m pytest tests/storage/test_sqlite_provider.py -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.storage.config import DatabaseConfig, AppConfig
from core.storage.providers.sqlite import SQLiteProvider
from core.storage.provider import HealthStatus


class TestSQLiteProviderBeforeInit(unittest.TestCase):
    """Behaviour before initialize() is called."""

    def setUp(self):
        self.config = DatabaseConfig(provider="sqlite", sqlite_path=":memory:")
        self.provider = SQLiteProvider(self.config)

    def test_get_engine_before_init_raises(self):
        with self.assertRaises(RuntimeError):
            self.provider.get_engine()

    def test_get_session_factory_before_init_raises(self):
        with self.assertRaises(RuntimeError):
            self.provider.get_session_factory()

    def test_health_check_before_init_returns_unhealthy(self):
        result = self.provider.health_check()
        self.assertEqual(result.status, HealthStatus.UNHEALTHY)
        self.assertFalse(result.is_healthy)

    def test_health_check_before_init_does_not_raise(self):
        # Must return a result, not raise
        result = self.provider.health_check()
        self.assertIsNotNone(result)

    def test_get_metadata_before_init_does_not_raise(self):
        meta = self.provider.get_metadata()
        self.assertIsNotNone(meta)

    def test_get_capabilities_before_init_does_not_raise(self):
        caps = self.provider.get_capabilities()
        self.assertIsNotNone(caps)

    def test_shutdown_before_init_does_not_raise(self):
        self.provider.shutdown()  # noop — must not crash


class TestSQLiteProviderInMemory(unittest.TestCase):
    """In-memory SQLite: initialize() → full lifecycle tests."""

    def setUp(self):
        self.config = DatabaseConfig(provider="sqlite", sqlite_path=":memory:")
        self.provider = SQLiteProvider(self.config)
        self.provider.initialize()

    def tearDown(self):
        try:
            self.provider.shutdown()
        except Exception:
            pass

    # ------------------------------------------------------------------ engine

    def test_get_engine_after_init_returns_engine(self):
        from sqlalchemy import Engine
        engine = self.provider.get_engine()
        self.assertIsInstance(engine, Engine)

    def test_engine_is_connectable(self):
        from sqlalchemy import text
        engine = self.provider.get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).fetchone()
        self.assertIsNotNone(result)

    # --------------------------------------------------------- session factory

    def test_get_session_factory_returns_callable(self):
        factory = self.provider.get_session_factory()
        self.assertIsNotNone(factory)
        self.assertTrue(callable(factory))

    def test_session_factory_produces_usable_session(self):
        from sqlalchemy import text
        factory = self.provider.get_session_factory()
        session = factory()
        try:
            result = session.execute(text("SELECT 1")).fetchone()
            self.assertIsNotNone(result)
        finally:
            session.close()

    # ---------------------------------------------------------- health check

    def test_health_check_returns_healthy(self):
        result = self.provider.health_check()
        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertTrue(result.is_healthy)

    def test_health_check_has_latency_ms(self):
        result = self.provider.health_check()
        self.assertIsNotNone(result.latency_ms)
        self.assertGreaterEqual(result.latency_ms, 0)

    def test_health_check_has_message(self):
        result = self.provider.health_check()
        self.assertIsInstance(result.message, str)
        self.assertTrue(len(result.message) > 0)

    # ------------------------------------------------------------ metadata

    def test_metadata_name_is_sqlite(self):
        meta = self.provider.get_metadata()
        self.assertEqual(meta.name, "sqlite")

    def test_metadata_driver_is_sqlite3(self):
        meta = self.provider.get_metadata()
        self.assertEqual(meta.driver, "sqlite3")

    def test_metadata_dialect_is_sqlite(self):
        meta = self.provider.get_metadata()
        self.assertEqual(meta.dialect, "sqlite")

    def test_metadata_version_is_non_empty_string(self):
        meta = self.provider.get_metadata()
        self.assertIsInstance(meta.version, str)
        self.assertTrue(len(meta.version) > 0)

    def test_provider_name_property_matches_metadata_name(self):
        self.assertEqual(self.provider.name, "sqlite")

    # --------------------------------------------------------- capabilities

    def test_capabilities_transactions_true(self):
        self.assertTrue(self.provider.get_capabilities().transactions)

    def test_capabilities_migrations_true(self):
        self.assertTrue(self.provider.get_capabilities().migrations)

    def test_capabilities_full_text_search_true(self):
        self.assertTrue(self.provider.get_capabilities().full_text_search)

    def test_capabilities_json_columns_true(self):
        self.assertTrue(self.provider.get_capabilities().json_columns)

    def test_capabilities_array_columns_false(self):
        self.assertFalse(self.provider.get_capabilities().array_columns)

    def test_capabilities_schemas_false(self):
        self.assertFalse(self.provider.get_capabilities().schemas)

    def test_capabilities_read_replicas_false(self):
        self.assertFalse(self.provider.get_capabilities().read_replicas)

    def test_capabilities_row_level_security_false(self):
        self.assertFalse(self.provider.get_capabilities().row_level_security)

    # ------------------------------------------------------------ shutdown

    def test_shutdown_disposes_engine(self):
        self.provider.shutdown()
        with self.assertRaises(RuntimeError):
            self.provider.get_engine()

    def test_shutdown_makes_health_check_unhealthy(self):
        self.provider.shutdown()
        result = self.provider.health_check()
        self.assertEqual(result.status, HealthStatus.UNHEALTHY)

    def test_double_shutdown_does_not_raise(self):
        self.provider.shutdown()
        self.provider.shutdown()  # idempotent

    # -------------------------------------------------- idempotent init

    def test_double_initialize_does_not_raise(self):
        # calling initialize() twice should not crash
        self.provider.initialize()

    def test_engine_works_after_double_initialize(self):
        from sqlalchemy import text
        self.provider.initialize()
        engine = self.provider.get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).fetchone()
        self.assertIsNotNone(result)


class TestSQLiteProviderFileDB(unittest.TestCase):
    """File-backed SQLite: migrations run correctly on a real file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self.config = DatabaseConfig(provider="sqlite", sqlite_path=self._db_path)
        self.provider = SQLiteProvider(self.config)
        self.provider.initialize()

    def tearDown(self):
        try:
            self.provider.shutdown()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_db_file_created(self):
        self.assertTrue(os.path.exists(self._db_path))

    def test_engine_is_connectable(self):
        from sqlalchemy import text
        with self.provider.get_engine().connect() as conn:
            result = conn.execute(text("SELECT 1")).fetchone()
        self.assertIsNotNone(result)

    def test_health_check_returns_healthy(self):
        result = self.provider.health_check()
        self.assertEqual(result.status, HealthStatus.HEALTHY)

    def test_devices_table_exists(self):
        """Migrations must create the devices table."""
        from sqlalchemy import text
        with self.provider.get_engine().connect() as conn:
            # sqlite_master lists all tables
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='devices'")
            ).fetchone()
        self.assertIsNotNone(row, "devices table not created by migrations")

    def test_lists_table_seeded_with_fixed_lists(self):
        """FIXED_LISTS must be seeded on first run."""
        from sqlalchemy import text
        with self.provider.get_engine().connect() as conn:
            rows = conn.execute(text("SELECT list_name FROM lists")).fetchall()
        names = [r[0] for r in rows]
        self.assertTrue(len(names) > 0, "No lists seeded in lists table")

    def test_factory_creates_working_file_provider(self):
        """StorageFactory end-to-end: create SQLite provider from config, open file DB."""
        from core.storage.factory import StorageFactory
        from sqlalchemy import text

        config = DatabaseConfig(provider="sqlite", sqlite_path=self._db_path)
        provider = StorageFactory.create(config)
        # Already initialized in setUp — create a second provider for the same file
        p2 = StorageFactory.create(config)
        p2.initialize()
        try:
            with p2.get_engine().connect() as conn:
                result = conn.execute(text("SELECT 1")).fetchone()
            self.assertIsNotNone(result)
        finally:
            p2.shutdown()


class TestSQLiteProviderViaAppConfig(unittest.TestCase):
    """AppConfig.for_sqlite() → StorageFactory → SQLiteProvider roundtrip."""

    def test_appconfig_for_sqlite_creates_working_provider(self):
        from core.storage.factory import StorageFactory
        from sqlalchemy import text

        config = AppConfig.for_sqlite(":memory:")
        provider = StorageFactory.create(config.database)
        provider.initialize()
        try:
            with provider.get_engine().connect() as conn:
                result = conn.execute(text("SELECT 1")).fetchone()
            self.assertIsNotNone(result)
        finally:
            provider.shutdown()

    def test_service_container_with_provider_arg(self):
        """ServiceContainer(provider=...) skips factory and initialize()."""
        from core.container import ServiceContainer

        config = DatabaseConfig(provider="sqlite", sqlite_path=":memory:")
        provider = SQLiteProvider(config)
        provider.initialize()
        try:
            container = ServiceContainer(provider=provider)
            # Verify repos are wired
            self.assertIsNotNone(container.device_repo)
            self.assertIsNotNone(container.device_service)
        finally:
            provider.shutdown()


if __name__ == "__main__":
    unittest.main()
