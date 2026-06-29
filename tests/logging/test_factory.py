"""
Tests for core.logging.factory — get_logger() and logger hierarchy.

Covers:
- get_logger(__name__) returns a logger in the configfoundry.* namespace
- __main__ and empty string return the root configfoundry logger
- Strings already starting with "configfoundry." are not double-prefixed
- All loggers are instances of logging.Logger
- Same name always returns the same instance (Python logging module caching)
"""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.logging.factory import ROOT_LOGGER_NAME, get_logger


class TestGetLogger(unittest.TestCase):
    def test_module_name_is_prefixed(self):
        logger = get_logger("core.services.device_service")
        self.assertEqual(logger.name, "configfoundry.core.services.device_service")

    def test_dunder_main_returns_root_logger(self):
        logger = get_logger("__main__")
        self.assertEqual(logger.name, ROOT_LOGGER_NAME)

    def test_empty_string_returns_root_logger(self):
        logger = get_logger("")
        self.assertEqual(logger.name, ROOT_LOGGER_NAME)

    def test_already_namespaced_not_double_prefixed(self):
        logger = get_logger("configfoundry.http")
        self.assertEqual(logger.name, "configfoundry.http")

    def test_root_logger_name_not_double_prefixed(self):
        logger = get_logger("configfoundry")
        self.assertEqual(logger.name, "configfoundry")

    def test_returns_logging_logger_instance(self):
        logger = get_logger("some.module")
        self.assertIsInstance(logger, logging.Logger)

    def test_same_name_returns_same_instance(self):
        a = get_logger("mymodule")
        b = get_logger("mymodule")
        self.assertIs(a, b)

    def test_all_loggers_under_root_namespace(self):
        names = [
            "api.v1.devices",
            "core.container",
            "core.services.generate_service",
            "core.repositories.sqlalchemy.device",
        ]
        for name in names:
            logger = get_logger(name)
            self.assertTrue(
                logger.name.startswith(ROOT_LOGGER_NAME + "."),
                f"Expected {ROOT_LOGGER_NAME}.*, got {logger.name!r}",
            )

    def test_root_logger_name_constant(self):
        self.assertEqual(ROOT_LOGGER_NAME, "configfoundry")


class TestLoggerHierarchy(unittest.TestCase):
    """
    Verify that child loggers propagate to the root configfoundry logger.
    This is the mechanism that lets a single handler on the root capture all logs.
    """

    def test_child_propagates_to_root(self):
        child = get_logger("core.services.device_service")
        root  = logging.getLogger(ROOT_LOGGER_NAME)
        # Child must be a descendant of root (names share a prefix).
        self.assertTrue(child.name.startswith(root.name + "."))

    def test_root_logger_is_parent_of_http_logger(self):
        http_logger = get_logger("configfoundry.http")
        root_logger = logging.getLogger(ROOT_LOGGER_NAME)
        self.assertEqual(http_logger.parent, root_logger)


if __name__ == "__main__":
    unittest.main()
