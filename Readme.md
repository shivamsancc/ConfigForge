<p align="center">
  <img src="/static/logo.svg" alt="ConfigForge" width="100%">
</p>

<p align="center">
  <a href="https://github.com/shivamsancc/ConfigForge"><img alt="repo" src="https://img.shields.io/badge/github-shivamsancc%2FConfigForge-181717?logo=github"></a>
  <img alt="status" src="https://img.shields.io/badge/status-active-brightgreen">
  <img alt="python" src="https://img.shields.io/badge/python-3.12%2B-blue">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-lightgrey">
</p>

<p align="center">
  A shared, self-hosted tool for generating Datadog SNMP/ICMP collector config YAML
  from a team-maintained inventory of network devices, bandwidth caps, and subnets.
</p>

---

## Why this exists

Network teams often track device inventory in a spreadsheet and hand-roll monitoring
config from it. ConfigForge replaces that with a small shared web server: one person
runs it on an always-on machine, and everyone on the team opens it in a browser to
manage the same dataset together &mdash; no per-person spreadsheet copies, no merge
conflicts, no "whose version is current?"

What you get instead of a spreadsheet: multi-user access from one shared dataset,
input validation (IP/CIDR format, credential fields), an audit log of who changed
what, and YAML generation that's always derived from current data instead of
copy-pasted by hand. What you give up: there's no offline editing without the
server running, and if your team lives in pivot tables and conditional formatting,
this won't replace that workflow &mdash; it replaces the "this is also our source of
truth for monitoring config" part of it.

## Getting Started

### Requirements

- Python 3.12+
- pip packages listed in `requirements.txt` (FastAPI, SQLAlchemy 2.x, Pydantic v2, uvicorn, httpx)

### Installation

```bash
git clone https://github.com/shivamsancc/ConfigForge.git
cd ConfigForge
pip install -r requirements.txt
```

### Start the server

```bash
python3 server.py
```

Starts on **`http://localhost:8420/`**, creates `db/configforge.db` automatically, and opens your default browser. Press `Ctrl+C` to stop.

### Custom database path

```bash
python3 server.py --db /path/to/shared/configforge.db
```

Point multiple team members at the same file on a shared drive so everyone works from the same dataset.

### Custom host and port

```bash
python3 server.py --host 0.0.0.0 --port 9000 --no-browser
```

Default host is `0.0.0.0` (all interfaces). Default port is `8420`.

### All CLI options

```
python3 server.py --help

  --db PATH         Path to SQLite database file (default: db/configforge.db)
  --config FILE     Path to a YAML config file (enables PostgreSQL/MySQL/etc.)
  --port PORT       Port to listen on (default: 8420)
  --host HOST       Interface to bind (default: 0.0.0.0)
  --no-browser      Don't open a browser tab on startup
```

### Development mode (auto-reload)

`server.py` does not pass `--reload` to uvicorn. For live reload during development, create a one-line shim and run uvicorn directly:

```python
# dev.py
from app import create_app
app = create_app(db_path="db/dev.db")
```

```bash
uvicorn dev:app --reload --port 8420
```

Any change to a `.py` file triggers an automatic restart.

### First run walkthrough

From the empty dashboard, three steps to your first generated file:

1. **Manage Lists** &rarr; add a Collector Region (e.g. `aws-mumbai`).
2. **Devices** &rarr; add a device, assign it that Collector Region.
3. **Generate YAML** &rarr; click Generate. You now have a YAML file derived from that device.

### API explorer (Swagger UI)

FastAPI generates interactive API documentation automatically:

| URL | Description |
|-----|-------------|
| `http://localhost:8420/docs` | Swagger UI — try every endpoint in the browser |
| `http://localhost:8420/redoc` | ReDoc — alternative read-only reference |

### Environment variables

All database settings can be provided via environment variables instead of CLI flags or a YAML file. Each uses the `CONFIGFORGE_DB_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIGFORGE_DB_PROVIDER` | `sqlite` | Storage backend (`sqlite`, `postgresql`, `mysql`, `sqlserver`) |
| `CONFIGFORGE_DB_SQLITE_PATH` | `db/configforge.db` | Path to SQLite file (or `:memory:`) |
| `CONFIGFORGE_DB_CONNECTION_URL` | — | Full SQLAlchemy URL for non-SQLite backends |
| `CONFIGFORGE_DB_POOL_SIZE` | `5` | Connection pool size |
| `CONFIGFORGE_DB_MAX_OVERFLOW` | `10` | Max connections above pool size |
| `CONFIGFORGE_DB_ECHO` | `false` | Log all SQL statements (`true`/`false`) |

