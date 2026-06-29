"""
ConfigFoundry centralized logging framework.

Public API — import from here, not from sub-modules:

    from core.logging import (
        configure_logging,
        get_logger,
        get_request_id,
        set_request_id,
        reset_request_id,
        generate_request_id,
    )

Quick-start
-----------
Call ``configure_logging()`` once at application startup (in ``server.py``
before ``create_app()``).  Every module then acquires its logger with::

    from core.logging import get_logger
    logger = get_logger(__name__)

The framework guarantees:
* All loggers live under the ``configfoundry`` namespace.
* ``logging.basicConfig()`` is never called — the stdlib root logger is
  not touched.
* Log records emitted during an HTTP request automatically carry the
  correlation ID set by ``CorrelationIDMiddleware``.
* ``configure_logging()`` is idempotent — calling it multiple times
  (e.g. in tests) does not stack handlers.

Audit separation
----------------
A future audit logger should be obtained via::

    audit = get_logger("configfoundry.audit")

It automatically inherits the ContextVar-based request_id injection.
A dedicated file handler can be attached to this logger later without
changing any business-logic code:

    import logging
    logging.getLogger("configfoundry.audit").addHandler(audit_file_handler)
    logging.getLogger("configfoundry.audit").propagate = False
"""
from __future__ import annotations

import logging
from typing import Optional

from core.logging.config import LoggingConfig
from core.logging.context import (
    generate_request_id,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from core.logging.factory import ROOT_LOGGER_NAME, get_logger
from core.logging.handlers import build_console_handler, build_file_handler

# ---------------------------------------------------------------------------
# Module-level flag — prevents stacking handlers on repeated calls
# ---------------------------------------------------------------------------
_configured: bool = False


def configure_logging(config: Optional[LoggingConfig] = None) -> None:
    """
    Configure the ``configfoundry`` logger hierarchy.

    Must be called once, early in application startup (before any logger
    is used), typically from ``server.py``::

        from core.logging import configure_logging
        configure_logging(app_config.logging)

    Parameters
    ----------
    config:
        ``LoggingConfig`` instance describing level, file path, rotation,
        console output, and JSON format.  When ``None``, defaults are used
        (INFO level, console only, text format, daily rotation).

    Notes
    -----
    * **Idempotent** — a second call replaces the existing handlers rather
      than adding duplicates.  This is intentional to support test fixtures
      that reconfigure logging between test cases.
    * **Does not call** ``logging.basicConfig()`` — the stdlib root logger is
      left untouched.  Only the ``configfoundry`` hierarchy is configured.
    * ``propagate`` is set to ``False`` so records do not bubble up to the
      stdlib root logger's (possibly unconfigured) handler.
    """
    global _configured

    if config is None:
        config = LoggingConfig()

    root: logging.Logger = logging.getLogger(ROOT_LOGGER_NAME)

    # Clear existing handlers (makes this call idempotent).
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    # Set level on the root logger for this hierarchy.
    numeric_level = getattr(logging, config.level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    # Never propagate to the stdlib root logger.
    root.propagate = False

    # Attach console handler.
    if config.console:
        root.addHandler(build_console_handler(json_format=config.json_format))

    # Attach file handler (optional).
    if config.file:
        root.addHandler(
            build_file_handler(
                path=config.file,
                rotation=config.rotation,
                max_bytes=config.max_bytes,
                backup_count=config.backup_count,
                json_format=config.json_format,
            )
        )

    _configured = True


# ---------------------------------------------------------------------------
# Re-export public API
# ---------------------------------------------------------------------------
__all__ = [
    # Configuration
    "configure_logging",
    "LoggingConfig",
    # Logger factory
    "get_logger",
    # Correlation ID context
    "get_request_id",
    "set_request_id",
    "reset_request_id",
    "generate_request_id",
]
