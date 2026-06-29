# Storage Architecture

ConfigFoundry v0.5 introduces a **Storage Abstraction Layer** that completely decouples the application from any specific database driver or engine. No repository, service, or route contains database-specific logic; all of that lives inside a `StorageProvider` implementation.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Layer                           │
│  FastAPI routes  →  Depends(get_container)                  │
└────────────────────────┬────────────────────────────────────┘
                         │ ServiceContainer
┌────────────────────────▼────────────────────────────────────┐
│                     Service Layer                           │
│  DeviceService  BandwidthService  SubnetService  …          │
│  (pure business logic — no DB calls)                        │
└────────────────────────┬────────────────────────────────────┘
                         │ Repository interfaces (ABCs)
┌────────────────────────▼────────────────────────────────────┐
│                  Repository Layer                           │
│  SQLAlchemyDeviceRepository  SQLAlchemyBandwidthRepository  │
│  …  (8 concrete repos, all accept StorageProvider)          │
└────────────────────────┬────────────────────────────────────┘
                         │ StorageProvider.get_engine()
┌────────────────────────▼────────────────────────────────────┐
│               StorageProvider (ABC)                         │
│  initialize()  shutdown()  get_engine()  health_check()     │
│  get_metadata()  get_capabilities()  get_session_factory()  │
└───┬────────────────┬──────────────────┬────────────────┬────┘
    │                │                  │                │
┌───▼───┐    ┌───────▼──────┐  ┌───────▼──┐  ┌─────────▼──┐
│SQLite │    │ PostgreSQL   │  │  MySQL   │  │ SQL Server │
│(full) │    │ (scaffold)   │  │(scaffold)│  │ (scaffold) │
└───────┘    └──────────────┘  └──────────┘  └────────────┘
```

The `StorageFactory` selects the correct provider at startup based on config. Repos never import a driver directly — they receive a `StorageProvider` through constructor injection.

---

## Module Layout

```
core/
  storage/
    __init__.py          # Public API + backward-compat shim (init(), list_devices(), …)
    provider.py          # StorageProvider ABC, HealthCheckResult, ProviderCapabilities, ProviderMetadata
    config.py            # DatabaseConfig, AppConfig dataclasses
    factory.py           # StorageFactory registry
    providers/
      __init__.py
      sqlite.py          # SQLiteProvider — fully functional
      postgresql.py      # PostgreSQLProvider — scaffold
      mysql.py           # MySQLProvider — scaffold
      sqlserver.py       # SQLServerProvider — scaffold
```

---

## StorageProvider Interface

Every provider must implement all methods of the ABC:

```python
class StorageProvider(ABC):
    def initialize(self) -> None: ...
        # Create engine, run migrations, seed data.
        # Raises NotImplementedError on scaffold providers.

    def shutdown(self) -> None: ...
        # Dispose engine / close connections. Must be idempotent.

    def get_engine(self) -> Engine: ...
        # Returns the live SQLAlchemy engine.
        # Raises RuntimeError if called before initialize() or after shutdown().

    def get_session_factory(self) -> sessionmaker: ...
        # Returns a bound sessionmaker.
        # Raises RuntimeError if called before initialize().

    def health_check(self) -> HealthCheckResult: ...
        # Non-raising. Returns HEALTHY/DEGRADED/UNHEALTHY with latency_ms.
        # Returns UNHEALTHY before initialize() and after shutdown().

    def get_metadata(self) -> ProviderMetadata: ...
        # Works without a live connection (name, version, driver, dialect).

    def get_capabilities(self) -> ProviderCapabilities: ...
        # Works without a live connection (feature flags).

    @property
    def name(self) -> str: ...
        # Convenience — returns get_metadata().name.
```

### Data classes

```python
@dataclass
class HealthCheckResult:
    status: HealthStatus          # HEALTHY | DEGRADED | UNHEALTHY
    message: str
    latency_ms: Optional[float]   # round-trip time in milliseconds
    details: Optional[dict]
    is_healthy: bool              # property: status == HEALTHY

@dataclass
class ProviderCapabilities:
    transactions: bool = True
    migrations: bool = True
    full_text_search: bool = False
    json_columns: bool = False
    array_columns: bool = False
    schemas: bool = False
    read_replicas: bool = False
    row_level_security: bool = False

@dataclass
class ProviderMetadata:
    name: str
    version: str
    driver: str
    dialect: str
    capabilities: ProviderCapabilities
