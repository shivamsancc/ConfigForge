"""
Startup and shutdown log messages for ConfigFoundry.

These functions are called from the FastAPI lifespan context manager in
``app.py``.  They emit structured, human-readable messages that make it
easy to confirm at a glance what was loaded, which storage backend is
active, and how long startup took.

Example startup output
----------------------
::

    2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] ConfigFoundry v0.5.0 starting up
    2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] API version  : v1  (prefix: /api/v1)
    2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Python       : 3.11.7
    2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Storage      : SQLiteProvider v1.0.0 (dialect: sqlite)
    2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Log file     : logs/configfoundry.log (rotation: daily)
    2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Startup time : 0.142s

Example shutdown output
-----------------------
::

    2024-01-15 18:45:00 INFO     configfoundry.lifecycle            [-] ConfigFoundry shutting down
    2024-01-15 18:45:00 INFO     configfoundry.lifecycle            [-] Closing storage provider: SQLiteProvider
    2024-01-15 18:45:00 INFO     configfoundry.lifecycle            [-] Shutdown complete
"""
from __future__ import annotations

import sys
from typing import Any, Optional

from core.logging.factory import get_logger

_lifecycle_logger = get_logger("configfoundry.lifecycle")


def log_startup_info(
    *,
    app_version: str,
    api_version: str,
    api_prefix: str = "",
    provider_meta: Optional[dict[str, Any]] = None,
    log_config=None,
    startup_duration_s: float = 0.0,
) -> None:
    """
    Emit structured startup information to the lifecycle logger.

    Parameters
    ----------
    app_version:
        Application version string, e.g. ``"0.5.0"``.
    api_version:
        Current API version tag, e.g. ``"v1"``.
    api_prefix:
        Full URL prefix, e.g. ``"/api/v1"``.
    provider_meta:
        Dictionary returned by ``StorageProvider.get_metadata()``.
        Expected keys: ``name``, ``version``, ``dialect`` (all optional).
    log_config:
        ``LoggingConfig`` instance — used to report the log file path and
        rotation mode.  ``None`` means logging defaults were used.
    startup_duration_s:
        Wall-clock seconds elapsed between the start of ``create_app()``
        and the end of the lifespan startup block.
    """
    provider_meta = provider_meta or {}

    _lifecycle_logger.info("ConfigFoundry v%s starting up", app_version)

    _lifecycle_logger.info(
        "API version  : %s  (prefix: %s)",
        api_version,
        api_prefix or f"/api/{api_version}",
    )

    _lifecycle_logger.info(
        "Python       : %s",
        sys.version.split()[0],
    )

    provider_name    = provider_meta.get("name", "unknown")
    provider_version = provider_meta.get("version", "")
    provider_dialect = provider_meta.get("dialect", "")

    version_part  = f" v{provider_version}" if provider_version else ""
    dialect_part  = f" (dialect: {provider_dialect})" if provider_dialect else ""
    _lifecycle_logger.info(
        "Storage      : %s%s%s",
        provider_name,
        version_part,
        dialect_part,
    )

    if log_config is not None:
        if log_config.file:
            _lifecycle_logger.info(
                "Log file     : %s (rotation: %s)",
                log_config.file,
                log_config.rotation,
            )
        else:
            _lifecycle_logger.info("Log file     : none (console only)")

    _lifecycle_logger.info("Startup time : %.3fs", startup_duration_s)


def log_shutdown_info(
    *,
    provider_meta: Optional[dict[str, Any]] = None,
) -> None:
    """
    Emit shutdown information to the lifecycle logger.

    Parameters
    ----------
    provider_meta:
        Dictionary returned by ``StorageProvider.get_metadata()``.
        Expected key: ``name``.
    """
    provider_meta = provider_meta or {}
    provider_name = provider_meta.get("name", "unknown")

    _lifecycle_logger.info("ConfigFoundry shutting down")
    _lifecycle_logger.info("Closing storage provider: %s", provider_name)
    _lifecycle_logger.info("Shutdown complete")
