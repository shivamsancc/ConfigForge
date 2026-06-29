"""
API v1 router for /api/v1/lists.

Endpoints
---------
GET  /api/v1/lists
GET  /api/v1/lists/{name}/usage
POST /api/v1/lists/{name}
"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.get("/lists")
def get_lists(c: ServiceContainer = Depends(get_container)):
    return {"lists": c.list_service.get_lists()}


@router.get("/lists/{list_name}/usage")
def list_usage(list_name: str, request: Request, c: ServiceContainer = Depends(get_container)):
    value = request.query_params.get("value", "")
    count = c.list_service.usage_count(list_name, value)
    return {"count": count}


@router.post("/lists/{list_name}")
def set_list(list_name: str, body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    items = body.get("items")
    if not isinstance(items, list):
        return JSONResponse({"error": "'items' must be a list"}, status_code=400)
    actor = body.get("_actor")
    try:
        saved = c.list_service.set_list(list_name, items, actor)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return {"items": saved}
