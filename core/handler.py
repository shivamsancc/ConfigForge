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
import os
import re
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from core.services.tag_service import TagInUseError

STATIC_DIR = None   # set by server.py before serving
_container = None   # set by set_container() before serving


def set_container(container) -> None:
    """Inject the service container.  Called once at startup by server.py."""
    global _container
    _container = container


def _get_container():
    """Return the active container, with a backward-compatible fallback.

    New code calls ``set_container()`` explicitly at startup.  Legacy code
    (including existing test helpers) calls ``storage.init()`` instead; in
    that case the container is stored on the storage module and we retrieve
    it here via a lazy import so there is no circular dependency at import
    time.
    """
    if _container is not None:
        return _container
    # Backward-compat path: storage.init() stores the container on itself.
    try:
        from core import storage as _storage_mod  # lazy to avoid circular import
        if _storage_mod._container is not None:
            return _storage_mod._container
    except ImportError:
        pass
    raise RuntimeError(
        "No service container is available. "
        "Call handler.set_container(container) at startup, "
        "or ensure storage.init() has been called."
    )


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
        c = _get_container()

        try:
            if path == "/api/devices":
                return self._send_json({"devices": c.device_service.list_devices()})
            if path == "/api/bandwidth":
                return self._send_json({"rows": c.bandwidth_service.list_bandwidth()})
            if path == "/api/subnets":
                return self._send_json({"subnets": c.subnet_service.list_subnets()})
            if path == "/api/lists":
                return self._send_json({"lists": c.list_service.get_lists()})
            if path == "/api/tags":
                return self._send_json({"tagDefs": c.tag_service.list_tags()})

            m = re.match(r"^/api/lists/([^/]+)/usage$", path)
            if m:
                value = qs.get("value", [""])[0]
                count = c.list_service.usage_count(m.group(1), value)
                return self._send_json({"count": count})

            m = re.match(r"^/api/tags/([^/]+)/usage$", path)
            if m:
                value = qs.get("value", [None])[0]
                if value is not None:
                    count = c.tag_service.value_usage_count(m.group(1), value)
                else:
                    count = c.tag_service.usage_count(m.group(1))
                return self._send_json({"count": count})

            if path == "/api/audit":
                limit = int(qs.get("limit", ["100"])[0])
                return self._send_json({"entries": c.audit_service.list_recent(limit)})

            if path == "/api/history":
                limit = int(qs.get("limit", ["50"])[0])
                return self._send_json({"entries": c.history_service.list_recent(limit)})

            m = re.match(r"^/api/history/([^/]+)$", path)
            if m:
                entry = c.history_service.get(m.group(1))
                if not entry:
                    return self._send_json({"error": "not found"}, 404)
                return self._send_json(entry)

            if path == "/api/meta":
                return self._send_json(c.meta_service.get_meta())

            if path == "/api/export/devices.xlsx":
                data = c.export_service.build_devices_xlsx()
                return self._send_binary(
                    data,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "devices_export.xlsx",
                )
            if path == "/api/export/bandwidth.xlsx":
                data = c.export_service.build_bandwidth_xlsx()
                return self._send_binary(
                    data,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "bandwidth_export.xlsx",
                )
            if path == "/api/export/subnets.xlsx":
                data = c.export_service.build_subnets_xlsx()
                return self._send_binary(
                    data,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "subnets_export.xlsx",
                )

            return self._serve_static(path)
        except Exception as e:
            traceback.print_exc()
            return self._send_json({"error": str(e), "type": type(e).__name__}, 500)

    def _serve_static(self, path):
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
        c = _get_container()

        try:
            if path == "/api/devices":
                return self._upsert_device(body, actor, c)
            if path == "/api/devices/import":
                return self._import_rows(body, actor, scope="devices", c=c)
            if path == "/api/devices/validate-import":
                return self._validate_import_rows(body, scope="devices", c=c)

            if path == "/api/bandwidth":
                return self._upsert_bandwidth(body, actor, c)
            if path == "/api/bandwidth/import":
                return self._import_rows(body, actor, scope="bandwidth", c=c)
            if path == "/api/bandwidth/validate-import":
                return self._validate_import_rows(body, scope="bandwidth", c=c)

            if path == "/api/subnets":
                return self._upsert_subnet(body, actor, c)
            if path == "/api/subnets/import":
                return self._import_rows(body, actor, scope="subnets", c=c)
            if path == "/api/subnets/validate-import":
                return self._validate_import_rows(body, scope="subnets", c=c)

            m = re.match(r"^/api/lists/([^/]+)$", path)
            if m:
                return self._set_list(m.group(1), body, actor, c)

            if path == "/api/tags":
                return self._upsert_tag(body, actor, c)

            if path == "/api/generate":
                return self._generate(actor, c)

            return self._send_json({"error": "not found"}, 404)
        except ValueError as e:
            return self._send_json({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self._send_json({"error": str(e), "type": type(e).__name__}, 500)

    def _upsert_device(self, body, actor, c):
        device = body.get("device")
        if not isinstance(device, dict):
            return self._send_json({"error": "'device' must be an object"}, 400)
        saved = c.device_service.create_or_update(device, actor)
        return self._send_json({"device": saved})

    def _upsert_bandwidth(self, body, actor, c):
        row = body.get("row")
        if not isinstance(row, dict):
            return self._send_json({"error": "'row' must be an object"}, 400)
        saved = c.bandwidth_service.create_or_update(row, actor)
        return self._send_json({"row": saved})

    def _upsert_subnet(self, body, actor, c):
        subnet = body.get("subnet")
        if not isinstance(subnet, dict):
            return self._send_json({"error": "'subnet' must be an object"}, 400)
        saved = c.subnet_service.create_or_update(subnet, actor)
        return self._send_json({"subnet": saved})

    def _import_rows(self, body, actor, scope, c):
        key = {"devices": "devices", "bandwidth": "rows", "subnets": "subnets"}[scope]
        rows = body.get(key)
        if not isinstance(rows, list):
            return self._send_json({"error": f"'{key}' must be a list"}, 400)
        mode = body.get("mode", "merge")

        if scope == "devices":
            result = c.import_service.import_devices(rows, mode, actor)
        elif scope == "bandwidth":
            result = c.import_service.import_bandwidth(rows, mode, actor)
        else:
            result = c.import_service.import_subnets(rows, mode, actor)

        return self._send_json(result)

    def _validate_import_rows(self, body, scope, c):
        key = {"devices": "devices", "bandwidth": "rows", "subnets": "subnets"}[scope]
        rows = body.get(key)
        if not isinstance(rows, list):
            return self._send_json({"error": f"'{key}' must be a list"}, 400)
        mode = body.get("mode", "merge")

        if scope == "devices":
            result = c.import_service.validate_import_devices(rows, mode)
        elif scope == "bandwidth":
            result = c.import_service.validate_import_bandwidth(rows, mode)
        elif scope == "subnets":
            result = c.import_service.validate_import_subnets(rows, mode)
        else:
            return self._send_json({"error": "unknown scope"}, 400)

        return self._send_json(result)

    def _set_list(self, list_name, body, actor, c):
        items = body.get("items")
        if not isinstance(items, list):
            return self._send_json({"error": "'items' must be a list"}, 400)
        try:
            saved = c.list_service.set_list(list_name, items, actor)
        except ValueError as e:
            return self._send_json({"error": str(e)}, 404)
        return self._send_json({"items": saved})

    def _upsert_tag(self, body, actor, c):
        tag_def = body.get("tagDef")
        if not isinstance(tag_def, dict):
            return self._send_json({"error": "'tagDef' must be an object"}, 400)
        saved = c.tag_service.create_or_update(tag_def, actor)
        return self._send_json({"tagDef": saved})

    def _generate(self, actor, c):
        result = c.generate_service.generate(actor)
        return self._send_json(result)

    # -------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)
        actor = qs.get("_actor", [None])[0]
        c = _get_container()

        try:
            m = re.match(r"^/api/devices/([^/]+)$", path)
            if m:
                c.device_service.delete(m.group(1), actor)
                return self._send_json({"deleted": m.group(1)})

            m = re.match(r"^/api/bandwidth/([^/]+)$", path)
            if m:
                c.bandwidth_service.delete(m.group(1), actor)
                return self._send_json({"deleted": m.group(1)})

            m = re.match(r"^/api/subnets/([^/]+)$", path)
            if m:
                c.subnet_service.delete(m.group(1), actor)
                return self._send_json({"deleted": m.group(1)})

            m = re.match(r"^/api/tags/([^/]+)$", path)
            if m:
                tag_id = m.group(1)
                force = qs.get("force", ["false"])[0] == "true"
                try:
                    result = c.tag_service.delete(tag_id, actor, force=force)
                    return self._send_json({"deleted": result["deleted"]})
                except TagInUseError as e:
                    return self._send_json(
                        {"error": "tag is in use", "dependents": e.dependents}, 409
                    )

            return self._send_json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._send_json({"error": str(e), "type": type(e).__name__}, 500)