```

---

## Configuration

### DatabaseConfig fields

| Field            | Type            | Default                    | Description                                      |
|------------------|-----------------|----------------------------|--------------------------------------------------|
| `provider`       | `str`           | `"sqlite"`                 | Provider name (see registry below)               |
| `sqlite_path`    | `str`           | `"db/configforge.db"`      | Path to SQLite file, or `":memory:"`             |
| `connection_url` | `str \| None`   | `None`                     | Full SQLAlchemy URL (non-SQLite backends)         |
| `pool_size`      | `int`           | `5`                        | Connection pool size                             |
| `max_overflow`   | `int`           | `10`                       | Max connections above pool_size                  |
| `echo`           | `bool`          | `False`                    | Log all SQL statements (development only)        |
| `connect_args`   | `dict`          | `{}`                       | Extra kwargs passed to `create_engine()`         |

### AppConfig

`AppConfig` is the top-level config object. Currently it wraps `DatabaseConfig`; future milestones may add `logging`, `auth`, and `features` sections.

```python
@dataclass
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
```

### Constructors

```python
# SQLite shortcut
config = AppConfig.for_sqlite("/path/to/configforge.db")
config = AppConfig.for_sqlite(":memory:")      # in-memory, useful for tests

# From a dict
config = AppConfig.from_dict({"database": {"provider": "sqlite", "sqlite_path": "db/cf.db"}})

# From environment variables
config = AppConfig.from_env()

# From a YAML file
config = AppConfig.from_yaml("/etc/configfoundry/config.yaml")
```

### Environment variables

All variables use the `CONFIGFORGE_DB_` prefix:

| Variable                       | DatabaseConfig field  |
|--------------------------------|-----------------------|
| `CONFIGFORGE_DB_PROVIDER`      | `provider`            |
| `CONFIGFORGE_DB_SQLITE_PATH`   | `sqlite_path`         |
| `CONFIGFORGE_DB_CONNECTION_URL`| `connection_url`      |
| `CONFIGFORGE_DB_POOL_SIZE`     | `pool_size`           |
| `CONFIGFORGE_DB_MAX_OVERFLOW`  | `max_overflow`        |
| `CONFIGFORGE_DB_ECHO`          | `echo`                |

### YAML config file

```yaml
# /etc/configfoundry/config.yaml
database:
  provider: postgresql
  connection_url: "postgresql+psycopg2://user:pass@db-host:5432/configforge"
  pool_size: 10
  max_overflow: 20
  echo: false
```

Pass it to the server with `--config`:

```bash
python3 server.py --config /etc/configfoundry/config.yaml --port 8420
```

---

## StorageFactory

`StorageFactory` is a registry-based factory. All four built-in providers are registered at import time via `_register_builtins()`.

### Built-in provider names

| Name           | Class                | Notes                       |
|----------------|----------------------|-----------------------------|
| `sqlite`       | `SQLiteProvider`     | Fully functional            |
| `postgresql`   | `PostgreSQLProvider` | Scaffold                    |
| `postgres`     | `PostgreSQLProvider` | Alias for `postgresql`      |
| `mysql`        | `MySQLProvider`      | Scaffold                    |
| `sqlserver`    | `SQLServerProvider`  | Scaffold                    |
| `mssql`        | `SQLServerProvider`  | Alias for `sqlserver`       |

### Usage

```python
from core.storage import StorageFactory, DatabaseConfig

config = DatabaseConfig(provider="sqlite", sqlite_path="db/cf.db")
provider = StorageFactory.create(config)   # instantiates SQLiteProvider(config)
provider.initialize()

# Listing registered providers
names = StorageFactory.list_providers()    # sorted list of strings

# Registering a custom provider
StorageFactory.register("duckdb", DuckDBProvider)

# Removing a provider (e.g. in tests)
StorageFactory.unregister("duckdb")
```

Provider names are matched **case-insensitively**. An unknown name raises `ValueError`.

---

## Dependency Injection

`ServiceContainer` is the single wiring point. Every repository receives the `StorageProvider` via constructor injection:

```python
# container.py (simplified)
class ServiceContainer:
    def __init__(self, *, config: AppConfig) -> None:
        self._provider = StorageFactory.create(config.database)
        self._provider.initialize()

        self.device_repo     = SQLAlchemyDeviceRepository(self._provider)
        self.bandwidth_repo  = SQLAlchemyBandwidthRepository(self._provider)
        # …

        self.device_service  = DeviceService(self.device_repo, self.audit_repo)
        # …
```

`ServiceContainer` also accepts `db_path: str` (SQLite shortcut, backward-compatible) and `provider: StorageProvider` (for tests that need direct control).

FastAPI resolves the container per request via `Depends(get_container)` in `api/dependencies.py`, which reads `request.app.state.container`.

---

## Adding a New Provider

Follow these steps to add support for a new database backend:

**1. Create the provider module** in `core/storage/providers/`:

```python
# core/storage/providers/duckdb.py
from core.storage.provider import (
    StorageProvider, HealthCheckResult, HealthStatus,
    ProviderCapabilities, ProviderMetadata,
)
from core.storage.config import DatabaseConfig

