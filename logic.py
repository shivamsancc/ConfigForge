"""
Core SNMP/ICMP collector-config conversion logic.

This is a faithful Python port of logic.js from the browser-based v1/v2
tool. Behavior is intentionally identical:

  - A device with no Collector Region is EXCLUDED from all output (and
    reported in `missing_region_devices`) -- region is mandatory for
    inclusion in any generated YAML.
  - A device with Config Type forcing ICMP (or Device Class == Storage)
    is always emitted as ping-only, regardless of whether it has
    credentials.
  - A device that should be SNMP but is missing any of its 5 per-device
    credential fields (snmpUser/authProtocol/authKey/privProtocol/privKey)
    is still emitted (so the file generates), but flagged in
    `missing_creds_devices` so the UI can surface a warning.
  - Arista-style "Eth N" / "Eth N.M" interfaces match by index; everything
    else matches by name. Dotted sub-indexes are kept as strings so
    trailing zeros aren't dropped by numeric coercion (e.g. "54.200").
"""

import re

COUNTRY_CODES = {
    "South Africa": "ZA", "India": "IN", "Philippines": "PH",
    "United States": "US", "US": "US", "United Kingdom": "GB",
    "Europe": "EU", "Romania": "RO", "Bulgaria": "BG",
    "Czech Republic": "CZ", "Singapore": "SG", "Germany": "DE",
}

FORCE_ICMP_CONFIG_TYPES = {"ICMP", "SNMP TRAP"}

_ETH_RE = re.compile(r"^Eth\s*(\d+(?:\.\d+)?)$", re.IGNORECASE)


def safe_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v != v:  # NaN
        return ""
    s = str(v).strip()
    if s.lower() == "nan":
        return ""
    return s


def sanitize_tag_value(value) -> str:
    s = safe_str(value)
    if not s:
        return "unknown"
    return s.replace(" ", "_")


def sanitize_filename(name) -> str:
    return str(name).lower().replace(" ", "_").replace("-", "_")


def parse_bandwidth(bw_string) -> int:
    s = safe_str(bw_string)
    m = re.search(r"([\d.]+)\s*(Gbps|Mbps|Kbps|bps)", s, re.IGNORECASE)
    if not m:
        return 0
    value = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "gbps":
        return round(value * 1_000_000_000)
    if unit == "mbps":
        return round(value * 1_000_000)
    if unit == "kbps":
        return round(value * 1_000)
    return round(value)


def get_interface_match(interface_raw, log=None):
    """
    Eth N / Eth N.M (Arista index-style interfaces) -> index match;
    everything else -> name match. Dotted sub-indexes kept as strings so
    trailing zeros aren't dropped by numeric coercion.
    """
    interface_str = safe_str(interface_raw)
    m = _ETH_RE.match(interface_str)
    if m:
        raw = m.group(1)
        match_value = raw if "." in raw else int(raw)
        if log:
            log(f"'{interface_str}' -> auto-converted to index: {match_value}")
        return "index", match_value
    return "name", interface_str


def should_be_icmp_only(device_class, config_type) -> bool:
    if safe_str(device_class).lower() == "storage":
        return True
    ct = safe_str(config_type).upper()
    if ct in FORCE_ICMP_CONFIG_TYPES:
        return True
    return False


def has_complete_credentials(device: dict) -> bool:
    """
    A device's own SNMPv3 fields are considered "complete" only if every
    one of the five fields is non-empty.
    """
    return bool(
        safe_str(device.get("snmpUser"))
        and safe_str(device.get("authProtocol"))
        and safe_str(device.get("authKey"))
        and safe_str(device.get("privProtocol"))
        and safe_str(device.get("privKey"))
    )


def load_bandwidth_caps(bw_rows, log=None):
    bandwidth_dict = {}
    total = 0
    for row in bw_rows:
        ip = safe_str(row.get("IP"))
        interface_raw = safe_str(row.get("Interface"))
        if not ip or not interface_raw:
            continue

        allocated_bw = safe_str(row.get("Allocated BW"))
        region = safe_str(row.get("Region"))
        center = safe_str(row.get("Center"))
        link_type = safe_str(row.get("Link Type"))
        iface_desc = safe_str(row.get("Interface_description"))

        speed_bps = parse_bandwidth(allocated_bw)
        match_field, match_value = get_interface_match(interface_raw, log)

        tags = []
        if region:
            tags.append(f"region:{sanitize_tag_value(region)}")
        if center:
            tags.append(f"center:{sanitize_tag_value(center)}")
        if link_type:
            tags.append(f"link_type:{sanitize_tag_value(link_type)}")
        if iface_desc:
            tags.append(f"interface_description:{iface_desc}")
        custom_tags = row.get("customTags")
        if isinstance(custom_tags, list):
            for t in custom_tags:
                ts = safe_str(t)
                if ts:
                    tags.append(ts)

        iface_config = {
            "match_field": match_field,
            "match_value": match_value,
            "in_speed": speed_bps,
            "out_speed": speed_bps,
            "tags": tags,
        }

        bandwidth_dict.setdefault(ip, []).append(iface_config)
        total += 1

    return bandwidth_dict, total