Logging is configured separately with `CONFIGFORGE_LOG_*` variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIGFORGE_LOG_LEVEL` | `INFO` | Minimum log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `CONFIGFORGE_LOG_FILE` | — | Log file path; omit for console-only |
| `CONFIGFORGE_LOG_CONSOLE` | `true` | Write to stderr (`true`/`false`) |
| `CONFIGFORGE_LOG_JSON` | `false` | Emit JSON lines instead of human-readable text |
| `CONFIGFORGE_LOG_ROTATION` | `daily` | `daily`, `size`, or `none` |
| `CONFIGFORGE_LOG_BACKUP_COUNT` | `7` | Number of rotated files to keep |
| `CONFIGFORGE_LOG_MAX_BYTES` | `10485760` | Max file size before rotation (rotation=size only) |

Environment variables are read by `AppConfig.from_env()`. To use them with the server, set them before starting:

```bash
CONFIGFORGE_DB_SQLITE_PATH=/mnt/shared/configforge.db \
CONFIGFORGE_LOG_FILE=logs/configfoundry.log \
CONFIGFORGE_LOG_LEVEL=DEBUG \
python3 server.py
```

### YAML config file (advanced)

For non-SQLite backends or to version-control your deployment config, pass a YAML file with `--config`:

```yaml
# config.yaml
database:
  provider: postgresql
  connection_url: "postgresql+psycopg2://user:pass@db-host:5432/configforge"
  pool_size: 10
  max_overflow: 20
  echo: false

logging:
  level: INFO
  file: logs/configfoundry.log
  console: true
  rotation: daily         # daily | size | none
  backup_count: 7
  json_format: false      # true to emit JSON lines for log aggregators
```

```bash
python3 server.py --config /etc/configfoundry/config.yaml --port 8420
```

If `--db` is also supplied alongside `--config`, it overrides `sqlite_path` in the YAML. Passwords in connection URLs are masked in console output.

See [`docs/storage-architecture.md`](docs/storage-architecture.md) for the full storage config reference and a guide to adding new database backends. See [`docs/logging.md`](docs/logging.md) for the full logging reference.

### Production startup

For production, bypass `server.py` and run uvicorn directly with multiple workers:

```bash
# Create a module-level app instance first (e.g. wsgi.py):
# from app import create_app
# from core.storage.config import AppConfig
# app = create_app(config=AppConfig.from_env())

uvicorn wsgi:app \
  --host 0.0.0.0 \
  --port 8420 \
  --workers 4 \
  --log-level warning \
  --no-access-log
```

Or with gunicorn and the uvicorn worker class:

```bash
gunicorn wsgi:app \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8420 \
  --workers 4
