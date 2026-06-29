"""
Storage façade — backward-compatible shim over the Repository layer.

This module preserves the original public API (``init()``, ``list_devices()``,
``upsert_device()``, etc.) so that existing code and tests that import
``core.storage`` continue to work without modification.

Internally every function now delegates to the matching repository or service
held in the module-level ``_container`` singleton, which is created by
``init()``.  No SQLite calls remain in this file; all persistence logic
lives in ``core/repositories/sqlite/``.

Architecture note
-----------------
New code should import and use services (``core.services.*``) or, where
only data retrieval is needed, repository interfaces (``core.repositories.*``).
This shim exists purely to avoid a big-bang migration of callers that were
written before the Repository Pattern was introduced.
"""
import ipaddress
import time

from core.container import ServiceContainer
from core.repositories.sqlite.list import FIXED_LISTS
from core.services.tag_service import TAG_SCOPES

# Re-export constants so ``storage.FIXED_LISTS`` and ``storage.TAG_SCOPES``
# continue to resolve correctly for any caller that references them.
FIXED_LISTS = FIXED_LISTS  # noqa: F811 — intentional re-assignment for re-export
TAG_SCOPES = TAG_SCOPES      # noqa: F811

_container: ServiceContainer | None = None


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init(db_path: str) -> None:
    """Open (or create) the SQLite database and run pending migrations."""
    global _container
    _container = ServiceContainer(db_path)


def _c() -> ServiceContainer:
    if _container is None:
        raise RuntimeError("storage.init() has not been called")
    return _container


# ---------------------------------------------------------------------------
# Time helpers (kept for any caller that imports them directly)
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def now_iso_from_unix(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def list_devices() -> list:
    return _c().device_repo.list_all()


def get_device(device_id: str):
    return _c().device_repo.get(device_id)


def upsert_device(device: dict) -> dict:
    return _c().device_repo.upsert(device)


def delete_device(device_id: str) -> None:
    _c().device_repo.delete(device_id)


def replace_all_devices(devices: list) -> None:
    _c().device_repo.replace_all(devices)


def merge_devices(devices: list) -> None:
    _c().device_repo.merge(devices)


# ---------------------------------------------------------------------------
# Bandwidth caps
# ---------------------------------------------------------------------------

def list_bandwidth() -> list:
    return _c().bandwidth_repo.list_all()


def get_bandwidth(row_id: str):
    return _c().bandwidth_repo.get(row_id)


def upsert_bandwidth(row: dict) -> dict:
    return _c().bandwidth_repo.upsert(row)


def delete_bandwidth(row_id: str) -> None:
    _c().bandwidth_repo.delete(row_id)


def replace_all_bandwidth(rows: list) -> None:
    _c().bandwidth_repo.replace_all(rows)


def merge_bandwidth(rows: list) -> None:
    _c().bandwidth_repo.merge(rows)


# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------

def list_subnets() -> list:
    return _c().subnet_repo.list_all()


def get_subnet(row_id: str):
    return _c().subnet_repo.get(row_id)


def upsert_subnet(row: dict) -> dict:
    return _c().subnet_repo.upsert(row)


def delete_subnet(row_id: str) -> None:
    _c().subnet_repo.delete(row_id)


def replace_all_subnets(rows: list) -> None:
    _c().subnet_repo.replace_all(rows)


def merge_subnets(rows: list) -> None:
    _c().subnet_repo.merge(rows)


def find_subnet_for_ip(ip_str: str, subnets: list | None = None):
    """Return the most-specific subnet containing ip_str, or None."""
    return _c().subnet_repo.find_for_ip(ip_str, subnets)


# ---------------------------------------------------------------------------
# Fixed lists
# ---------------------------------------------------------------------------

def get_lists() -> dict:
    return _c().list_repo.get_all()


def set_list(list_name: str, items: list) -> None:
    _c().list_repo.set_list(list_name, items)


def list_usage_count(list_name: str, value: str) -> int:
    return _c().list_service.usage_count(list_name, value)


# ---------------------------------------------------------------------------
# Dynamic tag definitions
# ---------------------------------------------------------------------------

def list_tag_defs() -> list:
    return _c().tag_repo.list_all()


def get_tag_def(tag_id: str):
    return _c().tag_repo.get(tag_id)


def upsert_tag_def(tag_def: dict) -> dict:
    return _c().tag_repo.upsert(tag_def)


def delete_tag_def(tag_id: str) -> None:
    _c().tag_repo.delete(tag_id)


def tag_def_usage_count(tag_id: str) -> int:
    return _c().tag_repo.usage_count(tag_id)


def tag_value_usage_count(tag_id: str, value: str) -> int:
    return _c().tag_repo.value_usage_count(tag_id, value)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def log_audit(actor, action: str, details=None) -> str:
    return _c().audit_repo.log(actor, action, details)


def list_audit(limit: int = 100) -> list:
    return _c().audit_repo.list_recent(limit)


# ---------------------------------------------------------------------------
# YAML history
# ---------------------------------------------------------------------------

def save_history(actor, summary: str, files: dict) -> str:
    entry_id = _c().history_repo.save(actor, summary, files)
    # Also update the meta timestamps so the dashboard stays current
    # (mirrors the original save_history behaviour).
    from core.repositories.sqlite.base import now_iso as _now_iso
    _c().meta_repo.set_kv("lastSavedAt", _now_iso())
    _c().meta_repo.set_kv("lastSavedBy", actor or "unknown")
    return entry_id


def list_history(limit: int = 50) -> list:
    return _c().history_repo.list_recent(limit)


def get_history_entry(entry_id: str):
    return _c().history_repo.get(entry_id)


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

def get_meta() -> dict:
    return _c().meta_service.get_meta()