class DuckDBProvider(StorageProvider):
    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine = None
        self._session_factory_obj = None

    def initialize(self) -> None:
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker

        url = f"duckdb:///{self._config.sqlite_path}"   # or connection_url
        self._engine = create_engine(url, **self._extra_kwargs())
        self._session_factory_obj = sessionmaker(bind=self._engine)
        # run any migrations here

    def shutdown(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None

    def get_engine(self):
        if self._engine is None:
            raise RuntimeError("DuckDBProvider.initialize() has not been called")
        return self._engine

    def get_session_factory(self):
        if self._session_factory_obj is None:
            raise RuntimeError("DuckDBProvider.initialize() has not been called")
        return self._session_factory_obj

    def health_check(self) -> HealthCheckResult:
        import time
        if self._engine is None:
            return HealthCheckResult(HealthStatus.UNHEALTHY, "Not initialised")
        try:
            from sqlalchemy import text
            t0 = time.perf_counter()
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            latency_ms = (time.perf_counter() - t0) * 1000
            return HealthCheckResult(HealthStatus.HEALTHY, "OK", latency_ms=latency_ms)
        except Exception as exc:
            return HealthCheckResult(HealthStatus.UNHEALTHY, str(exc))

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="duckdb", version="unknown", driver="duckdb_engine", dialect="duckdb",
            capabilities=self.get_capabilities(),
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            transactions=True, migrations=True, full_text_search=True,
            json_columns=True, array_columns=True, schemas=True,
        )

    def _extra_kwargs(self) -> dict:
        return {"echo": self._config.echo, **self._config.connect_args}
```

**2. Export from the providers package:**

```python
# core/storage/providers/__init__.py
from core.storage.providers.duckdb import DuckDBProvider
```

**3. Register in `core/storage/factory.py`:**

```python
def _register_builtins():
    # … existing registrations …
    StorageFactory.register("duckdb", DuckDBProvider)
```

**4. Write tests** in `tests/storage/` — follow `test_sqlite_provider.py` as the template. Scaffold providers only need the `TestScaffoldProviders`-style suite; fully functional providers need the complete lifecycle suite.

**5. Add driver to `requirements.txt`** (e.g. `duckdb-engine>=0.9.0`).

---

## Scaffold Providers

`PostgreSQLProvider`, `MySQLProvider`, and `SQLServerProvider` are **interface-compliant scaffolds**:

- `initialize()` → raises `NotImplementedError` with a helpful message
- `get_engine()` / `get_session_factory()` → raise `RuntimeError` (no engine available)
- `health_check()` → returns `UNHEALTHY` with `{"scaffold": True}` in `details` — never raises
- `shutdown()` → no-op
- `get_metadata()` / `get_capabilities()` → fully implemented, work without a live connection

This means scaffold providers can be inspected and registered without any database being present, making feature-detection and configuration UIs possible even before a backend is implemented.

---

## Session Management Strategy

All repositories use **per-operation sessions** via a context manager:

```python
with Session(self._engine) as session:
    # read or write
    session.commit()
```

This keeps repositories stateless (no held connections between calls), makes them safe to reuse across requests without locking, and allows the module-level storage shim to work without FastAPI request context.

**No shared session is passed between repos or services.** Each repo call opens and closes its own session. This is the recommended pattern for SQLAlchemy 2.x write workloads with a connection pool.

---

## Technical Debt & Next-Milestone Recommendations

### High priority

- **Implement PostgreSQL/MySQL/SQL Server providers.** The scaffolds are fully wired — only `initialize()`, `get_engine()`, and `get_session_factory()` need real bodies. Add `psycopg2`, `pymysql`, and `pyodbc` to `requirements.txt`, and adapt `SQLiteProvider._run_migrations()` to use SQLAlchemy DDL or Alembic instead of raw `sqlite3` commands.

- **Migrate to Alembic.** The current migration system uses raw `sqlite3` statements in `core/migrations.py`. Alembic would make schema evolution provider-agnostic and give a proper revision history.

- **Async support.** FastAPI + SQLAlchemy 2.x support `AsyncEngine` and `AsyncSession`. Adding an `AsyncStorageProvider` subtype (or a flag on the existing ABC) would allow fully async request handling.

### Medium priority

- **Connection URL validation.** `DatabaseConfig` accepts any string as `connection_url`. Add a `validate()` method (or Pydantic model) that checks the URL scheme matches the declared provider before `initialize()` is called.

- **Pool health monitoring.** Expose `pool.status()` in `health_check()` details so operators can see checkout counts, overflow, and timeouts without hitting the DB directly.

- **Config hot-reload.** Currently the provider is created once at startup. Introducing a reload endpoint (or SIGHUP handler) that recreates the container without restarting the process would help in long-lived deployments.

### Low priority

- **Remove `core/db.py`.** This file was the pre-abstraction entry point for `init_db()`. It is no longer called by any production code (SQLiteProvider owns that logic). It can be deleted once any remaining direct imports are confirmed absent.

- **Drop the backward-compat shim functions** in `core/storage/__init__.py` (`list_devices()`, `upsert_device()`, etc.) once the handler tests are updated to call the container directly.

- **Silence the `StarletteDeprecationWarning`** by upgrading to `httpx2` once it reaches a stable release.
