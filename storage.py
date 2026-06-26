"""
SQLite storage layer -- the shared, multi-user datastore that replaces the
old per-browser IndexedDB. One .db file lives on the FSx share; this module
is the only thing that talks to it.

Schema mirrors the IndexedDB stores from the browser-only version:
  devices, bandwidth_caps, lists, audit_log, yaml_history, meta

SNMPv3 authKey/privKey are encrypted at rest with AES-256-GCM (see
aesgcm.py) using a key derived from a constant embedded in this script.
This protects the .db file itself (e.g. someone browsing the FSx share
directly, or a backup) -- it does NOT add any access control to the web
app itself, and anyone with a copy of this script can decrypt any copy
of the .db. That's a deliberate, accepted tradeoff for simplicity.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time

import aesgcm

# ---------------------------------------------------------------------------
# Encryption key derivation
# ---------------------------------------------------------------------------
# This constant is the "key lives in the server script" choice: anyone with
# this file can derive the same key and decrypt any .db that was encrypted
# with it. That's a real, accepted limitation -- not a secret-keeping
# mechanism on its own, just a deterrent against casually opening the raw
# .db file or a backup of it.
_KEY_MATERIAL = b"snmp-yaml-generator-fsx-shared-credential-key-v1"
_ENC_KEY = hashlib.sha256(_KEY_MATERIAL).digest()  # 32 bytes -> AES-256
_AAD = b"snmpv3-credential-field"

_CRED_FIELDS = ("authKey", "privKey")


def _encrypt_field(plaintext: str) -> str:
    if not plaintext:
        return ""
    blob = aesgcm.encrypt(_ENC_KEY, plaintext.encode("utf-8"), _AAD)
    return "enc1:" + blob.hex()


def _decrypt_field(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith("enc1:"):
        # Unencrypted legacy/imported value -- pass through rather than
        # crash, so a hand-built import sheet or pre-migration row isn't
        # rejected outright.
        return stored
    blob = bytes.fromhex(stored[5:])
    try:
        return aesgcm.decrypt(_ENC_KEY, blob, _AAD).decode("utf-8")
    except ValueError:
        # Tampered or wrong key -- surface clearly rather than silently
        # returning garbage that might get pasted into a device config.
        return "<DECRYPTION FAILED -- credential may be corrupt>"


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_DB_PATH = None
_conn = None


def init(db_path: str):
    global _DB_PATH, _conn
    _DB_PATH = db_path
    first_time = not os.path.exists(db_path)
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA foreign_keys=ON")
    _conn.row_factory = sqlite3.Row
    _create_schema()
    return first_time


def _create_schema():
    with _lock:
        c = _conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bandwidth_caps (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS lists (
                list_name TEXT PRIMARY KEY,
                items TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                actor TEXT,
                action TEXT NOT NULL,
                details TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS yaml_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                actor TEXT,
                summary TEXT,
                files TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_ts ON yaml_history(ts)")
        _conn.commit()

        for list_name in ("collectorRegions", "deviceClasses", "deviceCategories", "deviceTypes"):
            c.execute("INSERT OR IGNORE INTO lists (list_name, items) VALUES (?, ?)",
                       (list_name, json.dumps([])))
        _conn.commit()


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def _encode_device(device: dict) -> dict:
    """Encrypt credential fields before storing."""
    out = dict(device)
    for field in _CRED_FIELDS:
        if field in out and out[field]:
            out[field] = _encrypt_field(out[field])
    return out


def _decode_device(device: dict) -> dict:
    out = dict(device)
    for field in _CRED_FIELDS:
        if field in out and out[field]:
            out[field] = _decrypt_field(out[field])
    return out


def list_devices() -> list:
    with _lock:
        rows = _conn.execute("SELECT data FROM devices ORDER BY updated_at ASC").fetchall()
    return [_decode_device(json.loads(r["data"])) for r in rows]


def get_device(device_id: str):
    with _lock:
        row = _conn.execute("SELECT data FROM devices WHERE id = ?", (device_id,)).fetchone()
    if not row:
        return None
    return _decode_device(json.loads(row["data"]))


def upsert_device(device: dict):
    if "id" not in device or not device["id"]:
        raise ValueError("device must have an id")
    encoded = _encode_device(device)
    with _lock:
        _conn.execute(
            "INSERT INTO devices (id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (device["id"], json.dumps(encoded), time.time()),
        )
        _conn.commit()


def delete_device(device_id: str):
    with _lock:
        _conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        _conn.commit()


def replace_all_devices(devices: list):
    """Used by full-dataset import (merge=replace)."""
    with _lock:
        _conn.execute("DELETE FROM devices")
        now = time.time()
        for d in devices:
            encoded = _encode_device(d)
            _conn.execute(
                "INSERT INTO devices (id, data, updated_at) VALUES (?, ?, ?)",
                (d["id"], json.dumps(encoded), now),
            )
        _conn.commit()


def merge_devices(devices: list):
    """Used by full-dataset import (merge=merge): upsert by id."""
    for d in devices:
        upsert_device(d)


# ---------------------------------------------------------------------------
# Bandwidth caps
# ---------------------------------------------------------------------------

def list_bandwidth_caps() -> list:
    with _lock:
        rows = _conn.execute("SELECT data FROM bandwidth_caps ORDER BY updated_at ASC").fetchall()
    return [json.loads(r["data"]) for r in rows]


def upsert_bandwidth_cap(row: dict):
    if "id" not in row or not row["id"]:
        raise ValueError("bandwidth cap row must have an id")
    with _lock:
        _conn.execute(
            "INSERT INTO bandwidth_caps (id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (row["id"], json.dumps(row), time.time()),
        )
        _conn.commit()


def delete_bandwidth_cap(row_id: str):
    with _lock:
        _conn.execute("DELETE FROM bandwidth_caps WHERE id = ?", (row_id,))
        _conn.commit()


def replace_all_bandwidth_caps(rows: list):
    with _lock:
        _conn.execute("DELETE FROM bandwidth_caps")
        now = time.time()
        for r in rows:
            _conn.execute(
                "INSERT INTO bandwidth_caps (id, data, updated_at) VALUES (?, ?, ?)",
                (r["id"], json.dumps(r), now),
            )
        _conn.commit()


def merge_bandwidth_caps(rows: list):
    for r in rows:
        upsert_bandwidth_cap(r)


# ---------------------------------------------------------------------------
# Managed lists
# ---------------------------------------------------------------------------

_LIST_NAMES = ("collectorRegions", "deviceClasses", "deviceCategories", "deviceTypes")


def get_list(list_name: str) -> list:
    with _lock:
        row = _conn.execute("SELECT items FROM lists WHERE list_name = ?", (list_name,)).fetchone()
    if not row:
        return []
    return json.loads(row["items"])


def get_all_lists() -> dict:
    return {name: get_list(name) for name in _LIST_NAMES}


def set_list(list_name: str, items: list):
    with _lock:
        _conn.execute(
            "INSERT INTO lists (list_name, items) VALUES (?, ?) "
            "ON CONFLICT(list_name) DO UPDATE SET items = excluded.items",
            (list_name, json.dumps(items)),
        )
        _conn.commit()


def add_to_list_if_missing(list_name: str, value: str):
    if not value:
        return
    items = get_list(list_name)
    if value not in items:
        items.append(value)
        set_list(list_name, items)


def count_list_value_usage(list_name: str, value: str) -> int:
    """How many devices currently use this value (for the 'in use' warning on removal)."""
    field_map = {
        "collectorRegions": "Collector Region",
        "deviceClasses": "Device Class",
        "deviceCategories": "Device Category",
        "deviceTypes": "Device Type",
    }
    field = field_map.get(list_name)
    if not field:
        return 0
    count = 0
    for d in list_devices():
        if d.get(field) == value:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def log_action(actor: str, action: str, details: dict = None):
    with _lock:
        _conn.execute(
            "INSERT INTO audit_log (ts, actor, action, details) VALUES (?, ?, ?, ?)",
            (time.time(), actor or "", action, json.dumps(details or {})),
        )
        _conn.commit()


def list_audit_log(limit: int = 500) -> list:
    with _lock:
        rows = _conn.execute(
            "SELECT id, ts, actor, action, details FROM audit_log ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"id": r["id"], "ts": r["ts"], "actor": r["actor"], "action": r["action"],
         "details": json.loads(r["details"]) if r["details"] else {}}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# YAML history
# ---------------------------------------------------------------------------

def save_yaml_history(actor: str, summary: str, files: dict):
    """`files` is {filename: yaml_text} for the generated batch."""
    with _lock:
        _conn.execute(
            "INSERT INTO yaml_history (ts, actor, summary, files) VALUES (?, ?, ?, ?)",
            (time.time(), actor or "", summary, json.dumps(files)),
        )
        _conn.commit()


def list_yaml_history(limit: int = 100) -> list:
    with _lock:
        rows = _conn.execute(
            "SELECT id, ts, actor, summary FROM yaml_history ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"id": r["id"], "ts": r["ts"], "actor": r["actor"], "summary": r["summary"]} for r in rows]


def get_yaml_history_entry(entry_id: int):
    with _lock:
        row = _conn.execute(
            "SELECT id, ts, actor, summary, files FROM yaml_history WHERE id = ?",
            (entry_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"], "ts": row["ts"], "actor": row["actor"],
        "summary": row["summary"], "files": json.loads(row["files"]),
    }


# ---------------------------------------------------------------------------
# Meta (e.g. last-imported-at, schema version)
# ---------------------------------------------------------------------------

def get_meta(key: str, default=None):
    with _lock:
        row = _conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value: str):
    with _lock:
        _conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        _conn.commit()
