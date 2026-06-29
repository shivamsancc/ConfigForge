"""
Tests for core.logging.startup — log_startup_info() and log_shutdown_info().

Covers:
- Startup log includes app version, api version, Python version
- Startup log includes provider name/dialect/version
- Startup log includes startup duration
- Startup log includes log file path when configured
- Shutdown log includes provider name
- Both functions are safe with empty/None provider_meta
- configure_logging() is idempotent (no handler stacking)
- configure_logging(None) uses defaults without error
"""
import logging
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.logging import configure_logging, get_logger
from core.logging.config import LoggingConfig
from core.logging.startup import log_shutdown_info, log_startup_info


class _RecordCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def messages(self) -> list[str]:
        return [r.getMessage() for r in self.records]


def _install_capture(logger_name: str = "configfoundry") -> _RecordCapture:
    cap = _RecordCapture()
    logging.getLogger(logger_name).addHandler(cap)
    return cap


def _remove_capture(cap: _RecordCapture, logger_name: str = "configfoundry"):
    logging.getLogger(logger_name).removeHandler(cap)


class TestLogStartupInfo(unittest.TestCase):
    def setUp(self):
        # Use a minimal console-only config so configure_logging() succeeds.
        configure_logging(LoggingConfig(console=False))
        self._cap = _install_capture()

    def tearDown(self):
        _remove_capture(self._cap)

    def test_startup_logs_app_version(self):
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={"name": "SQLiteProvider"},
        )
        self.assertTrue(
            any("0.5.0" in m for m in self._cap.messages()),
            f"App version not found. Messages: {self._cap.messages()}",
        )

    def test_startup_logs_api_version(self):
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={},
        )
        self.assertTrue(any("v1" in m for m in self._cap.messages()))

    def test_startup_logs_python_version(self):
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={},
        )
        # Should contain the running Python version
        py_version = sys.version.split()[0]
        self.assertTrue(
            any(py_version in m for m in self._cap.messages()),
            f"Python version {py_version!r} not found. Messages: {self._cap.messages()}",
        )

    def test_startup_logs_provider_name(self):
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={"name": "SQLiteProvider", "dialect": "sqlite"},
        )
        self.assertTrue(any("SQLiteProvider" in m for m in self._cap.messages()))

    def test_startup_logs_dialect(self):
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={"name": "SQLiteProvider", "dialect": "sqlite"},
        )
        self.assertTrue(any("sqlite" in m for m in self._cap.messages()))

    def test_startup_logs_duration(self):
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={},
            startup_duration_s=0.123,
        )
        self.assertTrue(
            any("0.123" in m for m in self._cap.messages()),
            f"Startup duration not found. Messages: {self._cap.messages()}",
        )

    def test_startup_logs_log_file_when_configured(self):
        cfg = LoggingConfig(file="/tmp/cf.log", rotation="size")
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={},
            log_config=cfg,
        )
        messages = self._cap.messages()
        self.assertTrue(
            any("/tmp/cf.log" in m for m in messages),
            f"Log file path not found. Messages: {messages}",
        )

    def test_startup_safe_with_empty_provider_meta(self):
        # Should not raise
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta={},
        )
        # At minimum something was logged
        self.assertGreater(len(self._cap.records), 0)

    def test_startup_safe_with_none_provider_meta(self):
        log_startup_info(
            app_version="0.5.0",
            api_version="v1",
            provider_meta=None,
        )
        self.assertGreater(len(self._cap.records), 0)


class TestLogShutdownInfo(unittest.TestCase):
    def setUp(self):
        configure_logging(LoggingConfig(console=False))
        self._cap = _install_capture()

    def tearDown(self):
        _remove_capture(self._cap)

    def test_shutdown_logs_provider_name(self):
        log_shutdown_info(provider_meta={"name": "SQLiteProvider"})
        self.assertTrue(any("SQLiteProvider" in m for m in self._cap.messages()))

    def test_shutdown_logs_shutting_down(self):
        log_shutdown_info(provider_meta={})
        self.assertTrue(
            any("shutting down" in m.lower() or "shutdown" in m.lower()
                for m in self._cap.messages())
        )

    def test_shutdown_safe_with_none_provider_meta(self):
        log_shutdown_info(provider_meta=None)
        self.assertGreater(len(self._cap.records), 0)


class TestConfigureLogging(unittest.TestCase):
    """Verify configure_logging() behaviour: idempotency, defaults, file creation."""

    def test_configure_logging_with_none_uses_defaults(self):
        # Should not raise
        configure_logging(None)
        root = logging.getLogger("configfoundry")
        self.assertIsNotNone(root)

    def test_configure_logging_idempotent_no_handler_stacking(self):
        cfg = LoggingConfig(console=True, file=None)
        configure_logging(cfg)
        handler_count_1 = len(logging.getLogger("configfoundry").handlers)
        configure_logging(cfg)
        handler_count_2 = len(logging.getLogger("configfoundry").handlers)
        self.assertEqual(
            handler_count_1, handler_count_2,
            "Handler count changed on second configure_logging() call — stacking detected",
        )

    def test_configure_logging_sets_propagate_false(self):
        configure_logging(LoggingConfig(console=False))
        root = logging.getLogger("configfoundry")
        self.assertFalse(root.propagate)

    def test_configure_logging_sets_correct_level(self):
        configure_logging(LoggingConfig(level="DEBUG", console=False))
        root = logging.getLogger("configfoundry")
        self.assertEqual(root.level, logging.DEBUG)

    def test_configure_logging_creates_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "subdir", "app.log")
            cfg = LoggingConfig(
                file=log_path,
                rotation="none",
                console=False,
            )
            configure_logging(cfg)
            logger = get_logger("test.file_creation")
            logger.info("file creation test")
            # Flush handlers
            for h in logging.getLogger("configfoundry").handlers:
                h.flush()
            self.assertTrue(
                os.path.exists(log_path),
                f"Log file was not created at {log_path}",
            )

    def test_configure_logging_console_false_adds_no_stream_handler(self):
        configure_logging(LoggingConfig(console=False, file=None))
        root = logging.getLogger("configfoundry")
        stream_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        self.assertEqual(len(stream_handlers), 0)


if __name__ == "__main__":
    unittest.main()
