"""
Logging configuration dataclass for ConfigFoundry.

Loaded from the ``logging:`` section of the YAML config file,
``CONFIGFORGE_LOG_*`` environment variables, or left at defaults.

YAML example
------------
::

    logging:
      level: INFO
      file: logs/configfoundry.log
      console: true
      rotation: daily        # daily | size | none
      backup_count: 7
      max_bytes: 10485760    # 10 MB (only used when rotation=size)
      json_format: false

Environment variables
---------------------
``CONFIGFORGE_LOG_LEVEL``        — DEBUG | INFO | WARNING | ERROR | CRITICAL
``CONFIGFORGE_LOG_FILE``         — path to log file (omit to log console only)
``CONFIGFORGE_LOG_CONSOLE``      — true | false
``CONFIGFORGE_LOG_JSON``         — true | false  (structured JSON output)
``CONFIGFORGE_LOG_ROTATION``     — daily | size | none
``CONFIGFORGE_LOG_BACKUP_COUNT`` — integer
``CONFIGFORGE_LOG_MAX_BYTES``    — integer (bytes, used when rotation=size)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LoggingConfig:
    """
    Configuration for the ConfigFoundry logging framework.

    Attributes
    ----------
    level:
        Minimum log level for the ``configfoundry`` logger hierarchy.
        Standard Python level names: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    file:
        Path to a log file.  ``None`` means file logging is disabled.
        Parent directories are created automatically.
    console:
        Whether to emit logs to ``stderr``.
    json_format:
        When ``True``, emit each record as a single JSON object.
        When ``False`` (default), emit human-readable text.
        Switching to JSON does not require code changes in callers —
        only this flag changes.
    rotation:
        ``"daily"``  — rotate at midnight, keep *backup_count* files.
        ``"size"``   — rotate when file exceeds *max_bytes*.
        ``"none"``   — write to the file without rotation.
    backup_count:
        How many rotated log files to keep.
    max_bytes:
        Maximum file size in bytes before rotation (``rotation="size"`` only).
    """

    level: str = "INFO"
    file: Optional[str] = None
    console: bool = True
    json_format: bool = False
    rotation: str = "daily"
    backup_count: int = 7
    max_bytes: int = 10 * 1024 * 1024  # 10 MB

    # ------------------------------------------------------------------
    # Factory class-methods
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "LoggingConfig":
        """Build a ``LoggingConfig`` from a plain dictionary."""
        known = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_env(cls) -> "LoggingConfig":
        """
        Build a ``LoggingConfig`` from ``CONFIGFORGE_LOG_*`` environment
        variables.  Missing variables fall back to dataclass defaults.
        """
        kwargs: dict = {}

        if v := os.environ.get("CONFIGFORGE_LOG_LEVEL"):
            kwargs["level"] = v.upper()
        if v := os.environ.get("CONFIGFORGE_LOG_FILE"):
            kwargs["file"] = v
        if v := os.environ.get("CONFIGFORGE_LOG_CONSOLE"):
            kwargs["console"] = v.strip().lower() in ("true", "1", "yes")
        if v := os.environ.get("CONFIGFORGE_LOG_JSON"):
            kwargs["json_format"] = v.strip().lower() in ("true", "1", "yes")
        if v := os.environ.get("CONFIGFORGE_LOG_ROTATION"):
            kwargs["rotation"] = v.lower()
        if v := os.environ.get("CONFIGFORGE_LOG_BACKUP_COUNT"):
            kwargs["backup_count"] = int(v)
        if v := os.environ.get("CONFIGFORGE_LOG_MAX_BYTES"):
            kwargs["max_bytes"] = int(v)

        return cls(**kwargs)
