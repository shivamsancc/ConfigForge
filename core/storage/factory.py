"""
Storage Factory — selects and instantiates the correct ``StorageProvider``.

The factory uses a class-level registry so providers can be added without
modifying this file.  All four built-in providers (SQLite, PostgreSQL,
MySQL, SQL Server) are auto-registered at import time.

Usage
-----
::

    from core.storage import StorageFactory, AppConfig

    config = AppConfig.from_yaml("config.yaml")           # provider: postgresql
    provider = StorageFactory.create(config.database)     # → PostgreSQLProvider
    provider.initialize()

Adding a new provider
---------------------
::

    from core.storage.factory import StorageFactory
    from myproject.storage import RedisProvider

    StorageFactory.register("redis", RedisProvider)

    # Now usable via config:
    #   database:
    #     provider: redis
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from core.storage.config import DatabaseConfig
from core.storage.provider import StorageProvider

if TYPE_CHECKING:
    pass


class StorageFactory:
    """
    Registry-based factory for ``StorageProvider`` implementations.

    Class-level ``_registry`` maps lowercase provider names to concrete
    ``StorageProvider`` subclasses.  The factory is intentionally stateless —
    it never holds references to created providers.
    """

    _registry: dict[str, type[StorageProvider]] = {}

    # ------------------------------------------------------------------
    # Registry management
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, name: str, provider_class: type[StorageProvider]) -> None:
        """
        Register a ``StorageProvider`` implementation under *name*.

        *name* is stored and matched case-insensitively.

        Parameters
        ----------
        name:
            The string used in ``DatabaseConfig.provider``.
        provider_class:
            A concrete subclass of ``StorageProvider``.

        Raises
        ------
        TypeError
            If *provider_class* is not a subclass of ``StorageProvider``.
        """
        if not (isinstance(provider_class, type) and issubclass(provider_class, StorageProvider)):
            raise TypeError(
                f"{provider_class!r} is not a subclass of StorageProvider"
            )
        cls._registry[name.lower()] = provider_class

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a provider from the registry (useful in tests)."""
        cls._registry.pop(name.lower(), None)

    @classmethod
    def list_providers(cls) -> list[str]:
        """Return the names of all registered providers, sorted."""
        return sorted(cls._registry.keys())

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, config: DatabaseConfig) -> StorageProvider:
        """
        Instantiate and return the provider specified by *config.provider*.

        Does NOT call ``initialize()`` — the caller is responsible for that.

        Parameters
        ----------
        config:
            A ``DatabaseConfig`` instance.  ``config.provider`` selects
            the provider; the rest of the config is passed through.

        Returns
        -------
        StorageProvider
            A new, uninitialised provider instance.

        Raises
        ------
        ValueError
            If ``config.provider`` is not in the registry.
        """
        key = config.provider.lower()
        provider_class = cls._registry.get(key)
        if provider_class is None:
            available = ", ".join(cls.list_providers()) or "(none registered)"
            raise ValueError(
                f"Unknown storage provider {config.provider!r}.  "
                f"Available: {available}"
            )
        return provider_class(config)


# ---------------------------------------------------------------------------
# Auto-register built-in providers
# ---------------------------------------------------------------------------
# Imports are deferred to this point to avoid circular imports at package
# load time.  All four providers register themselves here.

def _register_builtins() -> None:
    from core.storage.providers.sqlite import SQLiteProvider
    from core.storage.providers.postgresql import PostgreSQLProvider
    from core.storage.providers.mysql import MySQLProvider
    from core.storage.providers.sqlserver import SQLServerProvider

    StorageFactory.register("sqlite", SQLiteProvider)
    StorageFactory.register("postgresql", PostgreSQLProvider)
    StorageFactory.register("postgres", PostgreSQLProvider)   # alias
    StorageFactory.register("mysql", MySQLProvider)
    StorageFactory.register("sqlserver", SQLServerProvider)
    StorageFactory.register("mssql", SQLServerProvider)       # alias


_register_builtins()
