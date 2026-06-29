"""
Integration tests for SQLiteDeviceRepository.

Each test class spins up a fresh in-memory SQLite database (via
ServiceContainer) so it is completely isolated from other tests and from
the production database file.

Run from the repository root:
    python3 -m unittest tests/repositories/test_sqlite_device_repository.py
    python3 -m unittest discover tests/repositories/

Contracts verified
------------------
1.  list_all() returns an empty list for a fresh database.
2.  upsert() assigns a UUID when no id is provided.
3.  upsert() returns the record with the id populated.
4.  list_all() returns previously upserted records.
5.  Credential fields (authKey, privKey) are encrypted at rest and
    transparently decrypted on read.
6.  get() retrieves a single record by id; returns None for unknown ids.
7.  delete() removes a record; list_all() no longer returns it.
8.  replace_all() removes ALL existing records and inserts the new list.
9.  merge() upserts without touching unreferenced records.
10. Tags default to {} when not supplied.
"""
import os
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.container import ServiceContainer


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _device(
    ip: str = "192.0.2.1",
    name: str = "Router1",
    region: str = "us-east",
    auth_key: str = "authsecret",
    priv_key: str = "privsecret",
) -> dict:
    return {
        "IP": ip,
        "Device": name,
        "Collector Region": region,
        "snmpUser": "admin",
        "authProtocol": "SHA",
        "authKey": auth_key,
        "privProtocol": "AES",
        "privKey": priv_key,
    }


class _ContainerFixture:
    """Utility that creates a ServiceContainer backed by a temp SQLite file."""

    def __init__(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "test.db")
        self.container = ServiceContainer(db_path)
        self.repo = self.container.device_repo

    def teardown(self):
        self._tmpdir.cleanup()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestListAllEmpty(unittest.TestCase):
    def setUp(self):
        self._fix = _ContainerFixture()

    def tearDown(self):
        self._fix.teardown()

    def test_empty_database_returns_empty_list(self):
        self.assertEqual(self._fix.repo.list_all(), [])


class TestUpsertCreatesRecord(unittest.TestCase):
    def setUp(self):
        self._fix = _ContainerFixture()

    def tearDown(self):
        self._fix.teardown()

    def test_upsert_without_id_assigns_uuid(self):
        d = _device()
        saved = self._fix.repo.upsert(d)
        self.assertIn("id", saved)
        self.assertTrue(saved["id"])

    def test_upsert_returns_same_id_on_update(self):
        saved = self._fix.repo.upsert(_device())
        first_id = saved["id"]
        saved["Device"] = "UpdatedName"
        updated = self._fix.repo.upsert(saved)
        self.assertEqual(updated["id"], first_id)

    def test_list_all_returns_upserted_record(self):
        self._fix.repo.upsert(_device(ip="192.0.2.10", name="R10"))
        devices = self._fix.repo.list_all()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["IP"], "192.0.2.10")
        self.assertEqual(devices[0]["Device"], "R10")

    def test_tags_default_to_empty_dict(self):
        saved = self._fix.repo.upsert(_device())
        self.assertEqual(saved.get("tags"), {})

    def test_list_all_multiple_records(self):
        for i in range(1, 4):
            self._fix.repo.upsert(_device(ip=f"192.0.2.{i}", name=f"R{i}"))
        self.assertEqual(len(self._fix.repo.list_all()), 3)


class TestCredentialEncryption(unittest.TestCase):
    """authKey and privKey must survive a round-trip through encrypt/decrypt."""

    def setUp(self):
        self._fix = _ContainerFixture()

    def tearDown(self):
        self._fix.teardown()

    def test_auth_key_decrypted_on_read(self):
        self._fix.repo.upsert(_device(auth_key="my-auth-secret"))
        result = self._fix.repo.list_all()[0]
        self.assertEqual(result["authKey"], "my-auth-secret")

    def test_priv_key_decrypted_on_read(self):
        self._fix.repo.upsert(_device(priv_key="my-priv-secret"))
        result = self._fix.repo.list_all()[0]
        self.assertEqual(result["privKey"], "my-priv-secret")

    def test_credentials_not_stored_as_plaintext(self):
        """Read the raw SQLite row to confirm the value is not plain text."""
        import json as _json
        from sqlalchemy import text as _text
        self._fix.repo.upsert(_device(auth_key="toplevel-secret"))
        engine = self._fix.container._engine
        with engine.connect() as conn:
            row = conn.execute(_text("SELECT data FROM devices")).fetchone()
        data = _json.loads(row[0])
        # The stored value should not be the plaintext passphrase.
        self.assertNotEqual(data.get("authKey"), "toplevel-secret")

    def test_get_also_decrypts(self):
        saved = self._fix.repo.upsert(_device(auth_key="get-secret"))
        fetched = self._fix.repo.get(saved["id"])
        self.assertEqual(fetched["authKey"], "get-secret")


