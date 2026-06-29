"""
Unit tests for DeviceService.

All repository dependencies are replaced with ``unittest.mock.MagicMock``
objects, so these tests exercise only the service's own logic — input
validation, audit event selection, and return-value forwarding — without
touching SQLite at all.

Run from the repository root:
    python3 -m unittest tests/services/test_device_service.py
    python3 -m unittest discover tests/services/
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.services.device_service import DeviceService


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_service():
    """Return a DeviceService backed by mock repositories."""
    device_repo = MagicMock()
    audit_repo = MagicMock()
    service = DeviceService(device_repo=device_repo, audit_repo=audit_repo)
    return service, device_repo, audit_repo


def _device(ip="192.0.2.1", name="Router1", region="us-east", device_id=None):
    d = {"IP": ip, "Device": name, "Collector Region": region}
    if device_id is not None:
        d["id"] = device_id
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListDevices(unittest.TestCase):
    def test_delegates_to_repo(self):
        svc, repo, _ = _make_service()
        expected = [_device()]
        repo.list_all.return_value = expected
        result = svc.list_devices()
        repo.list_all.assert_called_once_with()
        self.assertEqual(result, expected)


class TestGetDevice(unittest.TestCase):
    def test_delegates_to_repo(self):
        svc, repo, _ = _make_service()
        repo.get.return_value = _device()
        result = svc.get_device("some-id")
        repo.get.assert_called_once_with("some-id")
        self.assertIsNotNone(result)

    def test_returns_none_for_missing(self):
        svc, repo, _ = _make_service()
        repo.get.return_value = None
        self.assertIsNone(svc.get_device("ghost"))


class TestCreateOrUpdate(unittest.TestCase):
    def test_valid_device_is_upserted(self):
        svc, repo, audit = _make_service()
        device = _device()
        repo.upsert.return_value = {**device, "id": "new-id"}
        saved = svc.create_or_update(device, actor="alice")
        repo.upsert.assert_called_once_with(device)
        self.assertEqual(saved["id"], "new-id")

    def test_create_logs_create_device_action(self):
        """A device without an id should produce a create_device audit entry."""
        svc, repo, audit = _make_service()
        device = _device()  # no id — new record
        repo.upsert.return_value = {**device, "id": "gen-id"}
        svc.create_or_update(device, actor="alice")
        audit.log.assert_called_once()
        action = audit.log.call_args[0][1]
        self.assertEqual(action, "create_device")

    def test_update_logs_update_device_action(self):
        """A device with a pre-existing id should produce an update_device entry."""
        svc, repo, audit = _make_service()
        device = _device(device_id="existing-id")
        repo.upsert.return_value = device
        svc.create_or_update(device, actor="bob")
        action = audit.log.call_args[0][1]
        self.assertEqual(action, "update_device")

    def test_invalid_ip_raises_value_error(self):
        svc, repo, audit = _make_service()
        with self.assertRaises(ValueError) as ctx:
            svc.create_or_update({"IP": "not-an-ip"}, actor="alice")
        self.assertIn("not-an-ip", str(ctx.exception))
        repo.upsert.assert_not_called()
        audit.log.assert_not_called()

    def test_blank_ip_is_accepted(self):
        """A blank IP is valid at the service level — the validator catches it."""
        svc, repo, audit = _make_service()
        device = {"IP": "", "Device": "NoIP"}
        repo.upsert.return_value = {**device, "id": "x"}
        svc.create_or_update(device, actor="alice")
        repo.upsert.assert_called_once()

    def test_actor_passed_to_audit(self):
        svc, repo, audit = _make_service()
        device = _device()
        repo.upsert.return_value = {**device, "id": "y"}
        svc.create_or_update(device, actor="charlie")
        actor_arg = audit.log.call_args[0][0]
        self.assertEqual(actor_arg, "charlie")

    def test_none_actor_accepted(self):
        svc, repo, audit = _make_service()
        device = _device()
        repo.upsert.return_value = {**device, "id": "z"}
        svc.create_or_update(device, actor=None)
        audit.log.assert_called_once()


class TestDelete(unittest.TestCase):
    def test_delete_delegates_to_repo(self):
        svc, repo, audit = _make_service()
        svc.delete("some-id", actor="alice")
        repo.delete.assert_called_once_with("some-id")

    def test_delete_logs_audit_entry(self):
        svc, repo, audit = _make_service()
        svc.delete("del-id", actor="bob")
        audit.log.assert_called_once()
        action = audit.log.call_args[0][1]
        self.assertEqual(action, "delete_device")


class TestReplaceAll(unittest.TestCase):
    def test_calls_repo_replace_all(self):
        svc, repo, audit = _make_service()
        devices = [_device("192.0.2.1"), _device("192.0.2.2")]
        svc.replace_all(devices, actor="alice")
        repo.replace_all.assert_called_once_with(devices)

    def test_logs_import_audit_with_mode_replace(self):
        svc, repo, audit = _make_service()
        svc.replace_all([], actor="alice")
        details = audit.log.call_args[0][2]
        self.assertEqual(details["mode"], "replace")


class TestMerge(unittest.TestCase):
    def test_calls_repo_merge(self):
        svc, repo, audit = _make_service()
        devices = [_device()]
        svc.merge(devices, actor="alice")
        repo.merge.assert_called_once_with(devices)

    def test_logs_import_audit_with_mode_merge(self):
        svc, repo, audit = _make_service()
        svc.merge([], actor="alice")
        details = audit.log.call_args[0][2]
        self.assertEqual(details["mode"], "merge")


if __name__ == "__main__":
    unittest.main()