```

Put a reverse proxy (nginx, Caddy, Traefik) in front for TLS termination, rate limiting, and access control.

## Features

> A screenshot of the Dashboard and the Network Tree belongs here. Neither is in
> this revision yet &mdash; treat the descriptions below as unverified until you've
> run it yourself.

### Inventory management

- **Devices, Bandwidth Capping, and Subnets** &mdash; full CRUD for your inventory,
  with both a sortable table view and a card view, instant client-side search,
  pagination (10/25/50/100/All rows, with your preference remembered), and a
  responsive layout down to mobile. Click any column header to sort &mdash; click
  again to reverse. All of this runs entirely in the browser, so it works exactly
  the same whether the server is on your LAN or unreachable.
- **Generate YAML** &mdash; one config file per Collector Region, built from your
  current devices and bandwidth caps, with live preview and download. Devices
  configured for ICMP or SNMP Trap automatically hide the SNMPv3 credential form
  entirely, live, as you change the Config Type &mdash; since they don't need it.
- **IP address validation** &mdash; both client-side (instant feedback while
  typing) and server-side (so a bad value can't sneak in through the API directly).
  Rows with an invalid IP or CIDR are skipped during import with a clear count
  rather than silently corrupting your data.
- **Excel import/export** &mdash; export your current data as an `.xlsx` template
  (including your custom tag columns), edit it offline, and re-import with a merge
  or replace mode. Credential column headers are alias-tolerant (`Auth Key`,
  `authKey`, `AuthKey` all map to the same field).

### Dynamic tags

- **Collector Region is the one fixed concept** &mdash; mandatory, and it's what
  Generate YAML groups files by. Everything else &mdash; Device Class, Region,
  Environment, Country, or anything you invent &mdash; is created on demand
  through **Manage Tags**, not hardcoded. A tag only exists once you create it.
- **One tag, many sections** &mdash; a tag can apply to Devices, Bandwidth
  Capping, and Subnets all at once, sharing a single value list across every
  section it's enabled for. Define "Environment" once, use it everywhere. Tag
  *creation* happens on **Manage Tags**; every tag's *value list* (alongside
  Collector Region's) lives on **Manage Lists**, so there's one place to curate
  every dropdown's options.
- **Tags render as real columns** &mdash; each tag shows up as its own column in
  every table (header = tag name, cell = value or empty), not packed into one
  generic "Tags" column.
- **Subnet-based tag inheritance** &mdash; tag a subnet once by CIDR instead of
  tagging every device in it individually. Any device whose IP falls inside that
  range inherits the tag for any value it doesn't already set itself, and the
  matched subnet is written into the generated YAML (`subnet: 10.1.1.0/24`) so
  it's traceable from the output alone.
- **Deleting something in use asks first.** Removing a tag, a tag value, or a
  Collector Region that's still referenced warns you with the affected record
  count before letting you proceed, and deleting a tag definition never deletes
  the records that used it &mdash; only the tag reference on them. (Same rule
  applies to the `DELETE /api/tags/{id}` endpoint &mdash; see REST API below.)

### Network Tree

Browsing hundreds of devices as a flat table makes it hard to see how your
network is actually laid out. The Network Tree is a spatial diagram instead:
Subnets on the left, branching to the Devices inside each one, branching to
that device's Bandwidth Capping rows on the right &mdash; built so you can pan
and zoom around a few hundred devices without losing your place.

- **Pan and zoom, Google-Maps style**, with independent scrolling per column so
  a bucket with hundreds of devices doesn't make the whole diagram unusably
  tall.
- **Click a card to drill in** (subnet &rarr; its devices &rarr; their
  bandwidth rows); click the already-selected card again for a details panel
  with an **Edit** button that opens the same form used everywhere else in the
  app. Editing from the diagram updates your data immediately.
- **Hover to trace a connection** &mdash; highlights the connector lines down
  to everything beneath the card you're hovering, so you can see at a glance
  what belongs to what.
- **Unassigned buckets** for devices with no matching subnet and bandwidth rows
  with no matching device, instead of either disappearing silently.
- **Filter with `key:value` queries** (`collector_region:india`,
  `country:"AWS US"` &mdash; quote multi-word values) or the dropdowns next to
  the filter bar. Filtering narrows what's shown; it never changes the
  diagram's shape.

### Everything else

- **Dashboard** &mdash; inventory totals with icon-bearing stat cards, breakdowns
  by Collector Region and any custom tag (correctly accounting for
  subnet-inherited values, not just directly-stored ones), generation status, and
  a recent-activity feed.
- **Dark and light mode** &mdash; toggle in the top bar, remembered in your
  browser, applied before the page even paints so there's no flash of the wrong
  theme.
- **Audit log + YAML history** &mdash; every change is attributed to whoever made
  it (a one-time name prompt, required and remembered permanently in your
  browser, not a login system), and every generation is saved so you can look
  back at what was produced and when.
- **Minimal, well-known dependencies.** The backend runs on FastAPI, SQLAlchemy 2.x, Pydantic v2, and uvicorn — all installable with a single `pip install -r requirements.txt`. AES-256-GCM credential encryption and the YAML serializer remain pure-Python with no additional dependencies.
- **Safe upgrades.** Every schema change ships as a versioned, idempotent
  migration that runs automatically on server startup (see
  [Upgrading](#upgrading) below) &mdash; updating to a new version is just
  "copy in the new files, restart."

## Limitations and non-goals

Things ConfigForge deliberately does not try to be, so you can decide quickly
whether it fits:

- **Not a CMDB.** It tracks the fields needed to generate monitoring config
  (IP, region, credentials, a handful of tags) &mdash; it doesn't model
  ownership, lifecycle, warranty, or asset relationships beyond
  subnet/device/bandwidth.
- **No RBAC.** Anyone who can reach the server can read and write everything.
  The "editor name" prompt is for audit-log attribution, not access control.
- **No authentication on the API.** Same caveat as the credentials section
  below &mdash; if you need real access control, put this behind a reverse
  proxy or VPN.
- **Single shared SQLite file, no locking beyond SQLite's own WAL mode.**
  Two people editing the same record at the same moment: last write wins,
  there's no optimistic-locking or conflict warning. For the team-sized usage
  this was built for (a handful of people maintaining a shared inventory,
  not editing the same device simultaneously) this hasn't been a problem in
  practice, but it's not battle-tested under heavy concurrent write load and
  you should know that going in.
- **Test suite covers the backend only.** The `tests/` directory contains 447 passing tests across repositories, services, handlers, the storage abstraction layer, and the logging framework. Frontend behaviour is still verified by hand against a real browser.

## Upgrading

Updating ConfigForge is: copy the new `.py` and `static/` files over the old
ones, restart the server. That's the whole process &mdash; no manual migration
script to remember, no risk of forgetting a step.

Every change to the database shape lives in `migrations.py` as a small, numbered,
idempotent function. On every startup, the server checks which migrations have
already applied to your specific `.db` file (tracked in a `schema_version` row)
and runs only the ones it hasn't seen yet, in order, each in its own transaction.
If a migration fails, it rolls back and the server refuses to start with that
database &mdash; your data is left exactly as it was, and the console tells you to
back up the file before retrying.

This is also how existing data survives structural changes. For example, when
Device Class / Device Category / Device Type / Operating Region / Geolocation /
Region / Center moved from hardcoded fields to the dynamic tag system, the
migration that made that change automatically promoted every value already in use
into a real tag definition and rewrote each device's stored data to match &mdash;
nothing was lost, and no manual cleanup was required.

## Security

SNMPv3 `authKey`/`privKey` values are encrypted at rest with AES-256-GCM, using a
key embedded in `storage.py`. This protects the raw `.db` file itself (e.g. if
someone copies it off a shared drive or finds it in a backup) but is **not** an
access-control mechanism for the running app &mdash; anyone who can reach the
server's HTTP port can use it normally, the same way anyone with the original
spreadsheet could read it. There's no authentication on the API, no rate
limiting, and no RBAC (see [Limitations and non-goals](#limitations-and-non-goals)
above). This is a deliberate, documented tradeoff in favor of staying simple and
dependency-free; if your environment needs real authentication, put ConfigForge
behind a reverse proxy or VPN.

## Architecture

The backend follows a layered architecture introduced in v0.5. Each layer has a single responsibility and depends only on the layer below it through well-defined interfaces.

```
HTTP layer       FastAPI routes (api/) — receive requests, validate with Pydantic v2, call services
Service layer    core/services/ — pure business logic, no HTTP or DB code
Repository layer core/repositories/ — data access via ABC interfaces; SQLAlchemy implementations
Storage layer    core/storage/ — StorageProvider ABC + factory; SQLiteProvider (full), PostgreSQL/MySQL/SQL Server (scaffolds)
Logging layer    core/logging/ — centralized logging, structured output, correlation IDs, log rotation
```

The `StorageProvider` abstraction means repositories never import a database driver directly. Swapping the backend is a config change, not a code change. The logging framework means every component emits structured, correlated records through one root logger — no `logging.basicConfig()` anywhere.

```
server.py                    entry point — CLI args, AppConfig assembly, configure_logging(), uvicorn startup
app.py                       FastAPI application factory (create_app, lifespan, middleware)
core/
  container.py               DI container — wires provider → repos → services
  logging/
    __init__.py              Public API: configure_logging(), get_logger(), get_request_id(), …
    config.py                LoggingConfig (YAML / env / defaults)
    context.py               ContextVar-based request ID propagation
    factory.py               get_logger(__name__)  →  configfoundry.* namespace
    formatters.py            ConfigFoundryFormatter (text) + JSONFormatter
    handlers.py              build_console_handler(), build_file_handler() with rotation
    middleware.py            CorrelationIDMiddleware + RequestLoggingMiddleware
    startup.py               log_startup_info(), log_shutdown_info()
  storage/
    provider.py              StorageProvider ABC, HealthCheckResult, ProviderCapabilities
    config.py                DatabaseConfig, AppConfig (YAML / env / dict constructors)
    factory.py               StorageFactory registry (sqlite, postgresql, mysql, sqlserver + aliases)
    providers/
      sqlite.py              SQLiteProvider — fully functional (WAL mode, migrations, seeding)
      postgresql.py          PostgreSQLProvider — scaffold (interface-compliant, initialize() raises)
      mysql.py               MySQLProvider — scaffold
      sqlserver.py           SQLServerProvider — scaffold
  repositories/
    interfaces/              ABC interfaces for every entity (IDeviceRepository, etc.)
    sqlalchemy/              SQLAlchemy 2.x implementations (8 repos, all accept StorageProvider)
  services/                  Business logic services (DeviceService, GenerateService, etc.)
