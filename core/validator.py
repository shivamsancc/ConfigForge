"""
Inventory-level validation engine.

``validate_inventory`` is the sole public entry point.  It receives
already-loaded plain Python lists (the same objects returned by
``storage.list_*``) and returns a sorted, flat list of findings.  It
never touches SQLite, never knows about HTTP, and has no side effects.

Each finding is a plain dict::

    {
        "code":     str  — machine-readable rule identifier (see below)
        "severity": str  — "error" | "warning"
        "category": str  — "inventory" | "snmp" | "network" | "generation"
        "message":  str  — human-readable description with enough context
                           for an operator to act without querying anything else
    }

When multiple devices (or rows) trigger the same rule the check produces
a *single* finding whose message aggregates all affected entities.  This
keeps the findings list short and the frontend rendering simple.

Findings are sorted errors-first, then warnings; within each severity
they are sorted alphabetically by message for deterministic output.

Rules implemented
-----------------
Code                      Sev      Category    Description
------------------------- -------- ----------- -----------------------------------
DEVICE_NO_IP              error    generation  Device row has a blank IP field.
DEVICE_INVALID_IP         error    network     Device IP is not a valid address.
DEVICE_DUPLICATE_IP       warning  inventory   Two or more devices share an IP.
DEVICE_NO_REGION          error    generation  Device has no Collector Region.
DEVICE_MISSING_CREDS      warning  snmp        SNMP device missing ≥1 credential.
DEVICE_NO_HOSTNAME        warning  inventory   Device hostname is blank/whitespace.
DEVICE_DUPLICATE_HOSTNAME warning  inventory   Two or more devices share a name.
BW_ORPHANED               warning  inventory   Bandwidth IP matches no device.
BW_DUPLICATE_INTERFACE    warning  inventory   Same IP/interface defined twice.
SUBNET_INVALID_CIDR       error    network     Subnet CIDR cannot be parsed.
SUBNET_DUPLICATE_CIDR     warning  network     Same CIDR defined on two subnets.

Rules deliberately deferred
----------------------------
TAG_UNKNOWN_VALUE  — most deployments allow free-text tag values; false positives
                     would be constant.  Add when real demand exists.
TAG_WRONG_SCOPE    — data-entry concern; better surfaced at form-submit time.
SUBNET_OVERLAP     — intentional CIDR hierarchies make this ambiguous.
"""
import ipaddress

from core.logic import is_valid_ip, has_full_creds, should_be_icmp_only

# Maximum entity names to list inline before switching to "… and N more".
_INLINE_LIMIT = 5

# Sort order for severity levels: lower number = appears first in output.
_SEVERITY_ORDER = {"error": 0, "warning": 1}


# ===========================================================================
# Public API
# ===========================================================================

def validate_inventory(devices: list, bandwidth: list,
                       subnets: list, tag_defs: list) -> list:
    """Validate the full inventory and return a sorted list of findings.

    Parameters mirror the return values of ``storage.list_*``.  The caller
    is responsible for loading data; this function never touches SQLite.

    Returns an empty list when the inventory has no detectable issues.
    """
    # Pre-compute the set of valid device IPs once so bandwidth checks that
    # correlate rows against devices do not repeat the O(n) loop.
    device_ips = {
        (d.get("IP") or "").strip()
        for d in devices
        if is_valid_ip((d.get("IP") or "").strip())
    }

    findings = []
    findings.extend(check_no_ip(devices))
    findings.extend(check_invalid_ip(devices))
    findings.extend(check_duplicate_ip(devices))
    findings.extend(check_no_region(devices))
    findings.extend(check_missing_snmp_credentials(devices))
    findings.extend(check_no_hostname(devices))
    findings.extend(check_duplicate_hostname(devices))
    findings.extend(check_orphaned_bandwidth(bandwidth, device_ips))
    findings.extend(check_duplicate_bandwidth_interface(bandwidth))
    findings.extend(check_invalid_subnets(subnets))
    findings.extend(check_duplicate_subnet_cidrs(subnets))

    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 99),
                                  f["message"]))
    return findings


