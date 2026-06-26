"""
HTTP request handler: JSON REST API + static file serving.

Single ThreadingHTTPServer process. One person runs this on an always-on
machine; everyone else opens a browser to http://<that machine>:<port>.

Request/response shapes (devices and bandwidth mirror each other):
  GET    /api/devices                -> {devices: [...]}
  POST   /api/devices                 body {device: {...}, _actor}      -> {device: {...with id...}}
  DELETE /api/devices/{id}?_actor=... -> {deleted: id}
  POST   /api/devices/import          body {devices: [...], mode, _actor} -> {imported: N, mode}

  GET    /api/bandwidth               -> {rows: [...]}
  POST   /api/bandwidth               body {row: {...}, _actor}        -> {row: {...with id...}}
  DELETE /api/bandwidth/{id}?_actor=... -> {deleted: id}
  POST   /api/bandwidth/import        body {rows: [...], mode, _actor} -> {imported: N, mode}

  GET    /api/subnets                 -> {subnets: [...]}
  POST   /api/subnets                 body {subnet: {...}, _actor}     -> {subnet: {...with id...}}
  DELETE /api/subnets/{id}?_actor=... -> {deleted: id}
  POST   /api/subnets/import          body {subnets: [...], mode, _actor} -> {imported: N, mode}

  GET    /api/lists                                  -> {lists: {...}}
  POST   /api/lists/{name}            body {items: [...], _actor}      -> {items: [...]}
  GET    /api/lists/{name}/usage?value=X              -> {count: N}

  GET    /api/tags                                    -> {tagDefs: [...]}
  POST   /api/tags                    body {tagDef: {...}, _actor}     -> {tagDef: {...with id...}}
  DELETE /api/tags/{id}?_actor=...                     -> {deleted: id} | 409 {error, dependents: N}
  GET    /api/tags/{id}/usage?value=X                  -> {count: N}   (value omitted = any non-empty)

  GET    /api/audit?limit=N           -> {entries: [...]}
  GET    /api/history?limit=N         -> {entries: [...]}
  GET    /api/history/{id}            -> {id, ts, actor, summary, files}
  POST   /api/generate                body {_actor}                    -> {files, groupStats, ...}
  GET    /api/meta                                    -> {deviceCount, bandwidthCount, subnetCount, lastSavedAt, lastSavedBy}
  GET    /api/export/devices.xlsx                     -> binary xlsx (template-compatible with import)
  GET    /api/export/bandwidth.xlsx                    -> binary xlsx

All write endpoints accept/return a dependency-checked-delete contract:
deleting something with active dependents returns HTTP 409 with
{error: "...", dependents: N} instead of failing silently or succeeding
destructively; the caller (frontend) is expected to surface this and
require an explicit force=true to proceed, EXCEPT for tag DEFINITIONS
and LIST ITEMS, where delete always succeeds but the response includes
a `warning` field with the dependent count so the frontend can confirm
before calling (frontend already does its own usage check + confirm
dialog before calling delete in the merge-tags-flow case). Devices/
bandwidth/subnets rows themselves have no cross-table dependents in this
schema, so their DELETE is unconditional.
"""
import json
import re
import ipaddress
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

import storage
import logic
import yamldump
import xlsxwriter

STATIC_DIR = None  # set by server.py before serving


