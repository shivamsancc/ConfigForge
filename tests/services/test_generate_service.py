"""
Unit tests for GenerateService.

All six repositories are replaced with ``unittest.mock.MagicMock`` objects
so the tests only exercise the GenerateService's own orchestration — that
it calls the right repositories, passes results through logic/validator,
persists history, and writes an audit entry.

Run from the repository root:
    python3 -m unittest tests/services/test_generate_service.py
    python3 -m unittest discover tests/services/
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.services.generate_service import GenerateService


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_service():
    """Return a GenerateService backed entirely by mock repositories."""
    device_repo = MagicMock()
    bandwidth_repo = MagicMock()
    subnet_repo = MagicMock()
    tag_repo = MagicMock()
    history_repo = MagicMock()
    meta_repo = MagicMock()
    audit_repo = MagicMock()

    # Default: each list_all() returns an empty list.
    device_repo.list_all.return_value = []
    bandwidth_repo.list_all.return_value = []
    subnet_repo.list_all.return_value = []
    tag_repo.list_all.return_value = []

    svc = GenerateService(
        device_repo=device_repo,
        bandwidth_repo=bandwidth_repo,
        subnet_repo=subnet_repo,
        tag_repo=tag_repo,
        history_repo=history_repo,
        meta_repo=meta_repo,
        audit_repo=audit_repo,
    )
    repos = {
        "device": device_repo,
        "bandwidth": bandwidth_repo,
        "subnet": subnet_repo,
        "tag": tag_repo,
        "history": history_repo,
        "meta": meta_repo,
        "audit": audit_repo,
    }
    return svc, repos


def _make_device(ip="192.0.2.1", name="R1", region="us-east"):
    return {
        "IP": ip, "Device": name, "Collector Region": region,
        "snmpUser": "admin", "authProtocol": "SHA",
        "authKey": "auth", "privProtocol": "AES", "privKey": "priv",
        "tags": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateLoadsAllInventory(unittest.TestCase):
    """GenerateService must read all four inventory collections."""

    def setUp(self):
        self.svc, self.repos = _make_service()

    def test_loads_devices(self):
        self.svc.generate(actor="alice")
        self.repos["device"].list_all.assert_called_once()

    def test_loads_bandwidth(self):
        self.svc.generate(actor="alice")
        self.repos["bandwidth"].list_all.assert_called_once()

    def test_loads_subnets(self):
        self.svc.generate(actor="alice")
        self.repos["subnet"].list_all.assert_called_once()

    def test_loads_tag_defs(self):
        self.svc.generate(actor="alice")
        self.repos["tag"].list_all.assert_called_once()


class TestGenerateResultStructure(unittest.TestCase):
    """The result dict must contain the keys the HTTP handler expects."""

    def setUp(self):
        self.svc, self.repos = _make_service()

    def test_result_has_files_key(self):
        result = self.svc.generate(actor="alice")
        self.assertIn("files", result)

    def test_result_has_findings_key(self):
        result = self.svc.generate(actor="alice")
        self.assertIn("findings", result)

    def test_result_has_summary_key(self):
        result = self.svc.generate(actor="alice")
        self.assertIn("summary", result)

    def test_files_are_yaml_strings_not_dicts(self):
        """Each value in 'files' must be a YAML-formatted string, not a dict."""
        self.repos["device"].list_all.return_value = [_make_device()]
        result = self.svc.generate(actor="alice")
        for filename, content in result["files"].items():
            with self.subTest(filename=filename):
                self.assertIsInstance(content, str)

    def test_findings_is_list(self):
        result = self.svc.generate(actor="alice")
        self.assertIsInstance(result["findings"], list)


class TestGeneratePersistsHistory(unittest.TestCase):
    """GenerateService must save a history snapshot after generation."""

    def setUp(self):
        self.svc, self.repos = _make_service()

    def test_history_repo_save_called(self):
        self.svc.generate(actor="alice")
        self.repos["history"].save.assert_called_once()

    def test_actor_passed_to_history_save(self):
        self.svc.generate(actor="carol")
        actor_arg = self.repos["history"].save.call_args[0][0]
        self.assertEqual(actor_arg, "carol")

    def test_rendered_yaml_strings_persisted_not_dicts(self):
        self.repos["device"].list_all.return_value = [_make_device()]
        self.svc.generate(actor="alice")
        files_arg = self.repos["history"].save.call_args[0][2]
        for content in files_arg.values():
            self.assertIsInstance(content, str)


class TestGenerateUpdatesMetaTimestamps(unittest.TestCase):
    """GenerateService must update lastSavedAt and lastSavedBy in meta."""

    def setUp(self):
        self.svc, self.repos = _make_service()

    def test_last_saved_at_updated(self):
        self.svc.generate(actor="alice")
        calls = self.repos["meta"].set_kv.call_args_list
        keys = [c[0][0] for c in calls]
        self.assertIn("lastSavedAt", keys)

    def test_last_saved_by_updated_with_actor(self):
        self.svc.generate(actor="dave")
        calls = self.repos["meta"].set_kv.call_args_list
        by_call = next((c for c in calls if c[0][0] == "lastSavedBy"), None)
        self.assertIsNotNone(by_call)
        self.assertEqual(by_call[0][1], "dave")

    def test_last_saved_by_unknown_when_actor_is_none(self):
        self.svc.generate(actor=None)
        calls = self.repos["meta"].set_kv.call_args_list
        by_call = next((c for c in calls if c[0][0] == "lastSavedBy"), None)
        self.assertIsNotNone(by_call)
        self.assertEqual(by_call[0][1], "unknown")


class TestGenerateWritesAuditEntry(unittest.TestCase):
    """GenerateService must log a 'generate' audit entry."""

    def setUp(self):
        self.svc, self.repos = _make_service()

    def test_audit_log_called(self):
        self.svc.generate(actor="alice")
        self.repos["audit"].log.assert_called_once()

    def test_audit_action_is_generate(self):
        self.svc.generate(actor="alice")
        action = self.repos["audit"].log.call_args[0][1]
        self.assertEqual(action, "generate")

    def test_audit_actor_forwarded(self):
        self.svc.generate(actor="eve")
        actor_arg = self.repos["audit"].log.call_args[0][0]
        self.assertEqual(actor_arg, "eve")


class TestGenerateWithRealDevice(unittest.TestCase):
    """Integration-style smoke test: a single device with full creds."""

    def test_generates_one_yaml_file_per_region(self):
        svc, repos = _make_service()
        repos["device"].list_all.return_value = [
            _make_device(ip="192.0.2.1", region="us-east"),
            _make_device(ip="192.0.2.2", region="us-east"),
            _make_device(ip="192.0.2.3", region="eu-west"),
        ]
        result = svc.generate(actor="alice")
        self.assertEqual(len(result["files"]), 2)
        self.assertIn("us_east.yaml", result["files"])
        self.assertIn("eu_west.yaml", result["files"])

    def test_empty_inventory_produces_no_files(self):
        svc, repos = _make_service()
        result = svc.generate(actor="alice")
        self.assertEqual(result["files"], {})


if __name__ == "__main__":
    unittest.main()
