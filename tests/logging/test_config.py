"""
Tests for core.logging.config — LoggingConfig dataclass.

Covers:
- Default values
- from_dict() with known and unknown keys
- from_env() for each CONFIGFORGE_LOG_* variable
- Boolean coercion edge cases
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.logging.config import LoggingConfig


class TestLoggingConfigDefaults(unittest.TestCase):
    def test_default_level_is_info(self):
        cfg = LoggingConfig()
        self.assertEqual(cfg.level, "INFO")

    def test_default_file_is_none(self):
        cfg = LoggingConfig()
        self.assertIsNone(cfg.file)

    def test_default_console_is_true(self):
        cfg = LoggingConfig()
        self.assertTrue(cfg.console)

    def test_default_json_format_is_false(self):
        cfg = LoggingConfig()
        self.assertFalse(cfg.json_format)

    def test_default_rotation_is_daily(self):
        cfg = LoggingConfig()
        self.assertEqual(cfg.rotation, "daily")

    def test_default_backup_count(self):
        cfg = LoggingConfig()
        self.assertEqual(cfg.backup_count, 7)

    def test_default_max_bytes(self):
        cfg = LoggingConfig()
        self.assertEqual(cfg.max_bytes, 10 * 1024 * 1024)


class TestLoggingConfigFromDict(unittest.TestCase):
    def test_known_keys_parsed(self):
        cfg = LoggingConfig.from_dict({
            "level": "DEBUG",
            "file": "/tmp/app.log",
            "console": False,
            "rotation": "size",
            "backup_count": 3,
            "max_bytes": 5_000_000,
            "json_format": True,
        })
        self.assertEqual(cfg.level, "DEBUG")
        self.assertEqual(cfg.file, "/tmp/app.log")
        self.assertFalse(cfg.console)
        self.assertEqual(cfg.rotation, "size")
        self.assertEqual(cfg.backup_count, 3)
        self.assertEqual(cfg.max_bytes, 5_000_000)
        self.assertTrue(cfg.json_format)

    def test_unknown_keys_silently_ignored(self):
        cfg = LoggingConfig.from_dict({"level": "WARNING", "unknown_future_key": 99})
        self.assertEqual(cfg.level, "WARNING")

    def test_empty_dict_returns_defaults(self):
        cfg = LoggingConfig.from_dict({})
        self.assertEqual(cfg.level, "INFO")

    def test_partial_dict_keeps_defaults_for_missing(self):
        cfg = LoggingConfig.from_dict({"level": "ERROR"})
        self.assertEqual(cfg.level, "ERROR")
        self.assertIsNone(cfg.file)
        self.assertTrue(cfg.console)


class TestLoggingConfigFromEnv(unittest.TestCase):
    def _set_env(self, **kwargs):
        for k, v in kwargs.items():
            os.environ[k] = str(v)

    def _clear_env(self, *keys):
        for k in keys:
            os.environ.pop(k, None)

    def tearDown(self):
        for key in [
            "CONFIGFORGE_LOG_LEVEL", "CONFIGFORGE_LOG_FILE",
            "CONFIGFORGE_LOG_CONSOLE", "CONFIGFORGE_LOG_JSON",
            "CONFIGFORGE_LOG_ROTATION", "CONFIGFORGE_LOG_BACKUP_COUNT",
            "CONFIGFORGE_LOG_MAX_BYTES",
        ]:
            os.environ.pop(key, None)

    def test_empty_env_returns_defaults(self):
        cfg = LoggingConfig.from_env()
        self.assertEqual(cfg.level, "INFO")
        self.assertIsNone(cfg.file)
        self.assertTrue(cfg.console)

    def test_level_from_env(self):
        self._set_env(CONFIGFORGE_LOG_LEVEL="debug")
        cfg = LoggingConfig.from_env()
        self.assertEqual(cfg.level, "DEBUG")   # uppercased

    def test_file_from_env(self):
        self._set_env(CONFIGFORGE_LOG_FILE="/var/log/cf.log")
        cfg = LoggingConfig.from_env()
        self.assertEqual(cfg.file, "/var/log/cf.log")

    def test_console_false_from_env(self):
        self._set_env(CONFIGFORGE_LOG_CONSOLE="false")
        cfg = LoggingConfig.from_env()
        self.assertFalse(cfg.console)

    def test_console_true_variants(self):
        for val in ("true", "1", "yes", "True", "YES"):
            self._set_env(CONFIGFORGE_LOG_CONSOLE=val)
            cfg = LoggingConfig.from_env()
            self.assertTrue(cfg.console, f"Expected True for CONFIGFORGE_LOG_CONSOLE={val!r}")

    def test_json_format_from_env(self):
        self._set_env(CONFIGFORGE_LOG_JSON="true")
        cfg = LoggingConfig.from_env()
        self.assertTrue(cfg.json_format)

    def test_rotation_from_env(self):
        self._set_env(CONFIGFORGE_LOG_ROTATION="size")
        cfg = LoggingConfig.from_env()
        self.assertEqual(cfg.rotation, "size")

    def test_backup_count_from_env(self):
        self._set_env(CONFIGFORGE_LOG_BACKUP_COUNT="14")
        cfg = LoggingConfig.from_env()
        self.assertEqual(cfg.backup_count, 14)

    def test_max_bytes_from_env(self):
        self._set_env(CONFIGFORGE_LOG_MAX_BYTES="52428800")
        cfg = LoggingConfig.from_env()
        self.assertEqual(cfg.max_bytes, 52428800)


if __name__ == "__main__":
    unittest.main()
