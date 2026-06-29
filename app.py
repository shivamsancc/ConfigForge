"""
FastAPI application factory for ConfigFoundry.

Usage
-----
Create from a database path (backward-compatible, SQLite)::

    from app import create_app
    app = create_app(db_path="/path/to/configforge.db")

Create from full application config::

    from app import create_app
    from core.storage import AppConfig, DatabaseConfig

    config = AppConfig(database=DatabaseConfig(provider="sqlite", sqlite_path="db/cf.db"))
    app = create_app(config=config)

Reuse an existing ``ServiceContainer`` (e.g. in tests that also call
``storage.init()`` directly so HTTP and storage calls share one DB)::

    from app import create_app
    app = create_app(container=existing_container)

API versioning
--------------
All REST endpoints live under ``/api/v1/``.  The v1 router is assembled in
``api/v1/router.py`` and included here under the ``/api`` prefix.

To add a future version alongside v1::

    from api.v2.router import router as v2_router
    app.include_router(v2_router, prefix="/api")

Both versions then coexist; callers choose by URL prefix.
See ``docs/api-versioning.md`` for the full guide.

Middleware order
----------------
Starlette prepends middleware: the last ``add_middleware()`` call runs FIRST.
We must register them in this order::

    app.add_middleware(RequestLoggingMiddleware)   # added first → runs second
    app.add_middleware(CorrelationIDMiddleware)    # added last  → runs first

This ensures every log line emitted by RequestLoggingMiddleware (and all
code below it) already carries the correlation ID.
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.v1.router import PREFIX as V1_PREFIX, VERSION as V1_VERSION, router as v1_router
from core.container import ServiceContainer
from core.logging import get_logger
from core.logging.middleware import CorrelationIDMiddleware, RequestLoggingMiddleware
from core.logging.startup import log_shutdown_info, log_startup_info
from core.storage.config import AppConfig

# ---------------------------------------------------------------------------
# Application version — bump this on every release.
# ---------------------------------------------------------------------------
APP_VERSION = "0.5.0"

# Module-level logger (obtained after configure_logging() is called in
# server.py — safe because loggers are created lazily).
_logger = get_logger(__name__)


def create_app(
    db_path: Optional[str] = None,
    container: Optional[ServiceContainer] = None,
    config: Optional[AppConfig] = None,
    static_dir: Optional[str] = None,
) -> FastAPI:
    """
    Build and return the FastAPI application.

    Exactly one of *db_path*, *container*, or *config* must be provided.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Backward-compatible shortcut —
        equivalent to passing ``AppConfig.for_sqlite(db_path)``.
    container:
        An already-constructed ``ServiceContainer``.  Used when tests need
        the HTTP layer to share the same repos/services as direct storage
        calls made via ``storage.init()``.
    config:
        Full ``AppConfig`` — enables non-SQLite backends and future config
        sections (logging, auth, feature flags).
    static_dir:
        Directory to serve static files from.  Defaults to the ``static/``
        folder next to this file.
    """
    _t_start = time.perf_counter()

    _given = sum(x is not None for x in (db_path, container, config))
    if _given == 0:
        raise ValueError("create_app() requires one of: db_path, container, or config")
    if _given > 1:
        raise ValueError("create_app() accepts only one of: db_path, container, or config")

    # ------------------------------------------------------------------
    # Build the service container BEFORE FastAPI so we can read provider
    # metadata in the lifespan handler.
    # ------------------------------------------------------------------
    if container is not None:
        _container = container
        _log_config = None
    elif config is not None:
        _container = ServiceContainer(config=config)
        _log_config = config.logging
    else:
        _container = ServiceContainer(db_path=db_path)
        _log_config = None

    # ------------------------------------------------------------------
    # Lifespan — startup and shutdown logging
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        # ---- startup ----
        try:
            provider_meta = _container._provider.get_metadata()
        except Exception:
            provider_meta = {}

        log_startup_info(
            app_version=APP_VERSION,
            api_version=V1_VERSION,
            api_prefix=V1_PREFIX,
            provider_meta=provider_meta,
            log_config=_log_config,
            startup_duration_s=time.perf_counter() - _t_start,
        )

        yield

        # ---- shutdown ----
        try:
            provider_meta = _container._provider.get_metadata()
        except Exception:
            provider_meta = {}

        log_shutdown_info(provider_meta=provider_meta)

    # ------------------------------------------------------------------
    # FastAPI application
    # ------------------------------------------------------------------
    app = FastAPI(
        title="ConfigFoundry — API v1",
        description=(
            "Shared SNMP/ICMP collector config YAML generator.\n\n"
            "All endpoints are versioned under `/api/v1/`. "
            "Interactive docs: [Swagger UI](/docs) · [ReDoc](/redoc)"
        ),
        version=APP_VERSION,
        lifespan=_lifespan,
        openapi_tags=[
            {"name": "devices",   "description": "Network device inventory"},
            {"name": "bandwidth", "description": "Interface bandwidth caps"},
            {"name": "subnets",   "description": "Subnet definitions and CIDR blocks"},
            {"name": "tags",      "description": "Dynamic tag definitions"},
            {"name": "lists",     "description": "Managed value lists (Collector Region, etc.)"},
            {"name": "generate",  "description": "YAML config generation"},
            {"name": "audit",     "description": "Audit log"},
            {"name": "history",   "description": "YAML generation history"},
            {"name": "meta",      "description": "Inventory metadata and statistics"},
            {"name": "export",    "description": "Excel export"},
        ],
    )

    # Store container on app.state for DI (api/dependencies.py reads this).
    app.state.container = _container

    # ------------------------------------------------------------------
    # Global exception handler — always return JSON on unhandled errors
    # ------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def _generic_error(request: Request, exc: Exception):
        _logger.error(
            "Unhandled %s on %s %s",
            type(exc).__name__,
            request.method,
            request.url.path,
            exc_info=True,
        )
        return JSONResponse(
            {"error": str(exc), "type": type(exc).__name__},
            status_code=500,
        )

    # ------------------------------------------------------------------
    # Middleware  (LAST added = FIRST to run)
    # ------------------------------------------------------------------
    app.add_middleware(RequestLoggingMiddleware)   # added first → runs second
    app.add_middleware(CorrelationIDMiddleware)    # added last  → runs first

    # ------------------------------------------------------------------
    # API v1 router  (all endpoints under /api/v1/)
    # ------------------------------------------------------------------
    app.include_router(v1_router, prefix="/api")

    # ------------------------------------------------------------------
    # Static file serving  (MUST come after all include_router calls)
    # ------------------------------------------------------------------
    _static = static_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "static"
    )
    if os.path.isdir(_static):
        app.mount("/", StaticFiles(directory=_static, html=True), name="static")

    return app
