"""
Core conversion logic: devices + bandwidth caps + subnets + tag defs
-> per-collector-region YAML-ready config dicts.

Kept as plain functions operating on plain dicts/lists (no SQLite, no
encryption) so it's easy to unit test in isolation and reason about.
"""
import re
import ipaddress

ARISTA_ETH_RE = re.compile(r"^Eth\s*(\d+(?:\.\d+)?)$", re.IGNORECASE)


def normalize_group_key(region: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", region.strip().lower())
    return key.strip("_") or "unknown"


def is_valid_ip(value: str) -> bool:
    if not value:
        return False
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def should_be_icmp_only(device: dict, resolved_tags: dict = None) -> bool:
    """Device Class is no longer a guaranteed fixed field -- it only
    exists once someone creates a "Device Class" tag through the Tags
    module. So this checks the *resolved* tag value by name (falling
    back to nothing if that tag doesn't exist in this deployment), plus
    the still-hardcoded Config Type field, which remains a bare device
    field rather than a tag."""
    resolved_tags = resolved_tags or {}
    cls = (resolved_tags.get("Device Class") or "").strip().lower()
    cfg = (device.get("Config Type") or "").strip().lower()
    return cls == "storage" or cfg in ("icmp", "snmp trap")


def has_full_creds(device: dict) -> bool:
    return all([
        device.get("snmpUser"), device.get("authProtocol"), device.get("authKey"),
        device.get("privProtocol"), device.get("privKey"),
    ])


def _parse_bw_to_bps(value: str):
    """Parse strings like '1 Gbps', '500 Mbps', '100kbps' into bits/sec."""
    if not value:
        return None
    m = re.match(r"^\s*([\d.]+)\s*([a-zA-Z]+)\s*$", value)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2).lower()
    multipliers = {
        "bps": 1, "kbps": 1_000, "mbps": 1_000_000, "gbps": 1_000_000_000,
        "kb": 1_000, "mb": 1_000_000, "gb": 1_000_000_000,
    }
    mult = multipliers.get(unit)
    if mult is None:
        return None
    return int(num * mult)


def _interface_match(interface_name: str) -> dict:
    """Arista 'Eth N' (optionally with a decimal sub-id, e.g. 'Eth 54.200')
    matches by ifIndex; everything else matches by interface name string."""
    m = ARISTA_ETH_RE.match((interface_name or "").strip())
    if m:
        return {"match_field": "index", "match_value": m.group(1)}
    return {"match_field": "name", "match_value": interface_name}


def resolve_tags_for_record(record: dict, tag_defs: list, subnet_match=None) -> dict:
    """Returns {tagName: value} for all non-empty tags on this record,
    after filling in any empty tag from a matching subnet's value (only
    for tags whose scope includes 'subnets' AND the record's own scope --
    i.e. subnet inheritance only fills gaps, never overrides an explicit
    value the record already has)."""
    own_tags = record.get("tags") or {}
    resolved = {}
    for td in tag_defs:
        tag_id = td["id"]
        value = own_tags.get(tag_id)
        if not value and subnet_match and "subnets" in td.get("scopes", []):
            value = (subnet_match.get("tags") or {}).get(tag_id)
        if value:
            resolved[td["name"]] = value
    return resolved


