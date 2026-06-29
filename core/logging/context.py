"""
Request-scoped context for the ConfigFoundry logging framework.

Uses Python's ``contextvars.ContextVar`` to propagate a Request ID through
the async call stack without passing it explicitly as a function argument.

How it works
------------
1. ``CorrelationIDMiddleware`` calls ``set_request_id(id)`` at the start of
   every HTTP request, obtaining a ``Token``.
2. All log records emitted during that request call ``get_request_id()``
   and include the ID in the ``request_id`` field.
3. After the response is sent, the middleware calls
   ``reset_request_id(token)`` to restore the previous context value
   (always ``"-"`` at the top level).

Thread safety
-------------
``contextvars.ContextVar`` is natively thread-safe and async-safe.
FastAPI runs sync route handlers in a thread pool, copying the current
asyncio context to each thread — so ``get_request_id()`` returns the
correct value inside sync handlers too, provided the middleware has set
it before the handler runs.

Audit log note
--------------
The same ContextVar mechanism is available to a future audit logger.
Import ``get_request_id()`` from this module and attach the ID to every
audit record to link audit entries back to the originating HTTP request.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

# Default value ("-") is used in log records when no request is active,
# e.g. during startup/shutdown or background tasks.
_request_id_var: ContextVar[str] = ContextVar(
    "configfoundry_request_id", default="-"
)


def get_request_id() -> str:
    """Return the current request ID, or ``"-"`` when outside a request."""
    return _request_id_var.get()


def set_request_id(request_id: str) -> Token:
    """
    Set the request ID for the current async/thread context.

    Returns a ``Token`` that must be passed to ``reset_request_id()``
    when the request is complete, to restore the previous value.
    """
    return _request_id_var.set(request_id)


def reset_request_id(token: Token) -> None:
    """
    Restore the context variable to its value before ``set_request_id()``
    was called.  Always call this in a ``finally`` block.
    """
    _request_id_var.reset(token)


def generate_request_id() -> str:
    """
    Generate a short, URL-safe, unique request identifier.

    Format: 12 lowercase hex characters (e.g. ``"a3f8c2d1e5b4"``).
    Short enough to be readable in log lines without being truncated.
    """
    return uuid.uuid4().hex[:12]
