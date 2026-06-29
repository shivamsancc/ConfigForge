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

The factory pattern lets ``server.py`` create the production app, while
test fixtures can spin up isolated apps backed by temporary databases.
"""
from __future__ import annotations

import os
import traceback
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.devices import router as devices_router
from api.bandwidth import router as bandwidth_router
from api.subnets import router as subnets_router
from api.tags import router as tags_router
from api.lists import router as lists_router
from api.generate import router as generate_router
from api.audit import router as audit_router
from api.history import router as history_router
from api.meta import router as meta_router
from api.export import router as export_router
from core.container import ServiceContainer
from core.storage.config import AppConfig


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
        title="ConfigFoundry",
        description="Shared SNMP collector config YAML generator",
        version="0.5.0",
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
    # API routers  (all mounted under /api)
    # ------------------------------------------------------------------
    for r in [
        devices_router,
        bandwidth_router,
        subnets_router,
        tags_router,
        lists_router,
        generate_router,
        audit_router,
        history_router,
        meta_router,
        export_router,
    ]:
        app.include_router(r, prefix="/api")

    # ------------------------------------------------------------------
    # Static file serving
    # ------------------------------------------------------------------
    _static = static_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "static"
    )
    if os.path.isdir(_static):
        app.mount("/", StaticFiles(directory=_static, html=True), name="static")

    return app