api/
  dependencies.py            Depends(get_container) — resolves ServiceContainer from request.app.state
  v1/
    router.py                Central v1 router (prefix="/v1", VERSION="v1", PREFIX="/api/v1")
    devices.py  bandwidth.py FastAPI routers (one per entity)
    subnets.py  tags.py  …
schemas/common.py            Pydantic v2 request/response models
migrations.py                Versioned, idempotent SQLite schema migrations
logic.py                     Core YAML conversion — pure functions, no HTTP or DB code
aesgcm.py                    AES-256-GCM credential encryption
static/
  app.js                     Shell: routing, global state, sidebar/topbar, theme toggle
  devices.js  bandwidth.js   Entity views
  networktree.js             Pan/zoom network diagram
  api.js                     Thin fetch() wrapper for every backend endpoint
  ui.js                      Icons, toasts, modals, shared helpers
```

The frontend is intentionally framework-free — plain HTML/CSS/JS served as static files, with [SheetJS](https://sheetjs.com/) vendored locally for `.xlsx` parsing. There's no build step: edit a `.js` file, refresh the browser.

See [`docs/storage-architecture.md`](docs/storage-architecture.md) for the full Storage Abstraction Layer reference, including how to add a new database backend in five steps. See [`docs/logging.md`](docs/logging.md) for the full logging framework reference.

## Logging

Every request is tagged with a 12-character hex correlation ID (`X-Request-ID` header) that appears in every log line emitted during that request. The access log line looks like:

```
2024-01-15 10:30:45 INFO     configfoundry.http    [a3f8c2d1e5b4] GET /api/v1/devices → 200 (12.3ms) ip=127.0.0.1
```

All application code acquires a logger with `get_logger(__name__)` from `core.logging`. The `configure_logging()` function is called once in `server.py` before `create_app()`, reads from `AppConfig.logging` (populated from the YAML `logging:` section or `CONFIGFORGE_LOG_*` env vars), and attaches handlers to the single `configfoundry` root logger. No module calls `logging.basicConfig()` directly.

Request bodies are never logged. Exceptions are logged with full traceback on the server; clients receive only `{"error": "...", "type": "..."}`.

See [`docs/logging.md`](docs/logging.md) for the complete reference: configuration, log formats (text and JSON), correlation IDs, rotation modes, audit log separation design, and how to add a new log destination.

## API Versioning

All REST endpoints are versioned under `/api/v1/`. The version is part of the URL, not a header, so different versions can coexist on the same running server.

### Current endpoints (v1)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/devices` | List all devices |
| `POST` | `/api/v1/devices` | Create or update a device |
| `DELETE` | `/api/v1/devices/{id}` | Delete a device |
| `POST` | `/api/v1/devices/validate-import` | Validate a bulk device import (no DB write) |
| `POST` | `/api/v1/devices/import` | Bulk import (merge or replace) |
| `GET` | `/api/v1/bandwidth` | List all bandwidth rows |
| `GET` | `/api/v1/subnets` | List all subnets |
| `GET` | `/api/v1/tags` | List all tag definitions |
| `POST` | `/api/v1/generate` | Generate YAML from current data |
| `GET` | `/api/v1/export/devices.xlsx` | Download devices as Excel |

