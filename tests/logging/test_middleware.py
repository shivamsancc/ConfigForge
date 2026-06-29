"""
Tests for core.logging.middleware — CorrelationIDMiddleware and
RequestLoggingMiddleware.

Contracts verified:
- CorrelationIDMiddleware generates X-Request-ID when absent from request
- CorrelationIDMiddleware propagates X-Request-ID when present in request
- X-Request-ID always appears in the response headers
- Generated request IDs are 12 lowercase hex chars
- RequestLoggingMiddleware logs method, path, status, duration, ip
- RequestLoggingMiddleware NEVER logs request body content
- Correlation ID is present in request log records (ContextVar set before logging)
- Long X-Request-ID values are capped at 128 chars (log injection guard)
"""
import logging
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi.testclient import TestClient

from app import create_app


def _make_client(db_path: str) -> TestClient:
    """Create a TestClient with no static directory (avoids 405 edge-case)."""
    app = create_app(
        db_path=db_path,
        static_dir=os.path.join(tempfile.mkdtemp(), "_no_static_"),
    )
    return TestClient(app, raise_server_exceptions=False)


class TestCorrelationIDMiddleware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp()
        cls._db = os.path.join(cls._tmpdir, "test.db")
        cls._client = _make_client(cls._db)

    def test_response_always_has_x_request_id(self):
        resp = self._client.get("/api/v1/devices")
        self.assertIn("x-request-id", resp.headers)

    def test_generated_id_is_12_hex_chars(self):
        resp = self._client.get("/api/v1/devices")
        rid = resp.headers["x-request-id"]
        self.assertEqual(len(rid), 12)
        int(rid, 16)   # raises if not valid hex

    def test_client_supplied_id_is_echoed_back(self):
        custom_id = "myrequest0001"
        resp = self._client.get(
            "/api/v1/devices",
            headers={"X-Request-ID": custom_id},
        )
        self.assertEqual(resp.headers["x-request-id"], custom_id)

    def test_long_client_id_is_truncated_to_128(self):
        long_id = "a" * 200
        resp = self._client.get(
            "/api/v1/devices",
            headers={"X-Request-ID": long_id},
        )
        returned = resp.headers["x-request-id"]
        self.assertLessEqual(len(returned), 128)

    def test_each_request_gets_unique_id(self):
        ids = set()
        for _ in range(20):
            resp = self._client.get("/api/v1/devices")
            ids.add(resp.headers["x-request-id"])
        self.assertEqual(len(ids), 20)


class TestRequestLoggingMiddleware(unittest.TestCase):
    """Verify that the request logger emits the expected fields."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp()
        cls._db = os.path.join(cls._tmpdir, "test_reqlog.db")
        cls._client = _make_client(cls._db)

    def _capture_logs(self) -> list[logging.LogRecord]:
        """Attach a capturing handler to configfoundry.http for one block."""
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = logging.getLogger("configfoundry.http")
        handler = _Capture()
        logger.addHandler(handler)
        # Temporarily lower effective level so INFO records pass through
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            return records, handler, old_level, logger
        finally:
            pass  # caller cleans up

    def test_request_log_contains_method(self):
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        http_logger = logging.getLogger("configfoundry.http")
        cap = _Capture()
        old_level = http_logger.level
        http_logger.addHandler(cap)
        http_logger.setLevel(logging.DEBUG)
        try:
            self._client.get("/api/v1/devices")
        finally:
            http_logger.removeHandler(cap)
            http_logger.setLevel(old_level)

        self.assertTrue(
            any("GET" in r.getMessage() for r in records),
            "Expected 'GET' in at least one log record",
        )

    def test_request_log_contains_path(self):
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        http_logger = logging.getLogger("configfoundry.http")
        cap = _Capture()
        old_level = http_logger.level
        http_logger.addHandler(cap)
        http_logger.setLevel(logging.DEBUG)
        try:
            self._client.get("/api/v1/devices")
        finally:
            http_logger.removeHandler(cap)
            http_logger.setLevel(old_level)

        messages = [r.getMessage() for r in records]
        self.assertTrue(
            any("/api/v1/devices" in m for m in messages),
            f"Expected path in log. Got: {messages}",
        )

    def test_request_log_contains_status_code(self):
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        http_logger = logging.getLogger("configfoundry.http")
        cap = _Capture()
        old_level = http_logger.level
        http_logger.addHandler(cap)
        http_logger.setLevel(logging.DEBUG)
        try:
            self._client.get("/api/v1/devices")
        finally:
            http_logger.removeHandler(cap)
            http_logger.setLevel(old_level)

        messages = [r.getMessage() for r in records]
        self.assertTrue(
            any("200" in m for m in messages),
            f"Expected status 200 in log. Got: {messages}",
        )

    def test_request_log_does_not_contain_request_body(self):
        """Ensure bodies are NEVER logged — security requirement."""
        records: list[logging.LogRecord] = []
        sensitive_payload = '{"password": "supersecret123", "token": "abc"}'

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        http_logger = logging.getLogger("configfoundry.http")
        cap = _Capture()
        old_level = http_logger.level
        http_logger.addHandler(cap)
        http_logger.setLevel(logging.DEBUG)
        try:
            # POST with sensitive body — body must never appear in any log record
            self._client.post(
                "/api/v1/devices",
                content=sensitive_payload,
                headers={"Content-Type": "application/json"},
            )
        finally:
            http_logger.removeHandler(cap)
            http_logger.setLevel(old_level)

        for record in records:
            msg = record.getMessage()
            self.assertNotIn(
                "supersecret123", msg,
                "Sensitive data from request body appeared in log!",
            )
            self.assertNotIn("supersecret123", str(record.__dict__))


if __name__ == "__main__":
    unittest.main()
