# Centralized Logging Framework

ConfigFoundry v0.5 ships a self-contained logging framework in `core/logging/`.
Every component of the application — FastAPI routes, services, repositories, middleware — logs through a single root logger named `configfoundry`, so all records can be captured, formatted, and rotated from one place.

---

## At a glance

```
core/logging/
  __init__.py      # Public API: configure_logging(), get_logger(), ...
  config.py        # LoggingConfig dataclass (YAML / env / defaults)
  context.py       # ContextVar-based request ID propagation
  factory.py       # get_logger(__name__)  →  configfoundry.* namespace
  formatters.py    # ConfigFoundryFormatter (text) + JSONFormatter
  handlers.py      # build_console_handler(), build_file_handler()
  middleware.py    # CorrelationIDMiddleware + RequestLoggingMiddleware
  startup.py       # log_startup_info(), log_shutdown_info()
```

---

## Configuration

### YAML config file

```yaml
# config.yaml
database:
  provider: sqlite
  sqlite_path: db/configforge.db

logging:
  level: INFO                       # DEBUG | INFO | WARNING | ERROR | CRITICAL
  file: logs/configfoundry.log      # omit to log console only
  console: true                     # write to stderr
  json_format: false                # true for structured JSON lines
  rotation: daily                   # daily | size | none
  backup_count: 7                   # rotated files to keep
  max_bytes: 10485760               # used only when rotation=size (10 MB)
```

```bash
python3 server.py --config config.yaml
```

### Environment variables

All logging options can also be set via `CONFIGFORGE_LOG_*` variables, which take precedence over YAML defaults:

| Variable | Default | Description |
|---|---|---|
| `CONFIGFORGE_LOG_LEVEL` | `INFO` | Minimum log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `CONFIGFORGE_LOG_FILE` | — | Log file path; omit for console-only |
| `CONFIGFORGE_LOG_CONSOLE` | `true` | Write to stderr (`true`/`false`) |
| `CONFIGFORGE_LOG_JSON` | `false` | Emit JSON lines instead of text |
| `CONFIGFORGE_LOG_ROTATION` | `daily` | `daily`, `size`, or `none` |
| `CONFIGFORGE_LOG_BACKUP_COUNT` | `7` | Number of rotated files to keep |
| `CONFIGFORGE_LOG_MAX_BYTES` | `10485760` | Max file size before rotation (`rotation=size`) |

Example:

```bash
CONFIGFORGE_LOG_LEVEL=DEBUG \
CONFIGFORGE_LOG_FILE=logs/configfoundry.log \
CONFIGFORGE_LOG_ROTATION=daily \
python3 server.py
```

---

## Log format

### Text (default)

```
2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] ConfigFoundry v0.5.0 starting up
2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] API version  : v1  (prefix: /api/v1)
2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Python       : 3.11.7
2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Storage      : SQLiteProvider v1.0.0 (dialect: sqlite)
2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Log file     : logs/configfoundry.log (rotation: daily)
2024-01-15 10:30:44 INFO     configfoundry.lifecycle            [-] Startup time : 0.142s
2024-01-15 10:30:45 INFO     configfoundry.http                 [a3f8c2d1e5b4] GET /api/v1/devices → 200 (12.3ms) ip=127.0.0.1
2024-01-15 10:30:45 INFO     configfoundry.http                 [b7d1f4a2c3e9] POST /api/v1/devices → 200 (8.1ms) ip=127.0.0.1
```

The bracketed value (`[a3f8c2d1e5b4]`) is the correlation ID. It is `[-]` for records emitted outside an HTTP request (startup, shutdown, background tasks).

### JSON (`json_format: true`)

```json
{"ts": "2024-01-15 10:30:45", "level": "INFO", "logger": "configfoundry.http", "module": "middleware", "line": 89, "request_id": "a3f8c2d1e5b4", "message": "GET /api/v1/devices → 200 (12.3ms) ip=127.0.0.1"}
```

One JSON object per line, ingestible by Elasticsearch, Loki, CloudWatch, Datadog, etc.

---

## Logger hierarchy

```
configfoundry                       ← root (handlers attached here)
├── configfoundry.http              ← RequestLoggingMiddleware
├── configfoundry.lifecycle         ← startup / shutdown
├── configfoundry.core
│   ├── configfoundry.core.container
│   ├── configfoundry.core.storage.providers.sqlite
│   └── …
└── configfoundry.api
    └── configfoundry.api.v1.router
        └── …
```

A single handler on the `configfoundry` root captures every record from any descendant. Setting `configfoundry.propagate = False` (done automatically by `configure_logging()`) ensures records never reach the stdlib root logger.

---

## Using the logger in your code

```python
from core.logging import get_logger

logger = get_logger(__name__)   # always pass __name__

logger.debug("Checking device %s", device_id)
logger.info("Device created: %s", device_id)
logger.warning("Validation failed: %r", errors)
logger.error("Unexpected failure", exc_info=True)   # includes full traceback
```

`get_logger(__name__)` in `core/services/device_service.py` returns:

```
logging.getLogger("configfoundry.core.services.device_service")
```

**Never call `logging.getLogger()` directly.** Always import `get_logger` from `core.logging`. This guarantees every logger lives in the `configfoundry` namespace.

---

## Correlation IDs

Every HTTP request is assigned a 12-character hex correlation ID (e.g. `a3f8c2d1e5b4`). The ID is stored in a `contextvars.ContextVar` so it propagates through the entire call stack — async handlers, sync handlers running in thread pools, and any intermediate awaits — without being passed as a function argument.

The ID is:

