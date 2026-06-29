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
"""
from __future__ import annotations

import os
import traceback
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.v1.router import router as v1_router
from core.container import ServiceContainer
from core.storage.config import AppConfig

# ---------------------------------------------------------------------------
# Application version — bump this on every release.
# ---------------------------------------------------------------------------
APP_VERSION = "0.5.0"


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
    _given = sum(x is not None for x in (db_path, container, config))
    if _given == 0:
        raise ValueError("create_app() requires one of: db_path, container, or config")
    if _given > 1:
        raise ValueError("create_app() accepts only one of: db_path, container, or config")

    app = FastAPI(
        title="ConfigFoundry — API v1",
        description=(
            "Shared SNMP/ICMP collector config YAML generator.\n\n"
            "All endpoints are versioned under `/api/v1/`. "
            "Interactive docs: [Swagger UI](/docs) · [ReDoc](/redoc)"
        ),
        version=APP_VERSION,
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

    # ------------------------------------------------------------------
    # Resolve / build the service container
    # ------------------------------------------------------------------
    if container is not None:
        app.state.container = container
    elif config is not None:
        app.state.container = ServiceContainer(config=config)
    else:
        app.state.container = ServiceContainer(db_path=db_path)

    # ------------------------------------------------------------------
    # Global exception handler — always return JSON on unhandled errors
    # ------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def _generic_error(request: Request, exc: Exception):
        traceback.print_exc()
        return JSONResponse(
            {"error": str(exc), "type": type(exc).__name__},
            status_code=500,
        )

    # ------------------------------------------------------------------
    # API v1 router  (all endpoints under /api/v1/)
    # ------------------------------------------------------------------
    app.include_router(v1_router, prefix="/api")

    # ------------------------------------------------------------------
    # Static file serving
    # ------------------------------------------------------------------
    _static = static_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "static"
    )
    if os.path.isdir(_static):
        app.mount("/", StaticFiles(directory=_static, html=True), name="static")

    return app