The full list is available at **`http://localhost:8420/docs`** (Swagger UI).

### How to add v2

1. Create `api/v2/` with the same layout as `api/v1/`:
   ```
   api/v2/__init__.py
   api/v2/router.py          # APIRouter(prefix="/v2"), includes sub-routers
   api/v2/devices.py         # override or extend endpoint behaviour
   # … other modules as needed
   ```

2. In `api/v2/router.py`, define or import the new endpoint logic:
   ```python
   from fastapi import APIRouter
   from api.v2 import devices   # new v2 implementation
   # optionally re-export unchanged v1 routers:
   from api.v1 import bandwidth, subnets, ...

   router = APIRouter(prefix="/v2")
   router.include_router(devices.router,   tags=["v2-devices"])
   router.include_router(bandwidth.router, tags=["bandwidth"])
   ```

3. Register the new router in `app.py` alongside v1:
   ```python
   from api.v1.router import router as v1_router
   from api.v2.router import router as v2_router

   app.include_router(v1_router, prefix="/api")
   app.include_router(v2_router, prefix="/api")
   ```
   Both versions coexist under the same FastAPI app. The combined OpenAPI spec at `/docs` shows `/api/v1/` and `/api/v2/` paths side by side.

4. **Mount `StaticFiles` last** — after all `include_router` calls — so the catch-all static handler does not shadow the new versioned routes.

