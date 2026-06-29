"""
FastAPI router for /api/subnets.

Endpoints
---------
GET    /api/subnets                          → {subnets: [...]}
POST   /api/subnets           body: {subnet, _actor}       → {subnet}
DELETE /api/subnets/{id}      query: _actor                → {deleted: id}
POST   /api/subnets/import    body: {subnets, mode, _actor} → {imported, mode}
POST   /api/subnets/validate-import  body: {subnets, mode} → {findings}
"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.get("/subnets")
def list_subnets(c: ServiceContainer = Depends(get_container)):
    return {"subnets": c.subnet_service.list_subnets()}


@router.post("/subnets/validate-import")
def validate_import_subnets(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    rows = body.get("subnets")
    if not isinstance(rows, list):
        return JSONResponse({"error": "'subnets' must be a list"}, status_code=400)
    mode = body.get("mode", "merge")
    result = c.import_service.validate_import_subnets(rows, mode)
    return result


@router.post("/subnets/import")
def import_subnets(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    rows = body.get("subnets")
    if not isinstance(rows, list):
        return JSONResponse({"error": "'subnets' must be a list"}, status_code=400)
    mode = body.get("mode", "merge")
    actor = body.get("_actor")
    result = c.import_service.import_subnets(rows, mode, actor)
    return result


@router.post("/subnets")
def upsert_subnet(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    subnet = body.get("subnet")
    if not isinstance(subnet, dict):
        return JSONResponse({"error": "'subnet' must be an object"}, status_code=400)
    actor = body.get("_actor")
    try:
        saved = c.subnet_service.create_or_update(subnet, actor)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"subnet": saved}


@router.delete("/subnets/{row_id}")
def delete_subnet(row_id: str, request: Request, c: ServiceContainer = Depends(get_container)):
    actor = request.query_params.get("_actor")
    c.subnet_service.delete(row_id, actor)
    return {"deleted": row_id}
