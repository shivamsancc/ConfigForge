"""
Unit and integration tests for API versioning.

Contracts verified
------------------
1.  Every endpoint is reachable under /api/v1/.
2.  The unversioned /api/<resource> paths return 404 (no fallback routing).
3.  The OpenAPI spec (GET /openapi.json) lists /api/v1/ paths only.
4.  The Swagger UI is served at /docs.
5.  The ReDoc UI is served at /redoc.
6.  The FastAPI app title contains "v1".
7.  api/v1/router.VERSION == "v1".
8.  api/v1/router.PREFIX == "/api/v1".
9.  Response shapes on v1 endpoints are unchanged from pre-versioning.
10. POST to old /api/devices path returns 404 (not 405 — route truly absent).

How to add v2 (structural test)
---------------------------------
The test ``test_v2_router_can_be_added_alongside_v1`` demonstrates the
extension pattern: create a new APIRouter with prefix="/v2", include it
under "/api", and both /api/v1/ and /api/v2/ coexist without conflict.

Run from repository root::

    python3 -m pytest tests/api/test_versioning.py -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import create_app
from api.v1.router import VERSION, PREFIX, router as v1_router


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

def _make_client() -> TestClient:
    """
    Fresh in-memory app for each test class.

    ``static_dir`` is set to a path that does not exist so that StaticFiles
    is NOT mounted.  This keeps tests focused on the API routing layer and
    avoids the StaticFiles catch-all handler returning 405 for POST requests
    to unregistered paths (which would mask the expected 404 response).
    """
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "versioning_test.db")
    app = create_app(db_path=db_path, static_dir=os.path.join(tmpdir, "_no_static_"))
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Router constants
# ---------------------------------------------------------------------------

class TestRouterConstants(unittest.TestCase):
    def test_version_constant_is_v1(self):
        self.assertEqual(VERSION, "v1")

    def test_prefix_constant_is_api_v1(self):
        self.assertEqual(PREFIX, "/api/v1")

    def test_v1_router_has_v1_prefix(self):
        self.assertEqual(v1_router.prefix, "/v1")


# ---------------------------------------------------------------------------
# OpenAPI metadata
# ---------------------------------------------------------------------------

class TestOpenAPIMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _make_client()
        cls.spec = cls.client.get("/openapi.json").json()

    def test_swagger_ui_is_served(self):
        r = self.client.get("/docs")
        self.assertEqual(r.status_code, 200)

    def test_redoc_is_served(self):
        r = self.client.get("/redoc")
        self.assertEqual(r.status_code, 200)

    def test_openapi_json_is_served(self):
        r = self.client.get("/openapi.json")
        self.assertEqual(r.status_code, 200)

    def test_app_title_contains_v1(self):
        self.assertIn("v1", self.spec["info"]["title"])

    def test_openapi_version_field_present(self):
        self.assertIn("version", self.spec["info"])

    def test_all_paths_are_under_api_v1(self):
        """Every path in the OpenAPI spec must start with /api/v1/."""
        paths = self.spec.get("paths", {})
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(
                    path.startswith("/api/v1/"),
                    f"Path {path!r} does not start with /api/v1/",
                )

    def test_no_unversioned_api_paths(self):
        """There must be no /api/<resource> paths (without /v1)."""
        paths = self.spec.get("paths", {})
        unversioned = [
            p for p in paths
            if p.startswith("/api/") and not p.startswith("/api/v1/")
        ]
        self.assertEqual(
            unversioned, [],
            f"Found unversioned API paths: {unversioned}",
        )

    def test_openapi_tags_include_devices(self):
        tag_names = {t["name"] for t in self.spec.get("tags", [])}
        self.assertIn("devices", tag_names)

    def test_openapi_has_ten_tags(self):
        """One tag per resource group: devices, bandwidth, subnets, tags,
        lists, generate, audit, history, meta, export."""
        tags = self.spec.get("tags", [])
        self.assertEqual(len(tags), 10)


# ---------------------------------------------------------------------------
# v1 endpoints reachable
# ---------------------------------------------------------------------------

class TestV1EndpointsReachable(unittest.TestCase):
    """Smoke-test that every v1 resource path responds (not 404/405)."""

    @classmethod
    def setUpClass(cls):
        cls.client = _make_client()

    def _get(self, path):
        return self.client.get(path)

    def test_v1_devices_list(self):
        r = self._get("/api/v1/devices")
        self.assertNotEqual(r.status_code, 404)
        self.assertIn("devices", r.json())

    def test_v1_bandwidth_list(self):
        r = self._get("/api/v1/bandwidth")
        self.assertNotEqual(r.status_code, 404)
        self.assertIn("rows", r.json())

    def test_v1_subnets_list(self):
        r = self._get("/api/v1/subnets")
        self.assertNotEqual(r.status_code, 404)
        self.assertIn("subnets", r.json())

    def test_v1_tags_list(self):
        r = self._get("/api/v1/tags")
        self.assertNotEqual(r.status_code, 404)
        self.assertIn("tagDefs", r.json())

    def test_v1_lists(self):
        r = self._get("/api/v1/lists")
        self.assertNotEqual(r.status_code, 404)
        self.assertIn("lists", r.json())

    def test_v1_audit(self):
        r = self._get("/api/v1/audit")
        self.assertNotEqual(r.status_code, 404)
        self.assertIn("entries", r.json())

    def test_v1_history(self):
        r = self._get("/api/v1/history")
        self.assertNotEqual(r.status_code, 404)
        self.assertIn("entries", r.json())

    def test_v1_meta(self):
        r = self._get("/api/v1/meta")
        self.assertNotEqual(r.status_code, 404)

    def test_v1_devices_validate_import_post(self):
        r = self.client.post("/api/v1/devices/validate-import", json={"devices": []})
        self.assertEqual(r.status_code, 200)
        self.assertIn("findings", r.json())

    def test_v1_bandwidth_validate_import_post(self):
        r = self.client.post("/api/v1/bandwidth/validate-import", json={"rows": []})
        self.assertEqual(r.status_code, 200)
        self.assertIn("findings", r.json())

    def test_v1_subnets_validate_import_post(self):
        r = self.client.post("/api/v1/subnets/validate-import", json={"subnets": []})
        self.assertEqual(r.status_code, 200)
        self.assertIn("findings", r.json())


# ---------------------------------------------------------------------------
# Old unversioned paths return 404
# ---------------------------------------------------------------------------

class TestUnversionedPathsAbsent(unittest.TestCase):
    """Routes must NOT be served at /api/<resource> — only /api/v1/<resource>."""

    @classmethod
    def setUpClass(cls):
        cls.client = _make_client()

    def _assert_404(self, method, path, **kwargs):
        fn = getattr(self.client, method)
        r = fn(path, **kwargs)
        self.assertEqual(
            r.status_code, 404,
            f"Expected 404 for {method.upper()} {path}, got {r.status_code}",
        )

    def test_old_devices_get_returns_404(self):
        self._assert_404("get", "/api/devices")

    def test_old_bandwidth_get_returns_404(self):
        self._assert_404("get", "/api/bandwidth")

    def test_old_subnets_get_returns_404(self):
        self._assert_404("get", "/api/subnets")

    def test_old_tags_get_returns_404(self):
        self._assert_404("get", "/api/tags")

    def test_old_lists_get_returns_404(self):
        self._assert_404("get", "/api/lists")

    def test_old_audit_get_returns_404(self):
        self._assert_404("get", "/api/audit")

    def test_old_history_get_returns_404(self):
        self._assert_404("get", "/api/history")

    def test_old_meta_get_returns_404(self):
        self._assert_404("get", "/api/meta")

    def test_old_devices_post_returns_404(self):
        self._assert_404("post", "/api/devices", json={"device": {}})

    def test_old_validate_import_returns_404(self):
        self._assert_404(
            "post", "/api/devices/validate-import",
            json={"devices": []},
        )


# ---------------------------------------------------------------------------
# Response schema unchanged
# ---------------------------------------------------------------------------

class TestV1ResponseSchemas(unittest.TestCase):
    """Verify that v1 response shapes are identical to the pre-versioning API."""

    @classmethod
    def setUpClass(cls):
        cls.client = _make_client()

    def test_devices_list_shape(self):
        data = self.client.get("/api/v1/devices").json()
        self.assertIn("devices", data)
        self.assertIsInstance(data["devices"], list)

    def test_bandwidth_list_shape(self):
        data = self.client.get("/api/v1/bandwidth").json()
        self.assertIn("rows", data)
        self.assertIsInstance(data["rows"], list)

    def test_subnets_list_shape(self):
        data = self.client.get("/api/v1/subnets").json()
        self.assertIn("subnets", data)
        self.assertIsInstance(data["subnets"], list)

    def test_tags_list_shape(self):
        data = self.client.get("/api/v1/tags").json()
        self.assertIn("tagDefs", data)
        self.assertIsInstance(data["tagDefs"], list)

    def test_lists_shape(self):
        data = self.client.get("/api/v1/lists").json()
        self.assertIn("lists", data)
        self.assertIsInstance(data["lists"], dict)

    def test_audit_shape(self):
        data = self.client.get("/api/v1/audit").json()
        self.assertIn("entries", data)
        self.assertIsInstance(data["entries"], list)

    def test_history_shape(self):
        data = self.client.get("/api/v1/history").json()
        self.assertIn("entries", data)
        self.assertIsInstance(data["entries"], list)

    def test_validate_import_devices_shape(self):
        r = self.client.post(
            "/api/v1/devices/validate-import", json={"devices": []}
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("findings", data)
        self.assertIsInstance(data["findings"], list)

    def test_validate_import_missing_key_returns_400(self):
        r = self.client.post("/api/v1/devices/validate-import", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.json())


# ---------------------------------------------------------------------------
# Extension pattern: v2 can coexist with v1
# ---------------------------------------------------------------------------

class TestFutureVersionCoexistence(unittest.TestCase):
    """
    Demonstrates that a v2 router can be added alongside v1 without
    disturbing existing v1 routes.

    This test does NOT require api/v2/ to exist in the codebase — it
    builds a minimal stub router in-process to verify the mounting pattern.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile, os
        tmpdir = tempfile.mkdtemp()
        db = os.path.join(tmpdir, "coexist.db")

        # Build the real app WITHOUT StaticFiles so the catch-all mount does
        # not shadow the v2 router we add below.  In production you would
        # register all versioned routers BEFORE mounting StaticFiles in
        # create_app() — the same ordering rule applies.
        cls.app = create_app(
            db_path=db,
            static_dir=os.path.join(tmpdir, "_no_static_"),
        )

        # Simulate a future v2 stub: one endpoint, new prefix.
        # In a real implementation this would be:
        #   from api.v2.router import router as v2_router
        #   cls.app.include_router(v2_router, prefix="/api")
        v2_stub = APIRouter(prefix="/v2")

        @v2_stub.get("/devices")
        def v2_devices():
            return {"devices": [], "version": "v2"}

        cls.app.include_router(v2_stub, prefix="/api")
        cls.client = TestClient(cls.app, raise_server_exceptions=False)

    def test_v1_devices_still_works_after_v2_mounted(self):
        r = self.client.get("/api/v1/devices")
        self.assertEqual(r.status_code, 200)
        self.assertIn("devices", r.json())

    def test_v2_stub_devices_reachable(self):
        r = self.client.get("/api/v2/devices")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("devices", data)
        self.assertEqual(data.get("version"), "v2")

    def test_v1_and_v2_both_in_openapi_spec(self):
        spec = self.client.get("/openapi.json").json()
        paths = list(spec.get("paths", {}).keys())
        v1_paths = [p for p in paths if p.startswith("/api/v1/")]
        v2_paths = [p for p in paths if p.startswith("/api/v2/")]
        self.assertTrue(len(v1_paths) > 0, "No v1 paths in combined spec")
        self.assertTrue(len(v2_paths) > 0, "No v2 paths in combined spec")

    def test_v2_does_not_shadow_v1(self):
        """Adding /api/v2/devices must not remove /api/v1/devices."""
        spec = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/devices", spec.get("paths", {}))
        self.assertIn("/api/v2/devices", spec.get("paths", {}))


if __name__ == "__main__":
    unittest.main()
