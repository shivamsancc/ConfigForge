"""
FastAPI router for /api/tags.

Endpoints
---------
GET    /api/tags                             → {tagDefs: [...]}
POST   /api/tags             body: {tagDef, _actor}    → {tagDef}
DELETE /api/tags/{id}        query: _actor, force      → {deleted: id} | 409
GET    /api/tags/{id}/usage  query: value              → {count: N}
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.dependencies import get_container
from core.container import ServiceContainer
from core.services.tag_service import TagInUseError

router = APIRouter()


@router.get("/tags")
def list_tags(c: ServiceContainer = Depends(get_container)):
    return {"tagDefs": c.tag_service.list_tags()}


@router.get("/tags/{tag_id}/usage")
def tag_usage(tag_id: str, request: Request, c: ServiceContainer = Depends(get_container)):
    value: Optional[str] = request.query_params.get("value")
    if value is not None:
        count = c.tag_service.value_usage_count(tag_id, value)
    else:
        count = c.tag_service.usage_count(tag_id)
    return {"count": count}


@router.post("/tags")
def upsert_tag(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    tag_def = body.get("tagDef")
    if not isinstance(tag_def, dict):
        return JSONResponse({"error": "'tagDef' must be an object"}, status_code=400)
    actor = body.get("_actor")
    saved = c.tag_service.create_or_update(tag_def, actor)
    return {"tagDef": saved}


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: str, request: Request, c: ServiceContainer = Depends(get_container)):
    actor = request.query_params.get("_actor")
    force = request.query_params.get("force", "false") == "true"
    try:
        result = c.tag_service.delete(tag_id, actor, force=force)
        return {"deleted": result["deleted"]}
    except TagInUseError as e:
        return JSONResponse({"error": "tag is in use", "dependents": e.dependents}, status_code=409)
