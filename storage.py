"""
Storage layer: SQLite (WAL mode), thread-safe via a global lock.

Tables (created/evolved by migrations.py, never directly here):
  devices         - one row per device, JSON blob + indexed id
  bandwidth_caps  - one row per bandwidth cap entry
  subnets         - one row per subnet (CIDR-based)
  lists           - the one fixed managed dropdown: Collector Region.
                    Every other categorization (Device Class, Region,
                    custom fields, etc.) lives in tag_defs instead --
                    Collector Region is the sole exception because it's
                    mandatory and drives YAML generation directly.
  tag_defs        - dynamic tag list definitions, each with a name, the
                    scopes (devices/bandwidth/subnets) it applies to, and
                    its set of allowed values
  audit_log       - append-only action log
  yaml_history    - past generations
  meta            - small key/value store (lastSavedAt, lastSavedBy, schema_version)

SNMPv3 authKey/privKey are AES-256-GCM encrypted at rest (aesgcm.py).
"""
import base64
import json
import sqlite3
import threading
import time
import uuid
import ipaddress

import aesgcm
import migrations

_lock = threading.Lock()
_conn: sqlite3.Connection = None

_CRED_FIELDS = ("authKey", "privKey")

# Fixed key embedded here on purpose (see README: protects the raw .db
# file at rest, not the running app itself — known, accepted tradeoff).
_ENC_KEY = b"ConfigForge-static-at-rest-key!!"  # exactly 32 bytes
assert len(_ENC_KEY) == 32

# Collector Region is the only field that remains a hardcoded, mandatory
# concept -- it's what generation groups devices by, so the system can't
# function without it. Every other categorization is created on demand
# through the Tags module (see migrations.py migrate_3 for how
# Device Class / Device Category / Device Type / Operating Region /
# geolocation / Region / Center get migrated into tags for upgraders).
FIXED_LISTS = ("collectorRegions",)
TAG_SCOPES = ("devices", "bandwidth", "subnets")


def init(db_path: str):
    global _conn
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    with _lock:
        migrations.run_pending_migrations(_conn)
        for name in FIXED_LISTS:
            _conn.execute(
                "INSERT OR IGNORE INTO lists (list_name, items) VALUES (?, ?)",
                (name, json.dumps([])),
            )
        _conn.commit()


def now_iso():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


# ---------------------------------------------------------------------------
# Credential encryption
# ---------------------------------------------------------------------------
def _encrypt_field(value: str) -> str:
    blob = aesgcm.encrypt(_ENC_KEY, value.encode("utf-8"))
    return base64.b64encode(blob).decode("ascii")


def _decrypt_field(value: str) -> str:
    try:
        blob = base64.b64decode(value)
        return aesgcm.decrypt(_ENC_KEY, blob).decode("utf-8")
    except Exception:
        # Tolerate legacy/plaintext rows rather than hard-crash the read path.
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
# Generic row CRUD (shared shape for devices / bandwidth_caps / subnets)
# ---------------------------------------------------------------------------
def _list_rows(table, decode=None):
    with _lock:
        rows = _conn.execute(f"SELECT data FROM {table} ORDER BY updated_at ASC").fetchall()
    out = [json.loads(r["data"]) for r in rows]
    return [decode(r) for r in out] if decode else out


