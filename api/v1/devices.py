"""
API v1 router for /api/v1/devices.

Endpoints
---------
GET    /api/v1/devices
POST   /api/v1/devices/validate-import
POST   /api/v1/devices/import
POST   /api/v1/devices
DELETE /api/v1/devices/{id}
"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.dependencies import get_container
from core.container import ServiceContainer

router = APIRouter()


@router.get("/devices")
def list_devices(c: ServiceContainer = Depends(get_container)):
    return {"devices": c.device_service.list_devices()}


@router.post("/devices/validate-import")
def validate_import_devices(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    rows = body.get("devices")
    if not isinstance(rows, list):
        return JSONResponse({"error": "'devices' must be a list"}, status_code=400)
    mode = body.get("mode", "merge")
    return c.import_service.validate_import_devices(rows, mode)


@router.post("/devices/import")
def import_devices(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    rows = body.get("devices")
    if not isinstance(rows, list):
        return JSONResponse({"error": "'devices' must be a list"}, status_code=400)
    mode = body.get("mode", "merge")
    actor = body.get("_actor")
    return c.import_service.import_devices(rows, mode, actor)


@router.post("/devices")
def upsert_device(body: dict[str, Any], c: ServiceContainer = Depends(get_container)):
    device = body.get("device")
    if not isinstance(device, dict):
        return JSONResponse({"error": "'device' must be an object"}, status_code=400)
    actor = body.get("_actor")
    try:
        saved = c.device_service.create_or_update(device, actor)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"device": saved}


@router.delete("/devices/{device_id}")
def delete_device(device_id: str, request: Request, c: ServiceContainer = Depends(get_container)):
    actor = request.query_params.get("_actor")
    c.device_service.delete(device_id, actor)
    return {"deleted": device_id}
