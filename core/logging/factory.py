"""
Logger factory for the ConfigFoundry logging framework.

All loggers in the application must be obtained through ``get_logger()``.
No module should call ``logging.getLogger()`` directly — the factory
ensures every logger lives in the ``configfoundry`` namespace, which means:

* A single handler attached to ``configfoundry`` captures all logs.
* Log levels can be tuned per-component via the standard logger hierarchy
  (e.g. set ``configfoundry.http`` to DEBUG while ``configfoundry`` is INFO).
* Future plugins automatically participate in the same logging tree by
  calling ``get_logger(__name__)``.

Usage
-----
::

    from core.logging import get_logger

    logger = get_logger(__name__)   # recommended — uses the module name
    logger.info("Device created: %s", device_id)

    # Named loggers for cross-cutting concerns:
    logger = get_logger("configfoundry.http")
    logger = get_logger("configfoundry.lifecycle")

Logger hierarchy
----------------
::

    configfoundry                   ← root (handlers attached here)
    ├── configfoundry.http          ← RequestLoggingMiddleware
    ├── configfoundry.lifecycle     ← startup / shutdown
    ├── configfoundry.core
    │   ├── configfoundry.core.container
    │   ├── configfoundry.core.storage.providers.sqlite
    │   └── …
    └── configfoundry.api
        └── configfoundry.api.v1.router
            └── …

Audit log note
--------------
A future audit logger should live at ``configfoundry.audit`` so it can
be given a dedicated handler (a separate file or external sink) without
affecting operational logs:

    audit_logger = get_logger("configfoundry.audit")

This keeps audit records in a separate stream while reusing all
infrastructure (formatters, ContextVar, request_id injection).
"""
from __future__ import annotations

import logging

# Root namespace for all ConfigFoundry loggers.
ROOT_LOGGER_NAME = "configfoundry"


def get_logger(name: str) -> logging.Logger:
    """
    Return a ``logging.Logger`` under the ``configfoundry`` namespace.

    Parameters
    ----------
    name:
        Typically ``__name__`` from the calling module.  The factory
        prepends ``configfoundry.`` if not already present.

        Special cases:
        - ``"__main__"`` → ``"configfoundry"``
        - ``""``          → ``"configfoundry"``
        - ``"configfoundry.http"`` → unchanged (already in namespace)

    Returns
    -------
    logging.Logger
        A standard Python logger.  The same instance is returned for
        the same *name* (Python's logging module caches loggers).

    Examples
    --------
    >>> logger = get_logger(__name__)
    >>> # In core/services/device_service.py: returns
    >>> # logging.getLogger("configfoundry.core.services.device_service")
    """
    if not name or name == "__main__":
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name.startswith(ROOT_LOGGER_NAME + ".") or name == ROOT_LOGGER_NAME:
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