def _get_row(table, row_id, decode=None):
    with _lock:
        row = _conn.execute(f"SELECT data FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if not row:
        return None
    data = json.loads(row["data"])
    return decode(data) if decode else data


def _upsert_row(table, row: dict, encode=None):
    if not row.get("id"):
        row["id"] = str(uuid.uuid4())
    row.setdefault("tags", {})
    encoded = encode(row) if encode else row
    with _lock:
        _conn.execute(
            f"INSERT INTO {table} (id, data, updated_at) VALUES (?, ?, ?) "
            f"ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (row["id"], json.dumps(encoded), time.time()),
        )
        _conn.commit()
    return row


def _delete_row(table, row_id):
    with _lock:
        _conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        _conn.commit()


def _replace_all(table, rows: list, encode=None):
    with _lock:
        _conn.execute(f"DELETE FROM {table}")
        now = time.time()
        for r in rows:
            if not r.get("id"):
                r["id"] = str(uuid.uuid4())
            r.setdefault("tags", {})
            encoded = encode(r) if encode else r
            _conn.execute(
                f"INSERT INTO {table} (id, data, updated_at) VALUES (?, ?, ?)",
                (r["id"], json.dumps(encoded), now),
            )
        _conn.commit()


def _merge_rows(table, rows: list, encode=None):
    for r in rows:
        _upsert_row(table, r, encode=encode)


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------
def list_devices():
    return _list_rows("devices", decode=_decode_device)


def get_device(device_id):
    return _get_row("devices", device_id, decode=_decode_device)


def upsert_device(device: dict):
    return _upsert_row("devices", device, encode=_encode_device)


def delete_device(device_id):
    _delete_row("devices", device_id)


def replace_all_devices(devices: list):
    _replace_all("devices", devices, encode=_encode_device)


def merge_devices(devices: list):
    _merge_rows("devices", devices, encode=_encode_device)


# ---------------------------------------------------------------------------
# Bandwidth caps
# ---------------------------------------------------------------------------
def list_bandwidth():
    return _list_rows("bandwidth_caps")


def get_bandwidth(row_id):
    return _get_row("bandwidth_caps", row_id)


def upsert_bandwidth(row: dict):
    return _upsert_row("bandwidth_caps", row)


def delete_bandwidth(row_id):
    _delete_row("bandwidth_caps", row_id)


def replace_all_bandwidth(rows: list):
    _replace_all("bandwidth_caps", rows)


def merge_bandwidth(rows: list):
    _merge_rows("bandwidth_caps", rows)


# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------
def list_subnets():
    return _list_rows("subnets")


def get_subnet(row_id):
    return _get_row("subnets", row_id)


def upsert_subnet(row: dict):
    return _upsert_row("subnets", row)


def delete_subnet(row_id):
    _delete_row("subnets", row_id)


def replace_all_subnets(rows: list):
    _replace_all("subnets", rows)


def merge_subnets(rows: list):
    _merge_rows("subnets", rows)


def find_subnet_for_ip(ip_str: str, subnets: list = None):
    """Return the first subnet row whose CIDR contains ip_str, or None.
    If multiple subnets match, the most specific (longest prefix /
    smallest range) wins, since that's the conventional CIDR resolution
    rule and avoids an arbitrary pick when subnets overlap."""
    if not ip_str:
        return None
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return None
    if subnets is None:
        subnets = list_subnets()
    best = None
    best_prefix = -1
    for s in subnets:
        cidr = (s.get("CIDR") or "").strip()
        if not cidr:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if ip in net and net.prefixlen > best_prefix:
            best = s
            best_prefix = net.prefixlen
    return best


# ---------------------------------------------------------------------------
# Fixed lists (Collector Region only -- see module docstring)
# ---------------------------------------------------------------------------
def get_lists():
    with _lock:
        rows = _conn.execute("SELECT list_name, items FROM lists").fetchall()
    return {r["list_name"]: json.loads(r["items"]) for r in rows}


def set_list(list_name, items: list):
    with _lock:
        _conn.execute(
            "INSERT INTO lists (list_name, items) VALUES (?, ?) "
            "ON CONFLICT(list_name) DO UPDATE SET items = excluded.items",
            (list_name, json.dumps(items)),
        )
        _conn.commit()


def list_usage_count(list_name, value):
    """How many devices currently have `value` set for the field that
    corresponds to `list_name`. Collector Region is the only fixed list
    left -- everything else lives in tag_defs and uses tag_value_usage_count."""
    field_map = {"collectorRegions": "Collector Region"}
    field = field_map.get(list_name)
    if not field:
        return 0
    count = 0
    for d in list_devices():
        if d.get(field) == value:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Dynamic tag definitions
# ---------------------------------------------------------------------------
def list_tag_defs():
    with _lock:
        rows = _conn.execute("SELECT data FROM tag_defs ORDER BY updated_at ASC").fetchall()
    return [json.loads(r["data"]) for r in rows]


def get_tag_def(tag_id):
    with _lock:
        row = _conn.execute("SELECT data FROM tag_defs WHERE id = ?", (tag_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def upsert_tag_def(tag_def: dict):
    """tag_def shape: {id, name, scopes: ["devices","bandwidth","subnets"], values: [...]}"""
    if not tag_def.get("id"):
        tag_def["id"] = str(uuid.uuid4())
    tag_def.setdefault("scopes", [])
    tag_def.setdefault("values", [])
    with _lock:
        _conn.execute(
            "INSERT INTO tag_defs (id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (tag_def["id"], json.dumps(tag_def), time.time()),
        )
        _conn.commit()
    return tag_def


def delete_tag_def(tag_id):
    with _lock:
        _conn.execute("DELETE FROM tag_defs WHERE id = ?", (tag_id,))
        _conn.commit()


_SCOPE_TABLE = {"devices": "devices", "bandwidth": "bandwidth_caps", "subnets": "subnets"}


def tag_def_usage_count(tag_id):
    """Total number of records (across all scopes this tag applies to)
    that currently have a non-empty value set for this tag."""
    tag_def = get_tag_def(tag_id)
    if not tag_def:
        return 0
    count = 0
    for scope in tag_def.get("scopes", []):
        table = _SCOPE_TABLE.get(scope)
        if not table:
            continue
        with _lock:
            rows = _conn.execute(f"SELECT data FROM {table}").fetchall()
        for r in rows:
            data = json.loads(r["data"])
            if (data.get("tags") or {}).get(tag_id):
                count += 1
    return count


def tag_value_usage_count(tag_id, value):
    """How many records currently have this exact value set for this tag."""
    tag_def = get_tag_def(tag_id)
    if not tag_def:
        return 0
    count = 0
    for scope in tag_def.get("scopes", []):
        table = _SCOPE_TABLE.get(scope)
        if not table:
            continue
        with _lock:
            rows = _conn.execute(f"SELECT data FROM {table}").fetchall()
        for r in rows:
            data = json.loads(r["data"])
            if (data.get("tags") or {}).get(tag_id) == value:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def log_audit(actor, action, details=None):
    entry_id = str(uuid.uuid4())
    with _lock:
        _conn.execute(
            "INSERT INTO audit_log (id, ts, actor, action, details) VALUES (?, ?, ?, ?, ?)",
            (entry_id, time.time(), actor or "unknown", action, json.dumps(details) if details is not None else None),
        )
        _conn.commit()
    return entry_id


def list_audit(limit=100):
    with _lock:
        rows = _conn.execute(
            "SELECT id, ts, actor, action, details FROM audit_log ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "ts": now_iso_from_unix(r["ts"]),
            "actor": r["actor"],
            "action": r["action"],
            "details": json.loads(r["details"]) if r["details"] else None,
        })
    return out


def now_iso_from_unix(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# ---------------------------------------------------------------------------
# YAML history
# ---------------------------------------------------------------------------
def save_history(actor, summary, files: dict):
    entry_id = str(uuid.uuid4())
    with _lock:
        _conn.execute(
            "INSERT INTO yaml_history (id, ts, actor, summary, files) VALUES (?, ?, ?, ?, ?)",
            (entry_id, time.time(), actor or "unknown", summary, json.dumps(files)),
        )
        _conn.commit()
        _conn.execute(
            "INSERT INTO meta (key, value) VALUES ('lastSavedAt', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (now_iso(),),
        )
        _conn.execute(
            "INSERT INTO meta (key, value) VALUES ('lastSavedBy', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (actor or "unknown",),
        )
        _conn.commit()
    return entry_id


def list_history(limit=50):
    with _lock:
        rows = _conn.execute(
            "SELECT id, ts, actor, summary FROM yaml_history ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"id": r["id"], "ts": now_iso_from_unix(r["ts"]), "actor": r["actor"], "summary": r["summary"]} for r in rows]


def get_history_entry(entry_id):
    with _lock:
        row = _conn.execute(
            "SELECT id, ts, actor, summary, files FROM yaml_history WHERE id = ?", (entry_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"], "ts": now_iso_from_unix(row["ts"]), "actor": row["actor"],
        "summary": row["summary"], "files": json.loads(row["files"]),
    }


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------
def get_meta():
    with _lock:
        rows = _conn.execute("SELECT key, value FROM meta").fetchall()
    m = {r["key"]: r["value"] for r in rows}
    return {
        "deviceCount": len(list_devices()),
        "bandwidthCount": len(list_bandwidth()),
        "subnetCount": len(list_subnets()),
        "lastSavedAt": m.get("lastSavedAt"),
        "lastSavedBy": m.get("lastSavedBy"),
    }