- Generated by `CorrelationIDMiddleware` if absent from the request.
- Taken from the `X-Request-ID` request header if present (useful for tracing across service boundaries).
- Added to every `X-Request-ID` response header so callers can correlate their own logs.
- Injected into every log record automatically by `ConfigFoundryFormatter` and `JSONFormatter`.

To read the current request ID in your code:

```python
from core.logging import get_request_id

def some_function():
    rid = get_request_id()   # "-" outside a request
```

---

## Middleware setup

The middleware is registered in `app.py`. Starlette prepends middleware, so the last-registered runs first. The required registration order is:

```python
# app.py — correct order
app.add_middleware(RequestLoggingMiddleware)   # added first → runs second
app.add_middleware(CorrelationIDMiddleware)    # added last  → runs first
```

`CorrelationIDMiddleware` must run first to set the `ContextVar` before `RequestLoggingMiddleware` logs the request. Reversing the order would log `[-]` instead of the real correlation ID.

### What RequestLoggingMiddleware logs

```
GET /api/v1/devices → 200 (12.3ms) ip=127.0.0.1
```

| Field | Source |
|---|---|
| Method | `request.method` |
| Path | `request.url.path` (no query string) |
| Status | `response.status_code` |
| Duration | `time.perf_counter()` delta |
| IP | `X-Forwarded-For` header (first value) or `request.client.host` |

**Never logged:** request body, response body, query string parameters, authorization headers. If you need to log query parameters for debugging, do it inside the route handler with explicit redaction applied first.

---

## Exception logging

Unhandled exceptions are caught by the global exception handler in `app.py` and logged with full traceback — the client receives only a sanitized JSON response:

```python
# What the client sees:
{"error": "division by zero", "type": "ZeroDivisionError"}

# What the server logs (with exc_info=True):
2024-01-15 10:30:46 ERROR    configfoundry.app                  [a3f8c2d1e5b4] Unhandled ZeroDivisionError on GET /api/v1/devices
Traceback (most recent call last):
  ...
ZeroDivisionError: division by zero
```

The correlation ID on the exception record lets you find the exact request in the access log.

---

## Startup and shutdown logging

`log_startup_info()` and `log_shutdown_info()` are called from the FastAPI lifespan context manager and emit a structured summary:

**Startup:**
```
ConfigFoundry v0.5.0 starting up
API version  : v1  (prefix: /api/v1)
Python       : 3.11.7
Storage      : SQLiteProvider v1.0.0 (dialect: sqlite)
Log file     : logs/configfoundry.log (rotation: daily)
Startup time : 0.142s
```

**Shutdown:**
```
ConfigFoundry shutting down
Closing storage provider: SQLiteProvider
Shutdown complete
```

These records appear on the `configfoundry.lifecycle` logger, so they can be filtered separately if needed.

---

## Log rotation

| Mode | Handler | Behaviour |
|---|---|---|
| `daily` | `TimedRotatingFileHandler(when="midnight")` | Rotate at midnight; keep `backup_count` files |
| `size` | `RotatingFileHandler(maxBytes=max_bytes)` | Rotate when file exceeds `max_bytes`; keep `backup_count` |
| `none` | `FileHandler` | No rotation; use for development or short-lived jobs |

Parent directories are created automatically. There is no mode that allows unlimited log growth — the default `daily` rotation with `backup_count=7` caps total disk usage at roughly 7 × (daily write volume).

---

## Audit log (future)

The framework is designed for audit-log separation. When you're ready to add audit logging:

1. Obtain the audit logger:
   ```python
   audit = get_logger("configfoundry.audit")
   ```

2. Add a dedicated handler:
   ```python
   import logging
   audit_logger = logging.getLogger("configfoundry.audit")
   audit_logger.addHandler(build_file_handler("logs/audit.log", rotation="daily"))
   audit_logger.propagate = False   # don't also write to the main log
   ```

3. The `request_id` ContextVar is automatically available — every audit record written during an HTTP request carries the correlation ID without any extra code.

No code changes are needed in services or repositories; the infrastructure is already in place.

---

## Adding a new log destination

To add a new handler type (e.g. a remote syslog server, Datadog agent, or email alerter on ERROR):

1. Build the handler using stdlib `logging.handlers` or a third-party library.
2. Attach a `ConfigFoundryFormatter` or `JSONFormatter` so the `request_id` field is included.
3. Add it to `logging.getLogger("configfoundry")` either in `configure_logging()` (for always-on destinations) or at startup in `server.py` (for environment-specific sinks).

---

## Testing with logging

In tests, `configure_logging()` is not called (no `server.py` entrypoint runs). Loggers still work — they just have no handlers, so records are silently discarded. This is correct: tests should not write to disk or produce console noise unless you're specifically testing logging behaviour.

For tests that need to assert on log output, attach a capturing handler to the relevant logger:

```python
import logging

class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
    def emit(self, record):
        self.records.append(record)

cap = Capture()
logging.getLogger("configfoundry").addHandler(cap)
# ... run the code under test ...
logging.getLogger("configfoundry").removeHandler(cap)

messages = [r.getMessage() for r in cap.records]
assert any("device created" in m.lower() for m in messages)
```

See `tests/logging/` for complete examples.

---

## Quick reference

| What | Where |
|---|---|
| Public API | `core/logging/__init__.py` |
| Configuration | `core/logging/config.py` |
| Request ID context | `core/logging/context.py` |
| Logger factory | `core/logging/factory.py` |
| Formatters (text + JSON) | `core/logging/formatters.py` |
| Handler builders | `core/logging/handlers.py` |
| HTTP middleware | `core/logging/middleware.py` |
| Startup / shutdown | `core/logging/startup.py` |
| Tests | `tests/logging/` |
| This document | `docs/logging.md` |
