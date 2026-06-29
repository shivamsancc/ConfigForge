"""
Central router for API v1.

Every endpoint in v1 is registered here under the ``/v1`` prefix.
``app.py`` mounts this router under ``/api``, giving the final paths:

    /api/v1/devices
    /api/v1/bandwidth
    /api/v1/subnets
    /api/v1/tags
    /api/v1/lists
    /api/v1/generate
    /api/v1/audit
    /api/v1/history
    /api/v1/meta
    /api/v1/export/...

Adding a future version
-----------------------
1. Create ``api/v2/`` with the same layout (router.py + endpoint modules).
2. Import and include ``v2_router`` in ``app.py`` alongside ``v1_router``.
3. The two versions coexist under the same FastAPI app; the OpenAPI spec will
   show both sets of paths grouped by their ``/v1`` / ``/v2`` prefixes.

Refer to ``docs/api-versioning.md`` for the full guide.
"""
from fastapi import APIRouter

from api.v1 import (
    audit,
    bandwidth,
    devices,
    export,
    generate,
    history,
    lists,
    meta,
    subnets,
    tags,
)

# All v1 routes share the /v1 prefix.  Individual sub-routers define paths
# relative to this prefix (e.g. "/devices"), so the final path becomes
# /api/v1/devices once app.py adds the /api prefix.
router = APIRouter(prefix="/v1")

router.include_router(devices.router,   tags=["devices"])
router.include_router(bandwidth.router, tags=["bandwidth"])
router.include_router(subnets.router,   tags=["subnets"])
router.include_router(tags.router,      tags=["tags"])
router.include_router(lists.router,     tags=["lists"])
router.include_router(generate.router,  tags=["generate"])
router.include_router(audit.router,     tags=["audit"])
router.include_router(history.router,   tags=["history"])
router.include_router(meta.router,      tags=["meta"])
router.include_router(export.router,    tags=["export"])

# Canonical version string exposed to the app layer.
VERSION = "v1"
PREFIX = f"/api/{VERSION}"