# ===========================================================================
# Internal helpers
# ===========================================================================

def _truncated_list(items: list, limit: int = _INLINE_LIMIT) -> str:
    """Return a comma-joined string, abbreviated when len(items) > limit."""
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f" and {len(items) - limit} more"


def _finding(code: str, severity: str, category: str, message: str) -> dict:
    return {"code": code, "severity": severity,
            "category": category, "message": message}


# ===========================================================================
# Device checks
# ===========================================================================

def check_no_ip(devices: list) -> list:
    """DEVICE_NO_IP — device row has a blank or whitespace-only IP field."""
    affected = []
    for device in devices:
        if not (device.get("IP") or "").strip():
            name = (device.get("Device") or "").strip() or "(unnamed)"
            affected.append(name)
    if not affected:
        return []
    n = len(affected)
    noun = "device" if n == 1 else "devices"
    verb = "has" if n == 1 else "have"
    return [_finding(
        "DEVICE_NO_IP", "error", "generation",
        f"{n} {noun} {verb} no IP address set: {_truncated_list(affected)}.",
    )]


def check_invalid_ip(devices: list) -> list:
    """DEVICE_INVALID_IP — device IP is present but not a valid IP address."""
    affected = []
    for device in devices:
        raw_ip = (device.get("IP") or "").strip()
        if not raw_ip:
            continue  # blank IPs are caught by check_no_ip
        if not is_valid_ip(raw_ip):
            name = (device.get("Device") or "").strip() or "(unnamed)"
            affected.append(f"{name} ({raw_ip})")
    if not affected:
        return []
    n = len(affected)
    noun = "device" if n == 1 else "devices"
    verb = "has" if n == 1 else "have"
    return [_finding(
        "DEVICE_INVALID_IP", "error", "network",
        f"{n} {noun} {verb} an invalid IP address: {_truncated_list(affected)}.",
    )]


def check_duplicate_ip(devices: list) -> list:
    """DEVICE_DUPLICATE_IP — two or more devices share the same IP address."""
    seen = {}        # ip -> first device name
    duplicates = {}  # ip -> [first_name, second_name, ...]

    for device in devices:
        raw_ip = (device.get("IP") or "").strip()
        if not raw_ip or not is_valid_ip(raw_ip):
            continue
        name = (device.get("Device") or "").strip() or "(unnamed)"
        if raw_ip in seen:
            duplicates.setdefault(raw_ip, [seen[raw_ip]]).append(name)
        else:
            seen[raw_ip] = name

    if not duplicates:
        return []
    pairs = [f"{ip} ({', '.join(names)})" for ip, names in duplicates.items()]
    n = len(duplicates)
    noun = "IP address is" if n == 1 else "IP addresses are"
    return [_finding(
        "DEVICE_DUPLICATE_IP", "warning", "inventory",
        f"{n} {noun} assigned to multiple devices: {_truncated_list(pairs)}. "
        f"Only the first device encountered for each IP will appear in "
        f"generated output.",
    )]


def check_no_region(devices: list) -> list:
    """DEVICE_NO_REGION — device with a valid IP has no Collector Region."""
    affected = []
    for device in devices:
        raw_ip = (device.get("IP") or "").strip()
        if not raw_ip or not is_valid_ip(raw_ip):
            continue  # already flagged by check_no_ip / check_invalid_ip
        region = (device.get("Collector Region") or "").strip()
        if not region:
            name = (device.get("Device") or "").strip() or "(unnamed)"
            affected.append(f"{name} ({raw_ip})")
    if not affected:
        return []
    n = len(affected)
    noun = "device" if n == 1 else "devices"
    verb = "has" if n == 1 else "have"
    return [_finding(
        "DEVICE_NO_REGION", "error", "generation",
        f"{n} {noun} {verb} no Collector Region set and will be excluded from "
        f"all generated output files: {_truncated_list(affected)}.",
    )]


