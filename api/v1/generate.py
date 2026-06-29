"""
API v1 router for /api/v1/generate.

Endpoints
---------
POST /api/v1/generate  body: {_actor}  → {files, groupStats, summary, findings}
"""
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.post("/generate")
def generate(body: dict[str, Any] = {}, c: ServiceContainer = Depends(get_container)):
    actor = body.get("_actor") if isinstance(body, dict) else None
    return c.generate_service.generate(actor)
