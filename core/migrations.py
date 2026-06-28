"""
Schema migrations.

Every change to the database shape -- new tables, new columns, new
default rows, data reshaping -- goes here as a numbered migration, never
as an ad-hoc ALTER scattered through storage.py. This is what lets an
existing deployment upgrade safely: copy in new .py files, restart the
server, and any migrations that haven't run yet for that .db file run
automatically, in order, exactly once.

How to add a new migration:
  1. Write a function `def migrate_N(conn): ...` below the last one,
     where N is the next integer after the current highest.
  2. Add it to MIGRATIONS in order.
  3. It must be safe to run on a database that's never seen this
     migration before. It does NOT need to be safe to run twice --
     the runner tracks which versions have already applied and skips
     them -- but it must not assume anything about the exact prior
     state beyond "every earlier migration has already run."
  4. Never edit an old migration after it's been released. If something
     was wrong, add a new migration that fixes it forward.
"""
import sqlite3


def _get_schema_version(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int):
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )


def _table_exists(conn, name) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _column_exists(conn, table, column) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


# ---------------------------------------------------------------------------
# Migration 1: baseline tables (devices, bandwidth_caps, lists, audit_log,
# yaml_history, meta). Written defensively with CREATE TABLE IF NOT EXISTS
# so it's a no-op on a database storage.init() already created these in,
# and a real bootstrap on a truly empty file.
# ---------------------------------------------------------------------------
def migrate_1(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bandwidth_caps (
            id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lists (
            list_name TEXT PRIMARY KEY, items TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY, ts REAL NOT NULL, actor TEXT,
            action TEXT NOT NULL, details TEXT
        );
        CREATE TABLE IF NOT EXISTS yaml_history (
            id TEXT PRIMARY KEY, ts REAL NOT NULL, actor TEXT,
            summary TEXT, files TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT
        );
        """
    )


# ---------------------------------------------------------------------------
# Migration 2: Subnets + dynamic tag definitions table.
# ---------------------------------------------------------------------------
def migrate_2(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS subnets (
            id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tag_defs (
            id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL
        );
        """
    )


# ---------------------------------------------------------------------------
# Migration 3: retire the old fixed dropdown lists (Device Class, Device
# Category, Device Type) in favor of the dynamic tag system -- only
# Collector Region stays a hardcoded concept. Converts any existing
# values in those 3 lists into real tag definitions (scoped to devices),
# and migrates each device's stored field value into device.tags{} under
# the new tag id, so existing data isn't silently dropped.
#
# Collector Region is deliberately left as-is: it keeps its own `lists`
# row and its own top-level `Collector Region` field on devices, because
# it remains a first-class, mandatory concept rather than a tag.
# ---------------------------------------------------------------------------
def migrate_3(conn):
    import json
    import uuid
    import time

    legacy_list_to_tag_name = {
        "deviceClasses": "Device Class",
        "deviceCategories": "Device Category",
        "deviceTypes": "Device Type",
    }
    legacy_field_names = {
        "deviceClasses": "Device Class",
        "deviceCategories": "Device Category",
        "deviceTypes": "Device Type",
    }
    # These never had a managed "lists" entry, but still exist as bare
    # device fields from the era before tags existed at all.
    bare_field_names = ["Operating Region", "geolocation", "Region", "Center"]

    now = time.time()
    field_to_tag_id = {}

    # 1. Promote each legacy managed list (if it has any values, or even
    #    if empty -- the field existed and might still be in use on rows)
    #    into a real tag def scoped to devices.
    for list_name, tag_name in legacy_list_to_tag_name.items():
        row = conn.execute("SELECT items FROM lists WHERE list_name = ?", (list_name,)).fetchone()
        values = json.loads(row[0]) if row else []
        # Only create the tag if there's actually any sign this field was
        # used (existing values OR at least one device has a non-empty
        # value for it) -- otherwise we'd resurrect fields nobody used
        # just because the empty placeholder list existed.
        used = bool(values) or _any_device_has_field(conn, legacy_field_names[list_name])
        if not used:
            continue
        tag_id = str(uuid.uuid4())
        field_to_tag_id[legacy_field_names[list_name]] = tag_id
        conn.execute(
            "INSERT INTO tag_defs (id, data, updated_at) VALUES (?, ?, ?)",
            (tag_id, json.dumps({"id": tag_id, "name": tag_name, "scopes": ["devices"], "values": values}), now),
        )

    # 2. Bare fields (Operating Region, geolocation, Region, Center) never
    #    had a managed value list -- promote them only if at least one
    #    device actually has a non-empty value, with an empty starting
    #    value list (since there was never a curated set of options).
    for field_name in bare_field_names:
        if not _any_device_has_field(conn, field_name):
            continue
        tag_id = str(uuid.uuid4())
        field_to_tag_id[field_name] = tag_id
        conn.execute(
            "INSERT INTO tag_defs (id, data, updated_at) VALUES (?, ?, ?)",
            (tag_id, json.dumps({"id": tag_id, "name": field_name, "scopes": ["devices"], "values": []}), now),
        )

    # 3. Migrate each device's bare field values into device.tags{}, and
    #    register any value actually in use into the new tag's value list
    #    (covers values that were in use on devices but never added to
    #    the old managed list, which the old system allowed).
    if field_to_tag_id:
        rows = conn.execute("SELECT id, data FROM devices").fetchall()
        tag_value_additions = {tag_id: set() for tag_id in field_to_tag_id.values()}
        for row_id, data_json in rows:
            device = json.loads(data_json)
            tags = device.get("tags") or {}
            changed = False
            for field_name, tag_id in field_to_tag_id.items():
                value = device.get(field_name)
                if value:
                    tags[tag_id] = value
                    tag_value_additions[tag_id].add(value)
                    changed = True
                # Intentionally leave the old bare field in place rather
                # than deleting it -- harmless leftover key, and safer
                # than risking data loss if this migration has a bug.
            if changed:
                device["tags"] = tags
                conn.execute(
                    "UPDATE devices SET data = ? WHERE id = ?",
                    (json.dumps(device), row_id),
                )

        # Make sure every value actually seen on a device ends up in that
        # tag's selectable value list, even if it wasn't in the old
        # managed list (old system allowed free-form values to slip in
        # via direct API calls or earlier bugs).
        for tag_id, seen_values in tag_value_additions.items():
            if not seen_values:
                continue
            row = conn.execute("SELECT data FROM tag_defs WHERE id = ?", (tag_id,)).fetchone()
            if not row:
                continue
            tag_def = json.loads(row[0])
            existing = set(tag_def.get("values", []))
            merged = sorted(existing | seen_values)
            if merged != tag_def.get("values", []):
                tag_def["values"] = merged
                conn.execute("UPDATE tag_defs SET data = ? WHERE id = ?", (json.dumps(tag_def), tag_id))

    # 4. Remove the 3 legacy managed lists -- Collector Region's list
    #    entry is untouched.
    conn.execute(
        "DELETE FROM lists WHERE list_name IN ('deviceClasses', 'deviceCategories', 'deviceTypes')"
    )


def _any_device_has_field(conn, field_name) -> bool:
    import json
    rows = conn.execute("SELECT data FROM devices").fetchall()
    for (data_json,) in rows:
        device = json.loads(data_json)
        if device.get(field_name):
            return True
    return False


# ---------------------------------------------------------------------------
# Migration 4: reconcile the Collector Region list with reality.
#
# Excel import writes whatever's in the spreadsheet's Collector Region
# column straight onto each device (correctly -- import needs to allow a
# brand-new region), but an earlier version of the frontend never fed
# those new values back into the managed list, so a device could already
# have e.g. "AWS Mumbai" set while the Collector Region dropdown in
# Manage Lists stayed empty or incomplete. This is a one-time repair for
# anyone who imported devices before that registration existed: it scans
# every device's stored Collector Region and adds any value found there
# that isn't already in the list. Safe to run on a database where the
# list was always correct -- it's a no-op in that case.
# ---------------------------------------------------------------------------
def migrate_4(conn):
    import json

    row = conn.execute("SELECT items FROM lists WHERE list_name = 'collectorRegions'").fetchone()
    existing = set(json.loads(row[0])) if row else set()

    rows = conn.execute("SELECT data FROM devices").fetchall()
    seen = set()
    for (data_json,) in rows:
        device = json.loads(data_json)
        region = (device.get("Collector Region") or "").strip()
        if region:
            seen.add(region)

    missing = seen - existing
    if not missing:
        return

    merged = sorted(existing | missing)
    conn.execute(
        "INSERT INTO lists (list_name, items) VALUES ('collectorRegions', ?) "
        "ON CONFLICT(list_name) DO UPDATE SET items = excluded.items",
        (json.dumps(merged),),
    )
    print(f"[migrations] migrate_4: added {len(missing)} Collector Region value(s) found on devices but missing from the managed list: {sorted(missing)}")


MIGRATIONS = [
    (1, migrate_1),
    (2, migrate_2),
    (3, migrate_3),
    (4, migrate_4),
]


def run_pending_migrations(conn: sqlite3.Connection, verbose=True):
    """Runs every migration with a version greater than the database's
    current schema_version, in order, each inside its own transaction.
    Safe to call on every server startup."""
    # meta table might not exist yet on a truly fresh file -- migration 1
    # creates it, so bootstrap that one table first if needed.
    if not _table_exists(conn, "meta"):
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()

    current = _get_schema_version(conn)
    applied = []
    for version, fn in MIGRATIONS:
        if version <= current:
            continue
        if verbose:
            print(f"[migrations] applying migration {version} ({fn.__name__})...")
        try:
            fn(conn)
            _set_schema_version(conn, version)
            conn.commit()
            applied.append(version)
        except Exception:
            conn.rollback()
            print(f"[migrations] FAILED applying migration {version} -- database left at version {current}.")
            print(f"[migrations] back up your .db file before retrying, and check the error above.")
            raise
    if verbose:
        if applied:
            print(f"[migrations] applied {len(applied)} migration(s): {applied}. Database now at schema version {applied[-1]}.")
        else:
            print(f"[migrations] database already up to date (schema version {current}).")