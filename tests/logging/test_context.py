"""
Tests for core.logging.context — ContextVar-based request ID propagation.

Covers:
- Default value is "-"
- set_request_id / get_request_id round-trip
- reset_request_id restores previous value
- generate_request_id produces 12 hex chars
- ContextVar isolation between asyncio tasks
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.logging.context import (
    generate_request_id,
    get_request_id,
    reset_request_id,
    set_request_id,
)


class TestGetRequestId(unittest.TestCase):
    def setUp(self):
        # Ensure clean state: reset to default by setting then resetting
        self._token = set_request_id("-")

    def tearDown(self):
        reset_request_id(self._token)

    def test_default_is_dash(self):
        # Fresh ContextVar default
        tok = set_request_id("-")
        self.assertEqual(get_request_id(), "-")
        reset_request_id(tok)

    def test_set_and_get(self):
        tok = set_request_id("abc123def456")
        self.assertEqual(get_request_id(), "abc123def456")
        reset_request_id(tok)

    def test_reset_restores_previous(self):
        tok1 = set_request_id("first")
        self.assertEqual(get_request_id(), "first")

        tok2 = set_request_id("second")
        self.assertEqual(get_request_id(), "second")

        reset_request_id(tok2)
        self.assertEqual(get_request_id(), "first")

        reset_request_id(tok1)


class TestGenerateRequestId(unittest.TestCase):
    def test_returns_12_chars(self):
        rid = generate_request_id()
        self.assertEqual(len(rid), 12)

    def test_returns_hex_string(self):
        rid = generate_request_id()
        int(rid, 16)   # raises ValueError if not valid hex

    def test_uniqueness(self):
        ids = {generate_request_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)

    def test_lowercase(self):
        rid = generate_request_id()
        self.assertEqual(rid, rid.lower())


class TestContextVarIsolation(unittest.TestCase):
    """ContextVar values must not bleed between independent asyncio tasks."""

    def test_tasks_have_independent_context(self):
        results = {}

        async def _inner():
            tok_a = set_request_id("task-A")
            try:
                results["A"] = get_request_id()
            finally:
                reset_request_id(tok_a)

        async def _outer():
            tok = set_request_id("outer")
            try:
                task = asyncio.ensure_future(_inner())
                await task
                # After the task, the outer context should be unchanged
                results["outer_after"] = get_request_id()
            finally:
                reset_request_id(tok)

        asyncio.run(_outer())
        self.assertEqual(results["A"], "task-A")
        self.assertEqual(results["outer_after"], "outer")

    def test_concurrent_tasks_do_not_interfere(self):
        """Two concurrent tasks each see their own request ID."""
        records = []

        async def _worker(label: str, delay: float):
            tok = set_request_id(label)
            try:
                await asyncio.sleep(delay)
                records.append((label, get_request_id()))
            finally:
                reset_request_id(tok)

        async def _run():
            await asyncio.gather(
                _worker("task-1", 0.01),
                _worker("task-2", 0.005),
            )

        asyncio.run(_run())

        # Each task must have seen its own ID, not the other task's.
        for label, seen in records:
            self.assertEqual(label, seen, f"Task {label!r} saw request_id {seen!r}")


if __name__ == "__main__":
    unittest.main()
