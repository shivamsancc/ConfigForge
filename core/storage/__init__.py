"""
ConfigFoundry Storage Abstraction Layer.

Public surface — import from here, not from sub-modules::

    from core.storage import (
        StorageProvider,
        HealthStatus,
        HealthCheckResult,
        ProviderCapabilities,
        ProviderMetadata,
        DatabaseConfig,
        AppConfig,
        StorageFactory,
    )

Backward-compatibility shim
----------------------------
Legacy code (and some tests) that used the old ``core/storage.py`` module
may still call ``storage.init(db_path)`` and read ``storage._container``.
Those entry points are preserved here so nothing outside this module needs
to change.
"""
from core.storage.provider import (
    StorageProvider,
    HealthStatus,
    HealthCheckResult,
    ProviderCapabilities,
    ProviderMetadata,
)
from core.storage.config import DatabaseConfig, AppConfig
from core.storage.factory import StorageFactory

__all__ = [
    # Provider abstraction
    "StorageProvider",
    "HealthStatus",
    "HealthCheckResult",
    "ProviderCapabilities",
    "ProviderMetadata",
    # Configuration
    "DatabaseConfig",
    "AppConfig",
    # Factory
    "StorageFactory",
    # Backward-compat shim
    "init",
    "_container",
]

# ---------------------------------------------------------------------------
# Backward-compatibility shim
# ---------------------------------------------------------------------------
# The old core/storage.py module exposed init() and _container so that tests
# (and handler code) could share a single ServiceContainer across HTTP and
# direct storage calls without threading it through every call site.
# This package preserves that interface so existing callers need no changes.

_container = None  # type: ignore[assignment]


def init(db_path: str) -> None:
    """
    Initialise the module-level ``ServiceContainer`` from a SQLite path.

    Idempotent — subsequent calls replace the previous container.
    """
    from core.container import ServiceContainer  # local import to avoid circulars

    global _container
    _container = ServiceContainer(db_path=db_path)


# ---------------------------------------------------------------------------
# Convenience wrappers that delegate to the active container's services/repos.
# These mirror the API that existed on the old core/storage.py module so that
# tests and any other code that calls storage.list_devices() etc. keep working.
# ---------------------------------------------------------------------------

def list_devices() -> list:
    if _container is None:
        raise RuntimeError("storage.init() has not been called")
    return _container.device_service.list_devices()


def upsert_device(device: dict) -> dict:
    if _container is None:
        raise RuntimeError("storage.init() has not been called")
    return _container.device_repo.upsert(device)


def list_bandwidth() -> list:
    if _container is None:
        raise RuntimeError("storage.init() has not been called")
    return _container.bandwidth_service.list_bandwidth()


def list_subnets() -> list:
    if _container is None:
        raise RuntimeError("storage.init() has not been called")
    return _container.subnet_service.list_subnets()