def convert_to_collector_configs(devices: list, bandwidth_rows: list, subnets: list = None,
                                   tag_defs: list = None) -> dict:
    subnets = subnets or []
    tag_defs = tag_defs or []

    # Index bandwidth rows by IP for O(1) lookup per device.
    bw_by_ip = {}
    for b in bandwidth_rows:
        ip = (b.get("IP") or "").strip()
        if ip:
            bw_by_ip.setdefault(ip, []).append(b)

    device_ips = set()
    groups = {}          # group_key -> {"region": display name, "devices": [...]}
    group_stats = {}
    skipped_devices = 0
    invalid_ip_devices = []
    missing_region_devices = []
    missing_creds_devices = []
    used_bw_ips = set()

    for device in devices:
        ip = (device.get("IP") or "").strip()
        if not ip:
            skipped_devices += 1
            continue
        if not is_valid_ip(ip):
            invalid_ip_devices.append({"ip": ip, "device": device.get("Device", "")})
            continue
        device_ips.add(ip)

        region = (device.get("Collector Region") or "").strip()
        if not region:
            missing_region_devices.append({"ip": ip, "device": device.get("Device", "")})
            continue

        group_key = normalize_group_key(region)
        groups.setdefault(group_key, {"region": region, "devices": []})
        gs = group_stats.setdefault(group_key, {
            "snmp_count": 0, "icmp_only_count": 0, "missing_creds_count": 0,
            "bw_devices": 0, "bw_interfaces": 0,
        })

        subnet_match = None
        for s in subnets:
            cidr = (s.get("CIDR") or "").strip()
            if not cidr:
                continue
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                if ipaddress.ip_address(ip) in net:
                    if subnet_match is None or net.prefixlen > ipaddress.ip_network(subnet_match["CIDR"], strict=False).prefixlen:
                        subnet_match = s
            except ValueError:
                continue

        resolved_tags = resolve_tags_for_record(device, tag_defs, subnet_match)
        forced_icmp = should_be_icmp_only(device, resolved_tags)
        full_creds = has_full_creds(device)

        entry = {
            "ip": ip,
            "device": device.get("Device", ""),
        }
        if subnet_match:
            entry["subnet"] = subnet_match.get("CIDR", "")
        if resolved_tags:
            entry["tags"] = resolved_tags

        if forced_icmp:
            entry["network_address"] = f"{ip}/32"
            entry["mode"] = "icmp"
            gs["icmp_only_count"] += 1
        else:
            entry["snmpUser"] = device.get("snmpUser", "")
            entry["authProtocol"] = device.get("authProtocol", "")
            entry["authKey"] = device.get("authKey", "")
            entry["privProtocol"] = device.get("privProtocol", "")
            entry["privKey"] = device.get("privKey", "")
            gs["snmp_count"] += 1
            if not full_creds:
                gs["missing_creds_count"] += 1
                missing_creds_devices.append({"ip": ip, "device": device.get("Device", ""), "region": region})

        bw_rows_for_ip = bw_by_ip.get(ip, [])
        if bw_rows_for_ip:
            used_bw_ips.add(ip)
            gs["bw_devices"] += 1
            interfaces = []
            for b in bw_rows_for_ip:
                gs["bw_interfaces"] += 1
                iface_match = _interface_match(b.get("Interface", ""))
                bps = _parse_bw_to_bps(b.get("Allocated BW", ""))
                interfaces.append({
                    **iface_match,
                    "allocated_bw_bps": bps,
                    "interface_description": b.get("Interface_description", ""),
                })
            entry["interface_configs"] = interfaces

        groups[group_key]["devices"].append(entry)

    orphaned_bw_ips = sorted({ip for ip in bw_by_ip if ip not in device_ips})

    files = {}
    for group_key, group_data in groups.items():
        config = {
            "init_config": {},
            "instances": group_data["devices"],
        }
        files[f"{group_key}.yaml"] = config

    snmp_total = sum(g["snmp_count"] for g in group_stats.values())
    icmp_total = sum(g["icmp_only_count"] for g in group_stats.values())

    return {
        "files": files,  # group_key.yaml -> config dict (caller runs yamldump)
        "groupStats": group_stats,
        "skippedDevices": skipped_devices,
        "invalidIpDevices": invalid_ip_devices,
        "missingRegionDevices": missing_region_devices,
        "missingCredsDevices": missing_creds_devices,
        "orphanedBwIps": orphaned_bw_ips,
        "totalBwInterfaces": sum(g["bw_interfaces"] for g in group_stats.values()),
        "snmpTotal": snmp_total,
        "icmpTotal": icmp_total,
        "summary": f"{len(groups)} region(s), {snmp_total} SNMP / {icmp_total} ICMP devices",
    }
