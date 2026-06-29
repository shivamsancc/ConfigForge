"""
Import diff engine.

``diff_import`` is the sole public entry point.  It receives already-loaded
plain Python lists and returns a structured diff describing exactly what a
proposed import would change — without touching SQLite, without knowing
about HTTP, and without side effects.

The engine is deliberately scope-agnostic: the same code path is suitable
for future YAML diff, inventory history comparison, and rollback previews.

Diff result schema
------------------
::

    {
        "new": [
            {"key": str, "label": str}
        ],
        "modified": [
            {
                "key":     str,
                "label":   str,
                "changes": [
                    {"field": str, "old": str, "new": str}
                    # for credential fields: {"field": str, "credential": True}
                ]
            }
        ],
        "unchanged": int,
        "removed":   [{"key": str, "label": str}]   # replace mode; always [] in merge
    }

Where:

key
    Stable machine-readable identifier for the record.
    Devices → IP address.
    Bandwidth → ``"<IP>|<Interface>"``.
    Subnets → normalised CIDR (``ip_network(strict=False)``).

label
    Human-readable string for display in the UI.

changes
    Field-level differences on a modified record.  Each entry has ``field``
    (the display name), and either ``old`` + ``new`` strings **or** the
    ``credential`` flag (True) indicating a credential field changed without
    revealing its value.

    Only changed fields appear in the list; unchanged fields are omitted.

Natural keys used per scope
---------------------------
Scope       Key field(s)          Note
----------  --------------------  ----------------------------------------
devices     IP                    First occurrence wins when duplicates exist
bandwidth   (IP, Interface)       First occurrence wins
subnets     normalised CIDR       ip_network(strict=False) before comparison

Field coverage
--------------
Scope       Compared fields
----------  ---------------------------------------------------------------
devices     Device, Collector Region, Config Type, Remarks,
            snmpUser, authProtocol, authKey*, privProtocol, privKey*, tags
bandwidth   Allocated BW, Region, Center, Link Type, Interface_description,
            tags
subnets     Description, tags

(*) Credential fields — value is never included in the diff output;
    a ``{"field": ..., "credential": True}`` entry indicates the field
    changed without revealing what it changed to or from.
"""
import ipaddress

# Fields whose values must never appear in the diff payload sent to browsers.
_CREDENTIAL_FIELDS = frozenset({"authKey", "privKey"})

# Fields to compare per scope (order determines display order in the UI).
_DEVICE_FIELDS = [
    "Device",
    "Collector Region",
    "Config Type",
    "Remarks",
    "snmpUser",
    "authProtocol",
    "authKey",
    "privProtocol",
    "privKey",
]

_BANDWIDTH_FIELDS = [
    "Allocated BW",
    "Region",
    "Center",
    "Link Type",
    "Interface_description",
]

_SUBNET_FIELDS = [
    "Description",
]


# ===========================================================================
# Public API
# ===========================================================================

def diff_import(scope: str, incoming: list, existing: list,
                mode: str, tag_defs: list = None) -> dict:
    """Compare *incoming* records against *existing* and return a diff dict.

    Parameters
    ----------
    scope
        ``"devices"``, ``"bandwidth"``, or ``"subnets"``.
    incoming
        Parsed records from the Excel import, not yet written to the DB.
        Same format as the lists returned by ``storage.list_*``.
    existing
        Current database records, already loaded by the caller.
    mode
        ``"merge"`` or ``"replace"``.  Only ``"replace"`` produces a
        non-empty ``removed`` list.
    tag_defs
        Tag definition list from ``storage.list_tag_defs()``.  Used to
        resolve tag IDs to human-readable names in the change list.

    Returns
    -------
    dict
        Diff result (see module docstring for schema).
    """
    tag_defs = tag_defs or []
    tag_name_by_id = {td["id"]: td["name"] for td in tag_defs}

    if scope == "devices":
        return _diff_devices(incoming, existing, mode, tag_name_by_id)
    if scope == "bandwidth":
        return _diff_bandwidth(incoming, existing, mode, tag_name_by_id)
    if scope == "subnets":
        return _diff_subnets(incoming, existing, mode, tag_name_by_id)
    raise ValueError(f"unknown diff scope: {scope!r}")


# ===========================================================================
# Internal helpers — normalisation
# ===========================================================================

def _norm(value) -> str:
    """Normalise any field value to a comparable string."""
    if value is None:
        return ""
    return str(value).strip()


def _norm_cidr(cidr: str) -> str:
    """Return the canonical network address string, or the raw value on error."""
    raw = cidr.strip()
    if not raw:
        return ""
    try:
        return str(ipaddress.ip_network(raw, strict=False))
    except ValueError:
        return raw  # invalid CIDRs are flagged by the validator; keep as-is


# ===========================================================================
# Internal helpers — key and label functions
# ===========================================================================

def _device_key(record: dict) -> str:
    return (record.get("IP") or "").strip()


def _device_label(record: dict) -> str:
    name = (record.get("Device") or "").strip()
    ip = _device_key(record)
    return f"{name} ({ip})" if name else ip


