# API Versioning Guide

ConfigFoundry v0.5 introduces URL-based API versioning. All REST endpoints are served under `/api/v1/`. Future versions (`/api/v2/`, `/api/v3/`) can be added alongside v1 without removing or changing any existing routes.

---

## Design decisions

**URL versioning, not header versioning.** The version appears in the path (`/api/v1/devices`) rather than a header (`Accept: application/vnd.api+json;version=1`). This makes versions:
- Bookmarkable and curl-able without extra flags
- Visible in server logs without header inspection
- Trivially testable with `status_code == 200` checks

**Router-per-version, not branch-per-version.** Each version is a self-contained Python package (`api/v1/`, `api/v2/`). Shared infrastructure (`api/dependencies.py`, `core/services/`, `core/repositories/`) is version-agnostic. A v2 router can re-use any v1 module it doesn't need to change.

**Single FastAPI app.** All versions are included in one FastAPI application and appear together in the OpenAPI spec at `/docs`. This avoids running multiple processes and keeps the container wiring simple. If true isolation is needed (separate auth middleware, separate rate limits), the sub-application pattern described at the end of this document is an alternative.

---

## Current layout

```
api/
  dependencies.py          # get_container() — shared across all versions
  v1/
    __init__.py
    router.py              # APIRouter(prefix="/v1"), includes 10 sub-routers
    devices.py
    bandwidth.py
    subnets.py
    tags.py
    lists.py
    generate.py
    audit.py
    history.py
    meta.py
    export.py
```

`app.py` mounts the v1 router:

```python
from api.v1.router import router as v1_router
app.include_router(v1_router, prefix="/api")
# Result: /api/v1/devices, /api/v1/bandwidth, …
```

---

## Adding v2 — step by step

### 1. Create the v2 package

```
api/v2/__init__.py
api/v2/router.py
api/v2/devices.py       # only if devices endpoint changes in v2
```

### 2. Write the v2 router

```python
# api/v2/router.py
from fastapi import APIRouter

# Import only what changes in v2
from api.v2 import devices as devices_v2

# Re-export unchanged v1 modules directly
from api.v1 import bandwidth, subnets, tags, lists, generate, audit, history, meta, export

router = APIRouter(prefix="/v2")

router.include_router(devices_v2.router, tags=["v2-devices"])
router.include_router(bandwidth.router,  tags=["bandwidth"])
router.include_router(subnets.router,    tags=["subnets"])
router.include_router(tags.router,       tags=["tags"])
router.include_router(lists.router,      tags=["lists"])
router.include_router(generate.router,   tags=["generate"])
router.include_router(audit.router,      tags=["audit"])
router.include_router(history.router,    tags=["history"])
router.include_router(meta.router,       tags=["meta"])
router.include_router(export.router,     tags=["export"])

VERSION = "v2"
PREFIX = f"/api/{VERSION}"
```

### 3. Register in app.py

```python
from api.v1.router import router as v1_router
from api.v2.router import router as v2_router   # new

app.include_router(v1_router, prefix="/api")
app.include_router(v2_router, prefix="/api")    # new
# StaticFiles mount MUST come after all include_router calls
```

Both versions are now live:
- `GET /api/v1/devices` — v1 behaviour
- `GET /api/v2/devices` — v2 behaviour

### 4. Update openapi_tags in app.py

Add tag entries for the new v2 endpoints to the `openapi_tags` list so Swagger UI groups them properly.

### 5. Write tests

Add `tests/api/test_v2.py` following the same structure as `tests/api/test_versioning.py`. Key contracts to verify:
- All v2 paths respond under `/api/v2/`
- All v1 paths still respond unchanged under `/api/v1/`
- OpenAPI spec contains both `/api/v1/` and `/api/v2/` paths

---

## StaticFiles ordering rule

`StaticFiles` is mounted at `/` in `create_app()` and acts as a catch-all. **All `include_router()` calls must happen before `app.mount()`.** Routers registered after the static mount are shadowed by it.

```python
# Correct order in app.py:
app.include_router(v1_router, prefix="/api")
app.include_router(v2_router, prefix="/api")   # add new versions HERE
# StaticFiles LAST:
app.mount("/", StaticFiles(directory=_static, html=True), name="static")
```

---

## Versioning rules

| Rule | Rationale |
|------|-----------|
| Never modify a shipped version's router | Clients depend on stable paths |
| Business logic lives in `core/services/`, not routers | Routers only translate HTTP ↔ service calls; services are version-agnostic |
| Schemas live in `schemas/` | A v2 router can use new Pydantic models without touching v1 schemas |
| Keep the old version alive for ≥ one release cycle | Give clients time to migrate |
| Mark deprecated versions with a `Deprecated` response header | FastAPI lets you add custom middleware for this |

---

## Alternative: sub-application isolation

For strict version isolation (separate middleware stacks, separate auth, separate rate limits), each version can be a full `FastAPI` sub-application mounted with `app.mount()`:

```python
# app.py
from fastapi import FastAPI
from api.v1.router import router as v1_router

def create_v1_sub_app(container) -> FastAPI:
    v1 = FastAPI(title="ConfigFoundry API v1", version="1.0.0")
    v1.state.container = container
    v1.include_router(v1_router)
    return v1

def create_app(...) -> FastAPI:
    root = FastAPI()
    container = ServiceContainer(...)
    root.mount("/api/v1", create_v1_sub_app(container))
    # Docs at: /api/v1/docs
    return root
```

Trade-offs vs. the single-app approach:
- ✅ Each version has its own `/docs`, `/redoc`, `/openapi.json`
- ✅ Middleware (auth, rate limit) can differ per version
- ✅ Can run different versions in different workers
- ❌ `app.state` is not shared — must pass `container` explicitly to each sub-app
- ❌ More boilerplate; `Depends(get_container)` must reference the sub-app's state

The single-app approach (used by ConfigFoundry) is the right default. Switch to sub-apps when different versions genuinely need different middleware or deployment topology.

---

## Quick reference

| What | Where |
|------|-------|
| v1 router | `api/v1/router.py` |
| v1 endpoint modules | `api/v1/*.py` |
| Shared DI dependency | `api/dependencies.py` |
| App factory (mounts routers) | `app.py` |
| Versioning tests | `tests/api/test_versioning.py` |
| This document | `docs/api-versioning.md` |
