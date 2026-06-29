"""
HTTP middleware for the ConfigFoundry logging framework.

Two middleware classes are provided:

``CorrelationIDMiddleware``
    Outermost middleware — must be added LAST with ``app.add_middleware()``.
    Generates or extracts the ``X-Request-ID`` header, writes the value
    into the ``ContextVar``, and adds the header to the response.

``RequestLoggingMiddleware``
    Added FIRST with ``app.add_middleware()`` (runs second, after the
    correlation ID is already set).  Logs method, path, status code,
    duration, and client IP.  Never logs request bodies or credentials.

Starlette middleware ordering note
-----------------------------------
``app.add_middleware(A)`` then ``app.add_middleware(B)`` means requests flow
``B → A → handler``.  To ensure CorrelationID runs before RequestLogging,
register them in the following order in ``app.py``::

    app.add_middleware(RequestLoggingMiddleware)   # added first → runs second
    app.add_middleware(CorrelationIDMiddleware)    # added last  → runs first

Security notes
--------------
* ``X-Request-ID`` from untrusted clients is accepted as-is (useful for
  tracing across service boundaries) but is not validated beyond being a
  non-empty string.  Internal IDs are 12 hex chars; client-supplied values
  may be longer but are capped at 128 chars to prevent log injection.
* Request bodies are never logged — only method, path (without query
  string by default), status, duration, and client IP.
* Sensitive paths (e.g. ``/api/v1/auth/token``) should be excluded at the
  middleware level by checking ``request.url.path`` — extend
  ``RequestLoggingMiddleware`` with a ``skip_paths`` argument if needed.
"""
from __future__ import annotations

import time
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.logging.context import (
    generate_request_id,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from core.logging.factory import get_logger

_REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LEN = 128   # guard against log-injection via oversized header

_http_logger = get_logger("configfoundry.http")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Assign a request ID to every inbound HTTP request.

    Behaviour
    ---------
    * If the request carries an ``X-Request-ID`` header, that value is used
      (truncated to 128 chars).
    * Otherwise, a 12-character hex ID is generated via ``generate_request_id()``.
    * The ID is stored in ``ContextVar`` for the duration of the request so
      all log records emitted during processing carry it automatically.
    * The ID is also written to the ``X-Request-ID`` response header so
      callers can correlate their own logs with server-side logs.

    Registration
    ------------
    Must be added LAST in ``app.py`` so it runs first::

        app.add_middleware(RequestLoggingMiddleware)
        app.add_middleware(CorrelationIDMiddleware)   # ← add last, runs first
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        raw = request.headers.get(_REQUEST_ID_HEADER, "")
        request_id = (raw.strip()[:_MAX_REQUEST_ID_LEN] if raw.strip()
                      else generate_request_id())

        token = set_request_id(request_id)
        try:
            response: Response = await call_next(request)
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            reset_request_id(token)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log every HTTP request: method, path, status code, duration, and IP.

    Log format
    ----------
    ::

        GET /api/v1/devices → 200 (12.3ms) ip=127.0.0.1

    What is NOT logged
    ------------------
    * Request or response bodies
    * Query string parameters (may contain credentials)
    * Request headers (may contain auth tokens)

    If you need to log query parameters for debugging, add an explicit
    ``logger.debug(str(request.query_params))`` inside the route handler
    where you can apply business-logic redaction first.

    Registration
    ------------
    Add FIRST in ``app.py`` so it runs second (after CorrelationID)::

        app.add_middleware(RequestLoggingMiddleware)   # ← add first, runs second
        app.add_middleware(CorrelationIDMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        t_start = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms = (time.perf_counter() - t_start) * 1000
        client_ip = _get_client_ip(request)

        _http_logger.info(
            "%s %s → %d (%.1fms) ip=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_ip,
        )

        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """
    Extract the real client IP, honouring the ``X-Forwarded-For`` header
    set by reverse proxies (nginx, ALB, Cloudflare, etc.).

    Only the first (leftmost) value in ``X-Forwarded-For`` is used, as
    that is the originating client address.  Subsequent values are
    intermediate proxies.

    Falls back to ``request.client.host`` when the header is absent.
    """
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "-"
