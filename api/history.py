"""
FastAPI router for /api/history.

Endpoints
---------
GET /api/history            query: limit  → {entries: [...]}
GET /api/history/{id}                     → {id, ts, actor, summary, files}
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.get("/history")
def list_history(request: Request, c: ServiceContainer = Depends(get_container)):
    limit = int(request.query_params.get("limit", "50"))
    return {"entries": c.history_service.list_recent(limit)}


@router.get("/history/{entry_id}")
def get_history(entry_id: str, c: ServiceContainer = Depends(get_container)):
    entry = c.history_service.get(entry_id)
    if not entry:
        return JSONResponse({"error": "not found"}, status_code=404)
    return entry
