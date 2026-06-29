"""
API v1 router for /api/v1/meta.

Endpoints
---------
GET /api/v1/meta  → {deviceCount, bandwidthCount, subnetCount, lastSavedAt, lastSavedBy}
"""
from fastapi import APIRouter, Depends

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.get("/meta")
def get_meta(c: ServiceContainer = Depends(get_container)):
    return c.meta_service.get_meta()
