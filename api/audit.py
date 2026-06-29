"""
FastAPI router for /api/audit.

Endpoints
---------
GET /api/audit  query: limit  → {entries: [...]}
"""
from fastapi import APIRouter, Depends, Request

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.get("/audit")
def list_audit(request: Request, c: ServiceContainer = Depends(get_container)):
    limit = int(request.query_params.get("limit", "100"))
    return {"entries": c.audit_service.list_recent(limit)}
