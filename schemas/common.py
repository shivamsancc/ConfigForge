"""
Pydantic v2 schemas for ConfigForge's REST API.

Design notes
------------
* Domain objects (device, bandwidth cap, subnet, tag def) are highly flexible
  — they carry arbitrary tag fields, optional SNMP credentials, and can gain
  new top-level fields without a schema change.  ``model_config =
  ConfigDict(extra="allow")`` lets any extra keys pass through unmodified.
* Request bodies that wrap a domain object (e.g. ``{"device": {...},
  "_actor": "alice"}``) are modelled as simple Pydantic models with
  ``extra="allow"`` so new envelope keys don't break anything.
* Response models are kept deliberately loose for the same reason.

The main value these schemas add over plain ``dict`` annotations:
  - FastAPI generates correct OpenAPI documentation.
  - Mandatory fields surface as 422 errors before business logic runs.
  - Type coercions (e.g. list vs. None) happen at the boundary.
"""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class FlexModel(BaseModel):
    """Base model that allows (and preserves) extra fields."""
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

class DeviceBody(FlexModel):
    """Envelope for POST /api/devices."""
    device: dict[str, Any]
    _actor: Optional[str] = None


class DeviceResponse(FlexModel):
    device: dict[str, Any]


class DeviceListResponse(FlexModel):
    devices: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Bandwidth caps
# ---------------------------------------------------------------------------

class BandwidthBody(FlexModel):
    """Envelope for POST /api/bandwidth."""
    row: dict[str, Any]
    _actor: Optional[str] = None


class BandwidthResponse(FlexModel):
    row: dict[str, Any]


class BandwidthListResponse(FlexModel):
    rows: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------

class SubnetBody(FlexModel):
    """Envelope for POST /api/subnets."""
    subnet: dict[str, Any]
    _actor: Optional[str] = None


class SubnetResponse(FlexModel):
    subnet: dict[str, Any]


class SubnetListResponse(FlexModel):
    subnets: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

class TagBody(FlexModel):
    """Envelope for POST /api/tags."""
    tagDef: dict[str, Any]
    _actor: Optional[str] = None


class TagResponse(FlexModel):
    tagDef: dict[str, Any]


class TagListResponse(FlexModel):
    tagDefs: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Import / validate-import
# ---------------------------------------------------------------------------

class ImportDevicesBody(FlexModel):
    devices: list[dict[str, Any]]
    mode: str = "merge"
    _actor: Optional[str] = None


class ImportBandwidthBody(FlexModel):
    rows: list[dict[str, Any]]
    mode: str = "merge"
    _actor: Optional[str] = None


class ImportSubnetsBody(FlexModel):
    subnets: list[dict[str, Any]]
    mode: str = "merge"
    _actor: Optional[str] = None


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

class SetListBody(FlexModel):
    items: list[Any]
    _actor: Optional[str] = None


class ListsResponse(FlexModel):
    lists: dict[str, list[Any]]


# ---------------------------------------------------------------------------
# Generate / audit / history / meta
# ---------------------------------------------------------------------------

class GenerateBody(FlexModel):
    _actor: Optional[str] = None


class ErrorResponse(FlexModel):
    error: str
