"""
Unit tests for StorageFactory.

Contracts verified
------------------
1.  ``StorageFactory.create()`` returns the correct provider class.
2.  Provider names are matched case-insensitively.
3.  An unknown provider name raises ``ValueError`` with a helpful message.
4.  All four built-in providers are registered on import.
5.  ``StorageFactory.list_providers()`` returns a sorted list.
6.  ``StorageFactory.register()`` rejects non-StorageProvider subclasses.
7.  ``StorageFactory.register()`` / ``unregister()`` round-trips correctly.
8.  Each scaffold provider implements the interface (no AttributeError).
9.  Scaffold providers' ``health_check()`` returns UNHEALTHY (not raises).
10. Scaffold providers expose correct capability flags.

Run from repository root::

    python3 -m pytest tests/storage/test_factory.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.storage import StorageFactory, DatabaseConfig, AppConfig, HealthStatus
from core.storage.providers.sqlite import SQLiteProvider
from core.storage.providers.postgresql import PostgreSQLProvider
from core.storage.providers.mysql import MySQLProvider
from core.storage.providers.sqlserver import SQLServerProvider


class TestStorageFactoryRegistry(unittest.TestCase):
    """Factory registry: create, list, register, unregister."""

    def test_sqlite_provider_registered(self):
        self.assertIn("sqlite", StorageFactory.list_providers())

    def test_postgresql_provider_registered(self):
        self.assertIn("postgresql", StorageFactory.list_providers())

    def test_postgres_alias_registered(self):
        self.assertIn("postgres", StorageFactory.list_providers())

    def test_mysql_provider_registered(self):
        self.assertIn("mysql", StorageFactory.list_providers())

    def test_sqlserver_provider_registered(self):
        self.assertIn("sqlserver", StorageFactory.list_providers())

    def test_mssql_alias_registered(self):
        self.assertIn("mssql", StorageFactory.list_providers())

    def test_list_providers_is_sorted(self):
        names = StorageFactory.list_providers()
        self.assertEqual(names, sorted(names))

    def test_register_and_unregister(self):
        from core.storage.provider import StorageProvider, HealthCheckResult, HealthStatus, ProviderCapabilities, ProviderMetadata
        from sqlalchemy.orm import sessionmaker

        class _DummyProvider(StorageProvider):
            def __init__(self, config): pass
            def initialize(self): pass
            def shutdown(self): pass
            def get_engine(self): raise RuntimeError("dummy")
            def get_session_factory(self): raise RuntimeError("dummy")
            def health_check(self): return HealthCheckResult(HealthStatus.UNHEALTHY, "dummy")
            def get_metadata(self): return ProviderMetadata("dummy", "0", "none", "none", ProviderCapabilities())
            def get_capabilities(self): return ProviderCapabilities()

        StorageFactory.register("dummy_test_provider", _DummyProvider)
        self.assertIn("dummy_test_provider", StorageFactory.list_providers())

        provider = StorageFactory.create(DatabaseConfig(provider="dummy_test_provider"))
        self.assertIsInstance(provider, _DummyProvider)

        StorageFactory.unregister("dummy_test_provider")
        self.assertNotIn("dummy_test_provider", StorageFactory.list_providers())

    def test_register_rejects_non_provider(self):
        with self.assertRaises(TypeError):
            StorageFactory.register("bad", object)  # type: ignore[arg-type]


class TestStorageFactoryCreate(unittest.TestCase):
    """create() selects the correct provider class."""

    def test_creates_sqlite_provider(self):
        config = DatabaseConfig(provider="sqlite", sqlite_path=":memory:")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, SQLiteProvider)

    def test_creates_postgresql_provider(self):
        config = DatabaseConfig(provider="postgresql")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, PostgreSQLProvider)

    def test_postgres_alias_creates_postgresql_provider(self):
        config = DatabaseConfig(provider="postgres")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, PostgreSQLProvider)

    def test_creates_mysql_provider(self):
        config = DatabaseConfig(provider="mysql")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, MySQLProvider)

    def test_creates_sqlserver_provider(self):
        config = DatabaseConfig(provider="sqlserver")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, SQLServerProvider)

    def test_mssql_alias_creates_sqlserver_provider(self):
        config = DatabaseConfig(provider="mssql")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, SQLServerProvider)

    def test_unknown_provider_raises_value_error(self):
        config = DatabaseConfig(provider="oracle")
        with self.assertRaises(ValueError) as ctx:
            StorageFactory.create(config)
        self.assertIn("oracle", str(ctx.exception))

    def test_case_insensitive_sqlite(self):
        config = DatabaseConfig(provider="SQLite")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, SQLiteProvider)

    def test_case_insensitive_postgresql(self):
        config = DatabaseConfig(provider="PostgreSQL")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, PostgreSQLProvider)

    def test_case_insensitive_mysql(self):
        config = DatabaseConfig(provider="MySQL")
        provider = StorageFactory.create(config)
        self.assertIsInstance(provider, MySQLProvider)


class TestScaffoldProviders(unittest.TestCase):
    """Scaffold providers: interface compliance, metadata, capabilities."""

    def _make_providers(self):
        config = DatabaseConfig()
        return [
            PostgreSQLProvider(config),
            MySQLProvider(config),
            SQLServerProvider(config),
        ]

    def test_scaffold_initialize_raises_not_implemented(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                with self.assertRaises(NotImplementedError):
                    p.initialize()

    def test_scaffold_get_engine_raises_runtime_error(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                with self.assertRaises(RuntimeError):
                    p.get_engine()

    def test_scaffold_get_session_factory_raises_runtime_error(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                with self.assertRaises(RuntimeError):
                    p.get_session_factory()

    def test_scaffold_health_check_returns_unhealthy_no_raise(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                result = p.health_check()
                self.assertEqual(result.status, HealthStatus.UNHEALTHY)
                self.assertFalse(result.is_healthy)

    def test_scaffold_shutdown_is_noop(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                p.shutdown()  # must not raise

    def test_scaffold_get_metadata_does_not_raise(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                meta = p.get_metadata()
                self.assertIsNotNone(meta.name)
                self.assertIsNotNone(meta.driver)

    def test_scaffold_get_capabilities_returns_object(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                caps = p.get_capabilities()
                self.assertIsNotNone(caps)

    def test_postgresql_supports_transactions(self):
        caps = PostgreSQLProvider(DatabaseConfig()).get_capabilities()
        self.assertTrue(caps.transactions)

    def test_postgresql_supports_json_columns(self):
        caps = PostgreSQLProvider(DatabaseConfig()).get_capabilities()
        self.assertTrue(caps.json_columns)

    def test_postgresql_supports_array_columns(self):
        caps = PostgreSQLProvider(DatabaseConfig()).get_capabilities()
        self.assertTrue(caps.array_columns)

    def test_sqlserver_supports_row_level_security(self):
        caps = SQLServerProvider(DatabaseConfig()).get_capabilities()
        self.assertTrue(caps.row_level_security)

    def test_mysql_does_not_support_array_columns(self):
        caps = MySQLProvider(DatabaseConfig()).get_capabilities()
        self.assertFalse(caps.array_columns)

    def test_provider_repr_does_not_raise(self):
        for p in self._make_providers():
            with self.subTest(provider=type(p).__name__):
                self.assertIsInstance(repr(p), str)


if __name__ == "__main__":
    unittest.main()
