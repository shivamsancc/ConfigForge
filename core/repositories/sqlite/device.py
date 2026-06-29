"""
SQLite implementation of IDeviceRepository.

SNMPv3 authKey and privKey are AES-256-GCM encrypted at rest using the
same static key as the original storage.py implementation.  The key is
intentionally embedded here (not a secret config value) — it protects
the raw .db file at rest, not the running application itself.
"""
import base64
import sqlite3
import threading
from typing import Optional

from core import aesgcm
from core.repositories.interfaces import IDeviceRepository
from core.repositories.sqlite.base import SQLiteBaseRepository

# ---------------------------------------------------------------------------
# Credential encryption (identical to the original storage.py logic)
# ---------------------------------------------------------------------------

_CRED_FIELDS: tuple[str, ...] = ("authKey", "privKey")

# 32-byte static key — see note in module docstring above.
_ENC_KEY: bytes = b"ConfigForge-static-at-rest-key!!"
assert len(_ENC_KEY) == 32


def _encrypt_field(value: str) -> str:
    blob = aesgcm.encrypt(_ENC_KEY, value.encode("utf-8"))
    return base64.b64encode(blob).decode("ascii")


def _decrypt_field(value: str) -> str:
    try:
        blob = base64.b64decode(value)
        return aesgcm.decrypt(_ENC_KEY, blob).decode("utf-8")
    except Exception:
        # Tolerate legacy/plaintext rows to avoid hard-crashing the read path.
        return value


def _encode_device(device: dict) -> dict:
    out = dict(device)
    for field in _CRED_FIELDS:
        if out.get(field):
            out[field] = _encrypt_field(out[field])
    return out


def _decode_device(device: dict) -> dict:
    out = dict(device)
    for field in _CRED_FIELDS:
        if out.get(field):
            out[field] = _decrypt_field(out[field])
    return out


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class SQLiteDeviceRepository(SQLiteBaseRepository, IDeviceRepository):
    """Persists device records in the ``devices`` SQLite table."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        super().__init__(conn, lock)

    def list_all(self) -> list[dict]:
        return self._list_rows("devices", decode=_decode_device)

    def get(self, device_id: str) -> Optional[dict]:
        return self._get_row("devices", device_id, decode=_decode_device)

    def upsert(self, device: dict) -> dict:
        return self._upsert_row("devices", device, encode=_encode_device)

    def delete(self, device_id: str) -> None:
        self._delete_row("devices", device_id)

    def replace_all(self, devices: list[dict]) -> None:
        self._replace_all("devices", devices, encode=_encode_device)

    def merge(self, devices: list[dict]) -> None:
        self._merge_rows("devices", devices, encode=_encode_device)
