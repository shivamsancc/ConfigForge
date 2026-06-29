"""
Log handler builders for the ConfigFoundry logging framework.

This module creates and configures ``logging.Handler`` instances based on a
``LoggingConfig``.  No other module should construct handlers directly —
all handler creation goes through ``build_console_handler()`` or
``build_file_handler()``.

Handler types
-------------
Console handler
    Always a plain ``logging.StreamHandler`` writing to ``stderr``.
    No rotation — the process manager (systemd, Docker, etc.) handles
    console log capture and rotation.

File handler — ``rotation="daily"``
    ``logging.handlers.TimedRotatingFileHandler`` rotating at midnight.
    Keeps *backup_count* historical files named
    ``<name>.log.2024-01-14``, etc.

File handler — ``rotation="size"``
    ``logging.handlers.RotatingFileHandler`` rotating once the file
    exceeds *max_bytes*.  Keeps *backup_count* backup files named
    ``<name>.log.1``, ``<name>.log.2``, etc.

File handler — ``rotation="none"``
    Plain ``logging.FileHandler`` with no rotation.  Suitable for
    development, short-lived jobs, or when the OS handles rotation.

Adding a new handler type
--------------------------
1. Add a constant to ``_ROTATION_*`` or a new branch to ``build_file_handler``.
2. Update ``LoggingConfig.rotation`` docstring with the new value.
3. Add a test in ``tests/logging/test_handlers.py``.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from typing import Optional

from core.logging.formatters import (
    ConfigFoundryFormatter,
    DATE_FORMAT,
    JSONFormatter,
    TEXT_FORMAT,
)

_ROTATION_DAILY = "daily"
_ROTATION_SIZE  = "size"
_ROTATION_NONE  = "none"


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _make_formatter(json_format: bool) -> logging.Formatter:
    """Return the correct formatter based on the config flag."""
    if json_format:
        return JSONFormatter()
    return ConfigFoundryFormatter(fmt=TEXT_FORMAT, datefmt=DATE_FORMAT)


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_console_handler(json_format: bool = False) -> logging.StreamHandler:
    """
    Build a console (stderr) log handler.

    Parameters
    ----------
    json_format:
        When ``True``, use ``JSONFormatter``; otherwise ``ConfigFoundryFormatter``.

    Returns
    -------
    logging.StreamHandler
        Configured, ready to attach to the ``configfoundry`` logger.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_make_formatter(json_format))
    return handler


def build_file_handler(
    path: str,
    rotation: str = _ROTATION_DAILY,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 7,
    json_format: bool = False,
) -> logging.FileHandler:
    """
    Build a file log handler with optional rotation.

    Parent directories are created automatically if they do not exist.

    Parameters
    ----------
    path:
        Absolute or relative path to the log file.
    rotation:
        ``"daily"``  — rotate at midnight, keep *backup_count* archives.
        ``"size"``   — rotate once file exceeds *max_bytes*.
        ``"none"``   — never rotate.
    max_bytes:
        Used only when ``rotation="size"``.
    backup_count:
        Number of historical log files to retain (used by ``"daily"`` and
        ``"size"`` rotation).
    json_format:
        When ``True``, emit JSON instead of human-readable text.

    Returns
    -------
    logging.FileHandler
        A configured file handler ready to attach to the root logger.

    Raises
    ------
    ValueError
        If *rotation* is not one of ``"daily"``, ``"size"``, ``"none"``.
    OSError
        If the log directory cannot be created (permission error, etc.).
    """
    # Ensure parent directory exists.
    log_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(log_dir, exist_ok=True)

    formatter = _make_formatter(json_format)

    if rotation == _ROTATION_DAILY:
        handler: logging.FileHandler = logging.handlers.TimedRotatingFileHandler(
            filename=path,
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
            utc=False,
        )
    elif rotation == _ROTATION_SIZE:
        handler = logging.handlers.RotatingFileHandler(
            filename=path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    elif rotation == _ROTATION_NONE:
        handler = logging.FileHandler(filename=path, encoding="utf-8")
    else:
        raise ValueError(
            f"Unknown rotation value {rotation!r}. "
            f"Expected one of: 'daily', 'size', 'none'."
        )

    handler.setFormatter(formatter)
    return handler