class Handler(BaseHTTPRequestHandler):
    server_version = "ConfigForge/1.0"

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_binary(self, data: bytes, content_type: str, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw)

    def log_message(self, fmt, *args):
        pass  # quiet; rely on audit log instead

    # -------------------------------------------------------------------
    # GET
    # -------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)

        try:
            if path == "/api/devices":
                return self._send_json({"devices": storage.list_devices()})
            if path == "/api/bandwidth":
                return self._send_json({"rows": storage.list_bandwidth()})
            if path == "/api/subnets":
                return self._send_json({"subnets": storage.list_subnets()})
            if path == "/api/lists":
                return self._send_json({"lists": storage.get_lists()})
            if path == "/api/tags":
                return self._send_json({"tagDefs": storage.list_tag_defs()})

            m = re.match(r"^/api/lists/([^/]+)/usage$", path)
            if m:
                value = qs.get("value", [""])[0]
                count = storage.list_usage_count(m.group(1), value)
                return self._send_json({"count": count})

            m = re.match(r"^/api/tags/([^/]+)/usage$", path)
            if m:
                value = qs.get("value", [None])[0]
                if value is not None:
                    count = storage.tag_value_usage_count(m.group(1), value)
                else:
                    count = storage.tag_def_usage_count(m.group(1))
                return self._send_json({"count": count})

            if path == "/api/audit":
                limit = int(qs.get("limit", ["100"])[0])
                return self._send_json({"entries": storage.list_audit(limit)})

            if path == "/api/history":
                limit = int(qs.get("limit", ["50"])[0])
                return self._send_json({"entries": storage.list_history(limit)})

            m = re.match(r"^/api/history/([^/]+)$", path)
            if m:
                entry = storage.get_history_entry(m.group(1))
                if not entry:
                    return self._send_json({"error": "not found"}, 404)
                return self._send_json(entry)

            if path == "/api/meta":
                return self._send_json(storage.get_meta())

            if path == "/api/export/devices.xlsx":
                return self._export_devices_xlsx()
            if path == "/api/export/bandwidth.xlsx":
                return self._export_bandwidth_xlsx()
            if path == "/api/export/subnets.xlsx":
                return self._export_subnets_xlsx()

            return self._serve_static(path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send_json({"error": str(e), "type": type(e).__name__}, 500)

    def _serve_static(self, path):
        import os
        if path == "/":
            path = "/index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, path.lstrip("/")))
        if not full.startswith(os.path.normpath(STATIC_DIR)):
            return self._send_json({"error": "forbidden"}, 403)
        if not os.path.isfile(full):
            return self._send_json({"error": "not found"}, 404)
        with open(full, "rb") as f:
            body = f.read()
        ctype = "text/html"
        if path.endswith(".js"):
            ctype = "application/javascript"
        elif path.endswith(".css"):
            ctype = "text/css"
        elif path.endswith(".svg"):
            ctype = "image/svg+xml"
        elif path.endswith(".png"):
            ctype = "image/png"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # -------------------------------------------------------------------
    # POST
    # -------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        try:
            body = self._read_json()
        except Exception as e:
            return self._send_json({"error": f"invalid JSON body: {e}"}, 400)
        actor = body.get("_actor")

        try:
            if path == "/api/devices":
                return self._upsert_device(body, actor)
            if path == "/api/devices/import":
                return self._import_rows(body, actor, scope="devices")

            if path == "/api/bandwidth":
                return self._upsert_bandwidth(body, actor)
            if path == "/api/bandwidth/import":
                return self._import_rows(body, actor, scope="bandwidth")

            if path == "/api/subnets":
                return self._upsert_subnet(body, actor)
            if path == "/api/subnets/import":
                return self._import_rows(body, actor, scope="subnets")

            m = re.match(r"^/api/lists/([^/]+)$", path)
            if m:
                return self._set_list(m.group(1), body, actor)

            if path == "/api/tags":
                return self._upsert_tag(body, actor)

            if path == "/api/generate":
                return self._generate(actor)

            return self._send_json({"error": "not found"}, 404)
        except ValueError as e:
            return self._send_json({"error": str(e)}, 400)
        except Exception as e:
            import traceback
            traceback.print_exc()  # full traceback to the server console
            return self._send_json({"error": str(e), "type": type(e).__name__}, 500)

    def _upsert_device(self, body, actor):
        device = body.get("device")
        if not isinstance(device, dict):
            return self._send_json({"error": "'device' must be an object"}, 400)
        ip = (device.get("IP") or "").strip()
        if ip and not logic.is_valid_ip(ip):
            return self._send_json({"error": f"'{ip}' is not a valid IP address"}, 400)
        is_create = not device.get("id")
        saved = storage.upsert_device(device)
        storage.log_audit(actor, "create_device" if is_create else "update_device",
                           {"id": saved["id"], "ip": saved.get("IP")})
        return self._send_json({"device": saved})

    def _upsert_bandwidth(self, body, actor):
        row = body.get("row")
        if not isinstance(row, dict):
            return self._send_json({"error": "'row' must be an object"}, 400)
        ip = (row.get("IP") or "").strip()
        if ip and not logic.is_valid_ip(ip):
            return self._send_json({"error": f"'{ip}' is not a valid IP address"}, 400)
        is_create = not row.get("id")
        saved = storage.upsert_bandwidth(row)
        storage.log_audit(actor, "create_bandwidth" if is_create else "update_bandwidth",
                           {"id": saved["id"], "ip": saved.get("IP")})
        return self._send_json({"row": saved})

    def _upsert_subnet(self, body, actor):
        subnet = body.get("subnet")
        if not isinstance(subnet, dict):
            return self._send_json({"error": "'subnet' must be an object"}, 400)
        cidr = (subnet.get("CIDR") or "").strip()
        if cidr:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                return self._send_json({"error": f"'{cidr}' is not a valid CIDR"}, 400)
        is_create = not subnet.get("id")
        saved = storage.upsert_subnet(subnet)
        storage.log_audit(actor, "create_subnet" if is_create else "update_subnet",
                           {"id": saved["id"], "cidr": saved.get("CIDR")})
        return self._send_json({"subnet": saved})

    def _import_rows(self, body, actor, scope):
        key = {"devices": "devices", "bandwidth": "rows", "subnets": "subnets"}[scope]
        rows = body.get(key)
        if not isinstance(rows, list):
            return self._send_json({"error": f"'{key}' must be a list"}, 400)
        mode = body.get("mode", "merge")
        if mode not in ("merge", "replace"):
            return self._send_json({"error": "'mode' must be 'merge' or 'replace'"}, 400)

        replace_fn, merge_fn = {
            "devices": (storage.replace_all_devices, storage.merge_devices),
            "bandwidth": (storage.replace_all_bandwidth, storage.merge_bandwidth),
            "subnets": (storage.replace_all_subnets, storage.merge_subnets),
        }[scope]

        if mode == "replace":
            replace_fn(rows)
        else:
            merge_fn(rows)

        storage.log_audit(actor, f"import_{scope}", {"count": len(rows), "mode": mode})
        return self._send_json({"imported": len(rows), "mode": mode})

    def _set_list(self, list_name, body, actor):
        if list_name not in storage.FIXED_LISTS:
            return self._send_json({"error": f"unknown list '{list_name}'"}, 404)
        items = body.get("items")
        if not isinstance(items, list):
            return self._send_json({"error": "'items' must be a list"}, 400)
        storage.set_list(list_name, items)
        storage.log_audit(body.get("_actor"), "update_list", {"list": list_name, "items": items})
        return self._send_json({"items": items})

    def _upsert_tag(self, body, actor):
        tag_def = body.get("tagDef")
        if not isinstance(tag_def, dict):
            return self._send_json({"error": "'tagDef' must be an object"}, 400)
        if not tag_def.get("name", "").strip():
            return self._send_json({"error": "tag name is required"}, 400)
        invalid_scopes = [s for s in tag_def.get("scopes", []) if s not in storage.TAG_SCOPES]
        if invalid_scopes:
            return self._send_json({"error": f"invalid scope(s): {invalid_scopes}"}, 400)
        is_create = not tag_def.get("id")
        saved = storage.upsert_tag_def(tag_def)
        storage.log_audit(actor, "create_tag" if is_create else "update_tag",
                           {"id": saved["id"], "name": saved.get("name")})
        return self._send_json({"tagDef": saved})

    def _generate(self, actor):
        devices = storage.list_devices()
        bandwidth = storage.list_bandwidth()
        subnets = storage.list_subnets()
        tag_defs = storage.list_tag_defs()

        result = logic.convert_to_collector_configs(devices, bandwidth, subnets, tag_defs)

        rendered_files = {name: yamldump.dump(config) for name, config in result["files"].items()}
        result["files"] = rendered_files

        storage.save_history(actor, result["summary"], rendered_files)
        storage.log_audit(actor, "generate", {"summary": result["summary"]})
        return self._send_json(result)

    def _export_devices_xlsx(self):
        data = build_devices_xlsx(storage.list_devices(), storage.list_tag_defs())
        self._send_binary(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "devices_export.xlsx")

    def _export_bandwidth_xlsx(self):
        data = build_bandwidth_xlsx(storage.list_bandwidth(), storage.list_tag_defs())
        self._send_binary(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "bandwidth_export.xlsx")

    def _export_subnets_xlsx(self):
        data = build_subnets_xlsx(storage.list_subnets(), storage.list_tag_defs())
        self._send_binary(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "subnets_export.xlsx")

    # -------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)
        actor = qs.get("_actor", [None])[0]

        try:
            m = re.match(r"^/api/devices/([^/]+)$", path)
            if m:
                storage.delete_device(m.group(1))
                storage.log_audit(actor, "delete_device", {"id": m.group(1)})
                return self._send_json({"deleted": m.group(1)})

            m = re.match(r"^/api/bandwidth/([^/]+)$", path)
            if m:
                storage.delete_bandwidth(m.group(1))
                storage.log_audit(actor, "delete_bandwidth", {"id": m.group(1)})
                return self._send_json({"deleted": m.group(1)})

            m = re.match(r"^/api/subnets/([^/]+)$", path)
            if m:
                storage.delete_subnet(m.group(1))
                storage.log_audit(actor, "delete_subnet", {"id": m.group(1)})
                return self._send_json({"deleted": m.group(1)})

            m = re.match(r"^/api/tags/([^/]+)$", path)
            if m:
                tag_id = m.group(1)
                force = qs.get("force", ["false"])[0] == "true"
                dependents = storage.tag_def_usage_count(tag_id)
                if dependents > 0 and not force:
                    return self._send_json(
                        {"error": "tag is in use", "dependents": dependents}, 409
                    )
                storage.delete_tag_def(tag_id)
                storage.log_audit(actor, "delete_tag", {"id": tag_id, "dependents_forced": dependents if force else 0})
                return self._send_json({"deleted": tag_id})

            return self._send_json({"error": "not found"}, 404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send_json({"error": str(e), "type": type(e).__name__}, 500)


# ---------------------------------------------------------------------------
# Excel export (template-compatible with the import flow)
# ---------------------------------------------------------------------------
def build_devices_xlsx(devices: list, tag_defs: list) -> bytes:
    # Only IP, Device, Collector Region (mandatory, hardcoded), Config
    # Type, Remarks, and credentials remain bare device fields. Every
    # other categorization (Device Class, Region, Center, etc.) is now
    # tag-driven and only appears as a column if/when someone actually
    # creates that tag through the Tags module -- see migrations.py
    # migrate_3 for how pre-existing values get promoted into tags.
    fixed_cols = ["IP", "Device", "Collector Region", "Config Type", "Remarks",
                  "snmpUser", "authProtocol", "authKey", "privProtocol", "privKey"]
    device_tag_defs = [td for td in tag_defs if "devices" in td.get("scopes", [])]
    tag_cols = [td["name"] for td in device_tag_defs]
    headers = fixed_cols + tag_cols

    rows = []
    for d in devices:
        row = [d.get(c, "") for c in fixed_cols]
        for td in device_tag_defs:
            row.append((d.get("tags") or {}).get(td["id"], ""))
        rows.append(row)

    return xlsxwriter.write_xlsx("devices", headers, rows)


def build_bandwidth_xlsx(rows_in: list, tag_defs: list) -> bytes:
    fixed_cols = ["IP", "Interface", "Allocated BW", "Region", "Center", "Link Type",
                  "Interface_description"]
    bw_tag_defs = [td for td in tag_defs if "bandwidth" in td.get("scopes", [])]
    tag_cols = [td["name"] for td in bw_tag_defs]
    headers = fixed_cols + tag_cols

    rows = []
    for r in rows_in:
        row = [r.get(c, "") for c in fixed_cols]
        for td in bw_tag_defs:
            row.append((r.get("tags") or {}).get(td["id"], ""))
        rows.append(row)

    return xlsxwriter.write_xlsx("bandwidth_capping", headers, rows)


def build_subnets_xlsx(subnets_in: list, tag_defs: list) -> bytes:
    fixed_cols = ["CIDR", "Description"]
    subnet_tag_defs = [td for td in tag_defs if "subnets" in td.get("scopes", [])]
    tag_cols = [td["name"] for td in subnet_tag_defs]
    headers = fixed_cols + tag_cols

    rows = []
    for s in subnets_in:
        row = [s.get(c, "") for c in fixed_cols]
        for td in subnet_tag_defs:
            row.append((s.get("tags") or {}).get(td["id"], ""))
        rows.append(row)

    return xlsxwriter.write_xlsx("subnets", headers, rows)