def convert_to_collector_configs(device_rows, bw_rows, init_config=None, log=None):
    """
    Main conversion: device rows (each with its OWN credential fields) +
    bandwidth rows -> per-collector-region YAML-ready objects.

    Returns a dict with keys: groups, skipped_devices,
    missing_region_devices, missing_creds_devices, orphaned_bw_ips,
    total_bw_interfaces -- same shape as the JS convertToCollectorConfigs.
    """
    if init_config is None:
        init_config = {
            "loader": "core",
            "use_device_id_as_hostname": True,
            "min_collection_interval": 100,
            "oid_batch_size": 5,
            "timeout": 5,
            "ping": {"enabled": True, "count": 4, "interval": 250, "timeout": 3000},
        }
    if log is None:
        log = lambda msg: None

    bandwidth_dict, total_bw_interfaces = load_bandwidth_caps(bw_rows, log)
    used_bw_ips = set()

    grouped_devices = {}
    stats_tracker = {}
    skipped_devices = 0
    missing_region_devices = []
    missing_creds_devices = []

    for row in device_rows:
        ip = safe_str(row.get("IP")) or safe_str(row.get("Device IP"))
        if not ip:
            skipped_devices += 1
            continue

        collector_region = safe_str(row.get("Collector Region"))
        if not collector_region:
            missing_region_devices.append({"ip": ip, "device": safe_str(row.get("Device"))})
            continue

        operating_region = safe_str(row.get("Operating Region"))
        config_type = safe_str(row.get("Config Type")) or "SNMP"
        geolocation = safe_str(row.get("geolocation"))
        region = safe_str(row.get("Region"))
        center = safe_str(row.get("Center"))
        device_class = safe_str(row.get("Device Class"))
        device_category = safe_str(row.get("Device Category"))
        device_type = safe_str(row.get("Device Type"))
        device_name = safe_str(row.get("Device"))

        country_code = COUNTRY_CODES.get(operating_region) or COUNTRY_CODES.get(region) or "XX"
        group_name = sanitize_filename(collector_region)

        if group_name not in stats_tracker:
            stats_tracker[group_name] = {
                "snmp_count": 0, "icmp_only_count": 0, "missing_creds_count": 0,
                "bw_devices": 0, "bw_interfaces": 0,
            }

        tags = []
        if collector_region:
            tags.append(f"collector_region:{sanitize_tag_value(collector_region)}")
        if operating_region:
            tags.append(f"operating_region:{sanitize_tag_value(operating_region)}")
        if config_type:
            tags.append(f"config_type:{sanitize_tag_value(config_type)}")
        if geolocation:
            tags.append(f"geolocation:{sanitize_tag_value(geolocation)}")
        if region:
            tags.append(f"region:{sanitize_tag_value(region)}")
        if center:
            tags.append(f"center:{sanitize_tag_value(center)}")
        if device_class:
            tags.append(f"device_class:{sanitize_tag_value(device_class)}")
        if device_category:
            tags.append(f"device_category:{sanitize_tag_value(device_category)}")
        if device_type:
            tags.append(f"device_type:{sanitize_tag_value(device_type)}")
        if device_name:
            tags.append(f"device_name:{sanitize_tag_value(device_name)}")
        custom_tags = row.get("customTags")
        if isinstance(custom_tags, list):
            for t in custom_tags:
                ts = safe_str(t)
                if ts:
                    tags.append(ts)
        tags.append(f"ip_address:{ip}")
        tags.append(f"country_code:{country_code}")

        if should_be_icmp_only(device_class, config_type):
            device_config = {"network_address": f"{ip}/32", "tags": tags}
            stats_tracker[group_name]["icmp_only_count"] += 1
        else:
            creds_ok = has_complete_credentials(row)
            if not creds_ok:
                missing_creds_devices.append({"ip": ip, "device": device_name, "region": collector_region})
                stats_tracker[group_name]["missing_creds_count"] += 1
            device_config = {
                "ip_address": ip,
                "snmp_version": 3,
                "user": safe_str(row.get("snmpUser")),
                "authProtocol": safe_str(row.get("authProtocol")) or "SHA",
                "authKey": safe_str(row.get("authKey")),
                "privProtocol": safe_str(row.get("privProtocol")) or "AES",
                "privKey": safe_str(row.get("privKey")),
                "tags": tags,
            }
            if ip in bandwidth_dict:
                device_config["interface_configs"] = bandwidth_dict[ip]
                used_bw_ips.add(ip)
                stats_tracker[group_name]["bw_devices"] += 1
                stats_tracker[group_name]["bw_interfaces"] += len(bandwidth_dict[ip])
            stats_tracker[group_name]["snmp_count"] += 1

        grouped_devices.setdefault(group_name, []).append(device_config)

    orphaned_bw_ips = [ip for ip in bandwidth_dict if ip not in used_bw_ips]

    groups = {}
    for group_name, devices in grouped_devices.items():
        groups[group_name] = {
            "config": {"init_config": init_config, "instances": devices},
            "stats": stats_tracker[group_name],
            "device_count": len(devices),
        }

    return {
        "groups": groups,
        "skipped_devices": skipped_devices,
        "missing_region_devices": missing_region_devices,
        "missing_creds_devices": missing_creds_devices,
        "orphaned_bw_ips": orphaned_bw_ips,
        "total_bw_interfaces": total_bw_interfaces,
    }