### Versioning rules

- Business logic lives in `core/services/`. Routers only translate HTTP ↔ service calls. Changing behaviour in v2 means writing new service methods or new service classes — not touching v1 routers.
- Schemas live in `schemas/`. A v2 router can use different Pydantic models while the underlying services remain the same.
- Never modify a v1 router after it ships — create v2 instead.
- Version-specific tests live in `tests/api/test_versioning.py`.

---

## REST API

All endpoints are under `/api/v1/`. A few representative examples:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/devices` | List all devices |
| `POST` | `/api/v1/devices` | Create or update a device |
| `DELETE` | `/api/v1/devices/{id}` | Delete a device |
| `POST` | `/api/v1/devices/import` | Bulk import (merge or replace) |
| `GET` | `/api/v1/subnets` | List all subnets |
| `GET` | `/api/v1/tags` | List all tag definitions |
| `POST` | `/api/v1/tags` | Create or update a tag definition |
| `DELETE` | `/api/v1/tags/{id}` | Delete a tag (409 if in use, unless `?force=true`) |
| `POST` | `/api/v1/generate` | Generate YAML from current data, save a history entry |
| `GET` | `/api/v1/export/devices.xlsx` | Download devices as an Excel template |

The complete request/response contract is available interactively at **`http://localhost:8420/docs`** (Swagger UI) once the server is running. Every endpoint is documented with its expected body, parameters, and response shape.

## Contributing

This is a young project &mdash; I'm the sole maintainer so far. Issues and pull
requests are welcome at
[github.com/shivamsancc/ConfigForge](https://github.com/shivamsancc/ConfigForge).

The project optimizes for running on locked-down, offline, single-team
infrastructure over almost anything else. If a PR trades that away for
convenience &mdash; a new pip dependency, a build step, an assumption that the
internet is reachable &mdash; expect pushback on the tradeoff, not the code
itself. A few more specific things worth knowing before you dive in:

- **Any schema change goes in `migrations.py`**, never as an ad-hoc `ALTER` in a repository or provider. Add a new numbered `migrate_N` function; never edit an existing one after release. If you're adding a new entity type alongside Devices/Bandwidth/Subnets, the pattern is: migration in `migrations.py`, ORM model in `models/`, ABC interface in `core/repositories/interfaces/`, SQLAlchemy implementation in `core/repositories/sqlalchemy/`, service in `core/services/`, FastAPI router in `api/`, Pydantic schemas in `schemas/`, wired up in `core/container.py`, and a JS view in `static/` following `subnets.js` as the simplest template.
- Keep new pip dependencies to a minimum. The core stack (FastAPI, SQLAlchemy, Pydantic, uvicorn) is established; anything new needs a strong justification. Optional-feature dependencies should be gated behind a `try/except` with a clear fallback message.
- The frontend has no build step on purpose. Please don't introduce one without
  discussing it first &mdash; that's a deliberate tradeoff, not an oversight.
- `yamldump.py` and `aesgcm.py` are both verified against their "real"
  counterparts (PyYAML and pycryptodome) in extensive fuzz tests during
  development. If you touch either file, please re-verify against the real
  library before submitting.
- `networktree.js`'s pan/zoom clamps panning and zooming so content can never
  drift fully out of view (see `clampZoomToContent`). If you touch the zoom
  math, test with a real button-click zoom-in followed by selecting a large
  bucket &mdash; that combination is what originally exposed the bug this
  guards against.

## License

MIT &mdash; see [LICENSE](LICENSE).