def check_missing_snmp_credentials(devices: list) -> list:
    """DEVICE_MISSING_CREDS — SNMP device is missing ≥1 SNMPv3 credential field.

    Devices without a valid IP or without a Collector Region are skipped: they
    are already excluded from generation, so their credentials are irrelevant.

    should_be_icmp_only() is called without resolved tags (conservative): a
    device that would become ICMP-only through subnet tag inheritance may
    appear here as a false positive, but only in deployments that use a Device
    Class tag inherited from subnets — a rare configuration.
    """
    affected = []
    for device in devices:
        raw_ip = (device.get("IP") or "").strip()
        if not raw_ip or not is_valid_ip(raw_ip):
            continue
        if not (device.get("Collector Region") or "").strip():
            continue  # excluded from generation; credentials irrelevant
        if not should_be_icmp_only(device) and not has_full_creds(device):
            name = (device.get("Device") or "").strip() or "(unnamed)"
            affected.append(f"{name} ({raw_ip})")
    if not affected:
        return []
    n = len(affected)
    noun = "device" if n == 1 else "devices"
    verb = "is" if n == 1 else "are"
    return [_finding(
        "DEVICE_MISSING_CREDS", "warning", "snmp",
        f"{n} {noun} {verb} missing one or more SNMPv3 credential fields "
        f"(snmpUser, authProtocol, authKey, privProtocol, privKey): "
        f"{_truncated_list(affected)}.",
    )]


def check_no_hostname(devices: list) -> list:
    """DEVICE_NO_HOSTNAME — device hostname is blank or whitespace-only."""
    affected = []
    for device in devices:
        if not (device.get("Device") or "").strip():
            # Use the IP as context when available so the operator can locate
            # the row without a name to search by.
            ip = (device.get("IP") or "").strip() or "(no IP)"
            affected.append(ip)
    if not affected:
        return []
    n = len(affected)
    noun = "device" if n == 1 else "devices"
    verb = "has" if n == 1 else "have"
    return [_finding(
        "DEVICE_NO_HOSTNAME", "warning", "inventory",
        f"{n} {noun} {verb} no hostname set: {_truncated_list(affected)}.",
    )]


def check_duplicate_hostname(devices: list) -> list:
    """DEVICE_DUPLICATE_HOSTNAME — two or more devices share the same hostname.

    Blank hostnames are skipped; they are handled by check_no_hostname.
    """
    seen = {}        # hostname -> first device IP (or "(no IP)")
    duplicates = {}  # hostname -> [ip_or_placeholder, ...]

    for device in devices:
        name = (device.get("Device") or "").strip()
        if not name:
            continue  # blank names caught by check_no_hostname
        ip = (device.get("IP") or "").strip() or "(no IP)"
        if name in seen:
            duplicates.setdefault(name, [seen[name]]).append(ip)
        else:
            seen[name] = ip

    if not duplicates:
        return []
    pairs = [f'"{hn}" ({", ".join(ips)})' for hn, ips in duplicates.items()]
    n = len(duplicates)
    noun = "hostname is" if n == 1 else "hostnames are"
    return [_finding(
        "DEVICE_DUPLICATE_HOSTNAME", "warning", "inventory",
        f"{n} {noun} used by multiple devices: {_truncated_list(pairs)}.",
    )]


# ===========================================================================
# Bandwidth checks
# ===========================================================================

def check_orphaned_bandwidth(bandwidth: list, device_ips: set) -> list:
    """BW_ORPHANED — bandwidth row references an IP with no matching device.

    ``device_ips`` is pre-computed by ``validate_inventory`` and contains
    only IPs that passed ``is_valid_ip``.  Rows with a blank IP are ignored.
    """
    orphaned = []
    seen = set()
    for row in bandwidth:
        ip = (row.get("IP") or "").strip()
        if not ip or ip in device_ips or ip in seen:
            continue
        seen.add(ip)
        orphaned.append(ip)
    if not orphaned:
        return []
    n = len(orphaned)
    noun = "IP" if n == 1 else "IPs"
    verb = "has" if n == 1 else "have"
    return [_finding(
        "BW_ORPHANED", "warning", "inventory",
        f"{n} bandwidth {noun} {verb} no matching device in the inventory: "
        f"{_truncated_list(orphaned)}.",
    )]


