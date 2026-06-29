"""
FastAPI router for /api/export.

Endpoints
---------
GET /api/export/devices.xlsx    → binary xlsx
GET /api/export/bandwidth.xlsx  → binary xlsx
GET /api/export/subnets.xlsx    → binary xlsx
"""
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from api.dependencies import get_container
from core.container import ServiceContainer

_XLSX_CTYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter()


@router.get("/export/devices.xlsx")
def export_devices(c: ServiceContainer = Depends(get_container)):
    data = c.export_service.build_devices_xlsx()
    return Response(
        content=data,
        media_type=_XLSX_CTYPE,
        headers={"Content-Disposition": 'attachment; filename="devices_export.xlsx"'},
    )


@router.get("/export/bandwidth.xlsx")
def export_bandwidth(c: ServiceContainer = Depends(get_container)):
    data = c.export_service.build_bandwidth_xlsx()
    return Response(
        content=data,
        media_type=_XLSX_CTYPE,
        headers={"Content-Disposition": 'attachment; filename="bandwidth_export.xlsx"'},
    )


@router.get("/export/subnets.xlsx")
def export_subnets(c: ServiceContainer = Depends(get_container)):
    data = c.export_service.build_subnets_xlsx()
    return Response(
        content=data,
        media_type=_XLSX_CTYPE,
        headers={"Content-Disposition": 'attachment; filename="subnets_export.xlsx"'},
    )