def _bandwidth_key(record: dict) -> str:
    ip = (record.get("IP") or "").strip()
    iface = (record.get("Interface") or "").strip()
    if not ip or not iface:
        return ""
    return f"{ip}|{iface}"


def _bandwidth_label(record: dict) -> str:
    ip = (record.get("IP") or "").strip()
    iface = (record.get("Interface") or "").strip()
    return f"{ip} / {iface}"


def _subnet_key(record: dict) -> str:
    return _norm_cidr((record.get("CIDR") or "").strip())


def _subnet_label(record: dict) -> str:
    cidr = (record.get("CIDR") or "").strip()
    desc = (record.get("Description") or "").strip()
    return f"{desc} ({cidr})" if desc else cidr


# ===========================================================================
# Per-scope diff dispatchers
# ===========================================================================

def _diff_devices(incoming, existing, mode, tag_name_by_id):
    existing_by_key = {
        _device_key(r): r
        for r in existing
        if _device_key(r)
    }
    incoming_by_key = _first_occurrence(
        incoming, key_fn=_device_key
    )
    return _diff_records(
        incoming_by_key, existing_by_key, mode, tag_name_by_id,
        compare_fields=_DEVICE_FIELDS,
        label_fn=_device_label,
    )


def _diff_bandwidth(incoming, existing, mode, tag_name_by_id):
    existing_by_key = {
        _bandwidth_key(r): r
        for r in existing
        if _bandwidth_key(r)
    }
    incoming_by_key = _first_occurrence(
        incoming, key_fn=_bandwidth_key
    )
    return _diff_records(
        incoming_by_key, existing_by_key, mode, tag_name_by_id,
        compare_fields=_BANDWIDTH_FIELDS,
        label_fn=_bandwidth_label,
    )


def _diff_subnets(incoming, existing, mode, tag_name_by_id):
    existing_by_key = {
        _subnet_key(r): r
        for r in existing
        if _subnet_key(r)
    }
    incoming_by_key = _first_occurrence(
        incoming, key_fn=_subnet_key
    )
    return _diff_records(
        incoming_by_key, existing_by_key, mode, tag_name_by_id,
        compare_fields=_SUBNET_FIELDS,
        label_fn=_subnet_label,
    )


# ===========================================================================
# Generic record diff
# ===========================================================================

def _first_occurrence(records: list, key_fn) -> dict:
    """Return {key: record} keeping the first record for each key."""
    result = {}
    for r in records:
        k = key_fn(r)
        if k and k not in result:
            result[k] = r
    return result


def _diff_records(incoming_by_key: dict, existing_by_key: dict,
                  mode: str, tag_name_by_id: dict,
                  compare_fields: list, label_fn) -> dict:
    """Generic diff for any scope.

    Returns a diff dict with ``new``, ``modified``, ``unchanged``, and
    ``removed`` lists/counts.
    """
    new_items = []
    modified_items = []
    unchanged_count = 0

    for key, inc in incoming_by_key.items():
        if key not in existing_by_key:
            new_items.append({"key": key, "label": label_fn(inc)})
        else:
            ex = existing_by_key[key]
            changes = _compute_changes(inc, ex, compare_fields, tag_name_by_id)
            if changes:
                modified_items.append({
                    "key": key,
                    "label": label_fn(inc),
                    "changes": changes,
                })
            else:
                unchanged_count += 1

    removed_items = []
    if mode == "replace":
        for key, ex in existing_by_key.items():
            if key not in incoming_by_key:
                removed_items.append({"key": key, "label": label_fn(ex)})

    return {
        "new": new_items,
        "modified": modified_items,
        "unchanged": unchanged_count,
        "removed": removed_items,
    }


def _compute_changes(incoming: dict, existing: dict,
                     compare_fields: list, tag_name_by_id: dict) -> list:
    """Return a list of field-level changes between *incoming* and *existing*.

    Each entry is one of:

    * ``{"field": str, "old": str, "new": str}``  — plain field
    * ``{"field": str, "credential": True}``        — credential changed, value hidden
    """
    changes = []

    for field in compare_fields:
        old_val = _norm(existing.get(field))
        new_val = _norm(incoming.get(field))
        if old_val == new_val:
            continue
        if field in _CREDENTIAL_FIELDS:
            changes.append({"field": field, "credential": True})
        else:
            changes.append({"field": field, "old": old_val, "new": new_val})

    # Tag comparison: compare by tag ID, display by resolved tag name.
    old_tags = existing.get("tags") or {}
    new_tags = incoming.get("tags") or {}
    all_tag_ids = sorted(set(old_tags) | set(new_tags))
    for tag_id in all_tag_ids:
        old_val = _norm(old_tags.get(tag_id))
        new_val = _norm(new_tags.get(tag_id))
        if old_val == new_val:
            continue
        tag_name = tag_name_by_id.get(tag_id, tag_id)
        changes.append({"field": tag_name, "old": old_val, "new": new_val})

    return changes