def check_duplicate_bandwidth_interface(bandwidth: list) -> list:
    """BW_DUPLICATE_INTERFACE — same IP/interface combination defined twice.

    Rows with a blank IP or a blank interface name are skipped: they already
    represent incomplete data and are not useful as a duplicate key.
    """
    counts = {}   # (ip, interface) -> occurrence count
    for row in bandwidth:
        ip = (row.get("IP") or "").strip()
        iface = (row.get("Interface") or "").strip()
        if not ip or not iface:
            continue
        key = (ip, iface)
        counts[key] = counts.get(key, 0) + 1

    duplicates = [f"{ip} / {iface}" for (ip, iface), n in counts.items() if n > 1]
    if not duplicates:
        return []
    n = len(duplicates)
    # "combination" stays singular in both noun forms for readability.
    verb = "is" if n == 1 else "are"
    return [_finding(
        "BW_DUPLICATE_INTERFACE", "warning", "inventory",
        f"{n} device/interface combination{'' if n == 1 else 's'} {verb} "
        f"defined more than once: {_truncated_list(duplicates)}.",
    )]


# ===========================================================================
# Subnet checks
# ===========================================================================

def check_invalid_subnets(subnets: list) -> list:
    """SUBNET_INVALID_CIDR — subnet CIDR cannot be parsed as a network address."""
    invalid = []
    for subnet in subnets:
        cidr = (subnet.get("CIDR") or "").strip()
        if not cidr:
            continue  # blank CIDR silently skipped by generation too
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            # Accept both 'Name' (validator fixtures / future) and 'Description'
            # (current storage schema used by the frontend and subnets.js).
            label = (subnet.get("Description") or subnet.get("Name") or "").strip() or cidr
            invalid.append(f"{label} ({cidr})" if label != cidr else cidr)
    if not invalid:
        return []
    n = len(invalid)
    noun = "subnet" if n == 1 else "subnets"
    verb = "has" if n == 1 else "have"
    return [_finding(
        "SUBNET_INVALID_CIDR", "error", "network",
        f"{n} {noun} {verb} an invalid CIDR that will be ignored during "
        f"YAML generation and IP matching: {_truncated_list(invalid)}.",
    )]


def check_duplicate_subnet_cidrs(subnets: list) -> list:
    """SUBNET_DUPLICATE_CIDR — the same CIDR is defined on two or more subnets.

    CIDRs are normalised with ``ip_network(strict=False)`` before comparison
    so that ``192.0.2.1/24`` and ``192.0.2.0/24`` are treated as the same
    network.  Subnets with unparseable CIDRs are skipped (handled by
    check_invalid_subnets).
    """
    seen = {}        # canonical_cidr -> first subnet Name
    duplicates = {}  # canonical_cidr -> [first_name, second_name, ...]

    for subnet in subnets:
        cidr = (subnet.get("CIDR") or "").strip()
        if not cidr:
            continue
        try:
            canonical = str(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue  # already caught by check_invalid_subnets
        # Accept both 'Description' (storage schema) and 'Name' (fixtures).
        name = (subnet.get("Description") or subnet.get("Name") or cidr).strip()
        if canonical in seen:
            duplicates.setdefault(canonical, [seen[canonical]]).append(name)
        else:
            seen[canonical] = name

    if not duplicates:
        return []
    pairs = [f"{cidr} ({', '.join(names)})" for cidr, names in duplicates.items()]
    n = len(duplicates)
    noun = "subnet CIDR is" if n == 1 else "subnet CIDRs are"
    return [_finding(
        "SUBNET_DUPLICATE_CIDR", "warning", "network",
        f"{n} {noun} defined more than once: {_truncated_list(pairs)}.",
    )]
