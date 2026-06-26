"""
HTTP request handler: JSON REST API + static file serving.

Single ThreadingHTTPServer process. One person runs this on an always-on
machine; everyone else just opens a browser to http://<that machine>:<port>.
"""

import json
import mimetypes
import os
import re
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import logic
import storage
import yamldump

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


class Handler(BaseHTTPRequestHandler):
    server_version = "SNMPYAMLGenerator/1.0"

    # Quiet the default request logging format a bit
    def log_message(self, fmt, *args):
        try:
            print("%s - %s" % (self.address_string(), fmt % args))
        except Exception:
            pass

    # ---- helpers ----------------------------------------------------

    def _send_json(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str):
        self._send_json(status, {"error": message})

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON body: {e}")

    def _actor(self, body=None):
        """Editor-name attribution, same model as the old prompt()-once-per-session."""
        if body and isinstance(body, dict) and body.get("_actor"):
            return str(body["_actor"])[:120]
        return self.headers.get("X-Editor-Name", "unknown")

    # ---- static file serving ----------------------------------------

    def _serve_static(self, path: str):
        if path == "/" or path == "":
            path = "/index.html"
        # Prevent path traversal outside STATIC_DIR
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR):
            self.send_error(403, "Forbidden")
            return
        if not os.path.isfile(full):
            self.send_error(404, "Not found")
            return
        ctype, _ = mimetypes.guess_type(full)
        if not ctype:
            ctype = "application/octet-stream"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- routing ------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == "/api/devices":
                return self._send_json(200, {"devices": storage.list_devices()})
            if path == "/api/bandwidth":
                return self._send_json(200, {"rows": storage.list_bandwidth_caps()})
            if path == "/api/lists":
                return self._send_json(200, {"lists": storage.get_all_lists()})
            m = re.match(r"^/api/lists/([^/]+)/usage$", path)
            if m:
                list_name = m.group(1)
                value = (qs.get("value") or [""])[0]
                count = storage.count_list_value_usage(list_name, value)
                return self._send_json(200, {"listName": list_name, "value": value, "count": count})
            if path == "/api/audit":
                limit = int((qs.get("limit") or [500])[0])
                return self._send_json(200, {"entries": storage.list_audit_log(limit)})
            if path == "/api/history":
                limit = int((qs.get("limit") or [100])[0])
                return self._send_json(200, {"entries": storage.list_yaml_history(limit)})
            m = re.match(r"^/api/history/(\d+)$", path)
            if m:
                entry = storage.get_yaml_history_entry(int(m.group(1)))
                if entry is None:
                    return self._send_error_json(404, "history entry not found")
                return self._send_json(200, entry)
            if path == "/api/meta":
                devices = storage.list_devices()
                bw = storage.list_bandwidth_caps()
                last_saved_at = storage.get_meta("last_saved_at")
                last_saved_by = storage.get_meta("last_saved_by")
                return self._send_json(200, {
                    "deviceCount": len(devices),
                    "bandwidthCount": len(bw),
                    "lastSavedAt": last_saved_at,
                    "lastSavedBy": last_saved_by,
                })
            return self._serve_static(path)
        except Exception as e:
            self._send_error_json(500, str(e))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_json_body()
        except ValueError as e:
            return self._send_error_json(400, str(e))

        try:
            if path == "/api/devices":
                return self._handle_upsert_device(body)
            if path == "/api/devices/import":
                return self._handle_devices_import(body)
            if path == "/api/bandwidth":
                return self._handle_upsert_bandwidth(body)
            if path == "/api/bandwidth/import":
                return self._handle_bandwidth_import(body)
            m = re.match(r"^/api/lists/([^/]+)$", path)
            if m:
                return self._handle_set_list(m.group(1), body)
            if path == "/api/generate":
                return self._handle_generate(body)
            return self._send_error_json(404, "not found")
        except ValueError as e:
            return self._send_error_json(400, str(e))
        except Exception as e:
            return self._send_error_json(500, str(e))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            m = re.match(r"^/api/devices/([^/]+)$", path)
            if m:
                device_id = m.group(1)
                actor = self.headers.get("X-Editor-Name", "unknown")
                storage.delete_device(device_id)
                storage.log_action(actor, "device.delete", {"id": device_id})
                return self._send_json(200, {"deleted": device_id})
            m = re.match(r"^/api/bandwidth/([^/]+)$", path)
            if m:
                row_id = m.group(1)
                actor = self.headers.get("X-Editor-Name", "unknown")
                storage.delete_bandwidth_cap(row_id)
                storage.log_action(actor, "bandwidth.delete", {"id": row_id})
                return self._send_json(200, {"deleted": row_id})
            return self._send_error_json(404, "not found")
        except Exception as e:
            return self._send_error_json(500, str(e))

    # ---- handlers -----------------------------------------------------

    def _handle_upsert_device(self, body):
        device = body.get("device")
        if not device or not isinstance(device, dict):
            raise ValueError("missing 'device' object in request body")
        is_new = not device.get("id")
        if is_new:
            device["id"] = _new_id()
        storage.upsert_device(device)

        for list_name, field in (
            ("collectorRegions", "Collector Region"),
            ("deviceClasses", "Device Class"),
            ("deviceCategories", "Device Category"),
            ("deviceTypes", "Device Type"),
        ):
            storage.add_to_list_if_missing(list_name, device.get(field, ""))

        actor = self._actor(body)
        storage.log_action(actor, "device.create" if is_new else "device.update",
                            {"id": device["id"], "ip": device.get("IP", "")})
        return self._send_json(200, {"device": device})

    def _handle_devices_import(self, body):
        devices = body.get("devices")
        mode = body.get("mode", "merge")
        if not isinstance(devices, list):
            raise ValueError("'devices' must be a list")
        for d in devices:
            if not d.get("id"):
                d["id"] = _new_id()

        if mode == "replace":
            storage.replace_all_devices(devices)
        else:
            storage.merge_devices(devices)

        for d in devices:
            for list_name, field in (
                ("collectorRegions", "Collector Region"),
                ("deviceClasses", "Device Class"),
                ("deviceCategories", "Device Category"),
                ("deviceTypes", "Device Type"),
            ):
                storage.add_to_list_if_missing(list_name, d.get(field, ""))

        actor = self._actor(body)
        storage.log_action(actor, "devices.import", {"count": len(devices), "mode": mode})
        return self._send_json(200, {"imported": len(devices), "mode": mode})

    def _handle_upsert_bandwidth(self, body):
        row = body.get("row")
        if not row or not isinstance(row, dict):
            raise ValueError("missing 'row' object in request body")
        is_new = not row.get("id")
        if is_new:
            row["id"] = _new_id()
        storage.upsert_bandwidth_cap(row)
        actor = self._actor(body)
        storage.log_action(actor, "bandwidth.create" if is_new else "bandwidth.update",
                            {"id": row["id"], "ip": row.get("IP", "")})
        return self._send_json(200, {"row": row})

    def _handle_bandwidth_import(self, body):
        rows = body.get("rows")
        mode = body.get("mode", "merge")
        if not isinstance(rows, list):
            raise ValueError("'rows' must be a list")
        for r in rows:
            if not r.get("id"):
                r["id"] = _new_id()

        if mode == "replace":
            storage.replace_all_bandwidth_caps(rows)
        else:
            storage.merge_bandwidth_caps(rows)

        actor = self._actor(body)
        storage.log_action(actor, "bandwidth.import", {"count": len(rows), "mode": mode})
        return self._send_json(200, {"imported": len(rows), "mode": mode})

    def _handle_set_list(self, list_name, body):
        items = body.get("items")
        if not isinstance(items, list):
            raise ValueError("'items' must be a list")
        storage.set_list(list_name, items)
        actor = self._actor(body)
        storage.log_action(actor, "list.update", {"listName": list_name, "count": len(items)})
        return self._send_json(200, {"listName": list_name, "items": items})

    def _handle_generate(self, body):
        devices = storage.list_devices()
        bw_rows = storage.list_bandwidth_caps()

        log_lines = []
        result = logic.convert_to_collector_configs(
            devices, bw_rows, log=lambda msg: log_lines.append(msg)
        )

        files = {}
        for group_name, group_data in result["groups"].items():
            filename = f"{group_name}.yaml"
            files[filename] = yamldump.dump(group_data["config"])

        snmp_total = sum(g["stats"]["snmp_count"] for g in result["groups"].values())
        icmp_total = sum(g["stats"]["icmp_only_count"] for g in result["groups"].values())

        actor = self._actor(body)
        summary = f"{len(files)} region(s), {snmp_total} SNMP / {icmp_total} ICMP devices"
        storage.save_yaml_history(actor, summary, files)
        storage.log_action(actor, "generate", {
            "groups": list(result["groups"].keys()),
            "snmpCount": snmp_total,
            "icmpCount": icmp_total,
            "missingCredsCount": len(result["missing_creds_devices"]),
            "missingRegionCount": len(result["missing_region_devices"]),
        })

        return self._send_json(200, {
            "files": files,
            "groupStats": {name: g["stats"] for name, g in result["groups"].items()},
            "skippedDevices": result["skipped_devices"],
            "missingRegionDevices": result["missing_region_devices"],
            "missingCredsDevices": result["missing_creds_devices"],
            "orphanedBwIps": result["orphaned_bw_ips"],
            "totalBwInterfaces": result["total_bw_interfaces"],
            "snmpTotal": snmp_total,
            "icmpTotal": icmp_total,
            "summary": summary,
        })