class TestGetById(unittest.TestCase):
    def setUp(self):
        self._fix = _ContainerFixture()

    def tearDown(self):
        self._fix.teardown()

    def test_get_returns_record(self):
        saved = self._fix.repo.upsert(_device(name="FindMe"))
        fetched = self._fix.repo.get(saved["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["Device"], "FindMe")

    def test_get_unknown_id_returns_none(self):
        self.assertIsNone(self._fix.repo.get("no-such-id"))


class TestDelete(unittest.TestCase):
    def setUp(self):
        self._fix = _ContainerFixture()

    def tearDown(self):
        self._fix.teardown()

    def test_delete_removes_record(self):
        saved = self._fix.repo.upsert(_device())
        self._fix.repo.delete(saved["id"])
        self.assertEqual(self._fix.repo.list_all(), [])

    def test_delete_is_idempotent(self):
        # Deleting a non-existent id should not raise.
        self._fix.repo.delete("ghost-id")

    def test_delete_leaves_other_records_intact(self):
        a = self._fix.repo.upsert(_device(ip="192.0.2.1", name="A"))
        b = self._fix.repo.upsert(_device(ip="192.0.2.2", name="B"))
        self._fix.repo.delete(a["id"])
        remaining = self._fix.repo.list_all()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["Device"], "B")


class TestReplaceAll(unittest.TestCase):
    def setUp(self):
        self._fix = _ContainerFixture()

    def tearDown(self):
        self._fix.teardown()

    def test_replace_all_clears_existing_records(self):
        self._fix.repo.upsert(_device(ip="192.0.2.1"))
        self._fix.repo.upsert(_device(ip="192.0.2.2"))
        self._fix.repo.replace_all([_device(ip="192.0.2.99", name="Only")])
        devices = self._fix.repo.list_all()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["IP"], "192.0.2.99")

    def test_replace_all_with_empty_list_deletes_everything(self):
        self._fix.repo.upsert(_device())
        self._fix.repo.replace_all([])
        self.assertEqual(self._fix.repo.list_all(), [])

    def test_replace_all_assigns_ids_to_new_records(self):
        new_records = [_device(ip="192.0.2.1"), _device(ip="192.0.2.2")]
        self._fix.repo.replace_all(new_records)
        for d in self._fix.repo.list_all():
            self.assertTrue(d.get("id"))


class TestMerge(unittest.TestCase):
    def setUp(self):
        self._fix = _ContainerFixture()

    def tearDown(self):
        self._fix.teardown()

    def test_merge_adds_new_record(self):
        existing = self._fix.repo.upsert(_device(ip="192.0.2.1", name="Existing"))
        self._fix.repo.merge([_device(ip="192.0.2.2", name="New")])
        devices = self._fix.repo.list_all()
        self.assertEqual(len(devices), 2)

    def test_merge_updates_existing_record_by_id(self):
        saved = self._fix.repo.upsert(_device(name="Original"))
        saved["Device"] = "Updated"
        self._fix.repo.merge([saved])
        result = self._fix.repo.get(saved["id"])
        self.assertEqual(result["Device"], "Updated")

    def test_merge_leaves_untouched_records_intact(self):
        keep = self._fix.repo.upsert(_device(ip="192.0.2.1", name="Keep"))
        self._fix.repo.merge([_device(ip="192.0.2.2", name="New")])
        result = self._fix.repo.get(keep["id"])
        self.assertIsNotNone(result)
        self.assertEqual(result["Device"], "Keep")


if __name__ == "__main__":
    unittest.main()
