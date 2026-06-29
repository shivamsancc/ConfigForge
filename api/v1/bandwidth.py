"""
API v1 router for /api/v1/bandwidth.

Endpoints
---------
GET    /api/v1/bandwidth
POST   /api/v1/bandwidth/validate-import
POST   /api/v1/bandwidth/import
POST   /api/v1/bandwidth
DELETE /api/v1/bandwidth/{id}
"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.get("/bandwidth")
def list_bandwidth(c: ServiceContainer = Depends(get_container)):
    return {"rows": c.bandwidth_service.list_bandwidth()}


@router.post("/bandwidth/validate-import")
def validate_import_bandwidth(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    rows = body.get("rows")
    if not isinstance(rows, list):
        return JSONResponse({"error": "'rows' must be a list"}, status_code=400)
    mode = body.get("mode", "merge")
    return c.import_service.validate_import_bandwidth(rows, mode)


@router.post("/bandwidth/import")
def import_bandwidth(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    rows = body.get("rows")
    if not isinstance(rows, list):
        return JSONResponse({"error": "'rows' must be a list"}, status_code=400)
    mode = body.get("mode", "merge")
    actor = body.get("_actor")
    return c.import_service.import_bandwidth(rows, mode, actor)


@router.post("/bandwidth")
def upsert_bandwidth(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    row = body.get("row")
    if not isinstance(row, dict):
        return JSONResponse({"error": "'row' must be an object"}, status_code=400)
    actor = body.get("_actor")
    try:
        saved = c.bandwidth_service.create_or_update(row, actor)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"row": saved}


@router.delete("/bandwidth/{row_id}")
def delete_bandwidth(row_id: str, request: Request, c: ServiceContainer = Depends(get_container)):
    actor = request.query_params.get("_actor")
    c.bandwidth_service.delete(row_id, actor)
    return {"deleted": row_id}
