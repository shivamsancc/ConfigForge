# Database Migrations

ConfigFoundry v0.5 manages all database schema changes through [Alembic](https://alembic.sqlalchemy.org/), the standard SQLAlchemy migration toolkit. Every schema change is a versioned, reviewable Python file stored in `alembic/versions/`. Migrations are applied automatically at startup.

---

## How it works

```
server.py                   configure_logging() + create_app()
    │
    ▼
ServiceContainer            builds SQLiteProvider (or future PostgreSQL/MySQL)
    │
    ▼
StorageProvider.initialize()
    │
    ▼
core.migrations.runner.run_migrations(engine)
    │
    ├── No alembic_version, no app tables  →  alembic upgrade head  (fresh DB)
    ├── No alembic_version, has app tables →  alembic stamp head    (legacy DB)
    └── Has alembic_version                →  alembic upgrade head  (no-op or pending)
```

**Startup is always safe to run.** If the database is already at head (the common case), `upgrade head` is a no-op. If new migrations are pending (after deploying a new version), they are applied automatically before any request is served.

---

## Alembic environment layout

```
alembic.ini                  Alembic configuration (script_location, default URL)
alembic/
  env.py                     Migration environment — connection wiring, metadata
  script.py.mako             Template for new revision files
  versions/
    0001_baseline_schema.py  Baseline: creates all 8 tables (revision c1f4e7a8b2d0)
core/
  migrations/
    __init__.py              Package: exports run_migrations()
    runner.py                Programmatic API called by storage providers
  migrations_legacy.py       LEGACY — original custom sqlite3 system (reference only)
```

---

## Common CLI commands

Run from the project root. If the default SQLite URL in `alembic.ini` is not what you want, set `CONFIGFORGE_DB_URL`:

```bash
export CONFIGFORGE_DB_URL=sqlite:///db/configforge.db
# or
export CONFIGFORGE_DB_URL=postgresql+psycopg2://user:pass@host:5432/configforge
```

### Apply all pending migrations

```bash
alembic upgrade head
```

Runs every migration that has not yet been applied to the target database. This is what the application does automatically on startup. Safe to run while the server is stopped.

### Check current migration state

```bash
alembic current
```

Shows which revision the database is currently at. Example output:

```
c1f4e7a8b2d0 (head)
```

### Show full migration history

```bash
alembic history --indicate-current
```

Lists all revisions in order with an arrow next to the current one:

```
c1f4e7a8b2d0 -> (head), Baseline schema — all tables at schema version 4
-> c1f4e7a8b2d0 (current), Baseline schema — all tables at schema version 4
```

### Roll back one migration

```bash
alembic downgrade -1
```

Rolls back the most recently applied migration. Use `alembic downgrade base` to roll back all migrations (drops all application tables).

### Stamp a database (no DDL)

```bash
alembic stamp head
```

Marks the database as being at the head revision without running any migrations. Used when taking over a database that was set up outside of Alembic. The runner does this automatically for databases created by the old custom migration system.

### Preview SQL (offline mode)

```bash
alembic upgrade head --sql
```

Generates the SQL DDL for pending migrations without executing it. Useful for DBA review, audit trails, or applying migrations through a controlled process.

---

## Adding a new migration

Every schema change — new table, new column, renamed column, added index — must be a new Alembic migration. Never modify an existing migration after it has been deployed.

### 1. Update the ORM model

Edit the relevant model in `models/inventory.py`. For example, adding a `hostname` column to devices:

```python
class DeviceModel(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    hostname: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # new
```

### 2. Autogenerate the migration

With the target database at head, run:

```bash
alembic revision --autogenerate -m "add hostname column to devices"
```

Alembic compares the live database schema to the ORM models and generates a diff-based migration in `alembic/versions/`. Review the generated file carefully before committing — autogenerate is not perfect and may miss some differences (e.g. check constraints, some index types).

### 3. Review the generated file

The generated file will look like:

```python
# alembic/versions/a2b3c4d5e6f7_add_hostname_column_to_devices.py

revision = "a2b3c4d5e6f7"
down_revision = "c1f4e7a8b2d0"

def upgrade() -> None:
    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(sa.Column("hostname", sa.String(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_column("hostname")
```

Note the `op.batch_alter_table()` context — this is required for SQLite, which does not support `ALTER TABLE` directly. It is a no-op for PostgreSQL and MySQL.

### 4. Apply and test

```bash
alembic upgrade head
python3 -m pytest tests/migrations/
```

### 5. Commit

Commit both the model change and the migration file together. The migration file is part of the application source code — it must be in version control.

---

## SQLite batch mode

SQLite does not support most `ALTER TABLE` operations (add column to existing table, drop column, rename column). Alembic's `render_as_batch=True` option (enabled in `alembic/env.py`) wraps such operations in a table-copy-rename dance that achieves the same result.

This is transparent to callers. Use `op.batch_alter_table()` in all migrations that modify existing tables:

```python
# Correct — works on SQLite, PostgreSQL, MySQL, SQL Server
def upgrade() -> None:
    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(sa.Column("hostname", sa.String(), nullable=True))

# Wrong — fails on SQLite
def upgrade() -> None:
    op.add_column("devices", sa.Column("hostname", sa.String(), nullable=True))
```

`op.create_table()` and `op.drop_table()` (used in the baseline migration) do not require batch mode.

---

## Multi-database support

The migration files use SQLAlchemy column types (`sa.String`, `sa.Text`, `sa.Float`) rather than database-specific types, so they generate correct DDL for all supported backends:

| SQLAlchemy type | SQLite       | PostgreSQL          | MySQL         |
|----------------|--------------|---------------------|---------------|
| `sa.String()`  | TEXT         | VARCHAR             | VARCHAR(255)  |
| `sa.Text()`    | TEXT         | TEXT                | TEXT          |
| `sa.Float()`   | REAL         | DOUBLE PRECISION    | DOUBLE        |

Avoid database-specific SQL unless there is no cross-database alternative. If provider-specific SQL is unavoidable, gate it on the dialect:

```python
from alembic import op

def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # PostgreSQL-specific DDL
        op.execute("CREATE INDEX CONCURRENTLY ...")
    else:
        op.create_index("ix_devices_id", "devices", ["id"])
```

---

## Existing database compatibility

### Databases from before Alembic (schema_version 4)

The `core.migrations.runner` automatically detects databases that were created by the old `core/migrations_legacy.py` custom system. These have all application tables but no `alembic_version` table.

Detection: `meta` table exists AND `alembic_version` table does not.

Action: `alembic stamp head` — writes the baseline revision ID to `alembic_version` without touching any data or schema. On the next startup, the database is treated as Alembic-managed.

### Databases from before schema_version 4

If you have a database at schema_version 1–3, upgrade it to schema_version 4 first by running the old server one final time, then upgrade to the Alembic-managed version.

---

## Release process

For every release that includes schema changes:

1. **Ship the migration file** in `alembic/versions/` alongside the application code.
2. **Stop the old server** (or use a blue/green deployment).
3. **(Optional) Preview the SQL**: `alembic upgrade head --sql > migration.sql` — review before applying.
4. **Restart the new server** — migrations run automatically on startup.

The application aborts startup if a migration fails, leaving the database untouched.

---

## Rollback

To roll back a migration after an incident:

```bash
# Check what's current
alembic current

# Roll back one migration
alembic downgrade -1

# Restart the old version of the application
```

Not all schema changes are safely reversible. A migration that drops a column loses data — the downgrade would need to re-add the column, but the original data is gone. Plan downgrade paths carefully:

- **Additive changes** (add column, add table, add index) — always safe to downgrade.
- **Destructive changes** (drop column, drop table) — reversible structurally but data is lost. Back up the database before applying.
- **Data migrations** (reshaping rows) — write explicit upward and downward data transforms in `upgrade()` and `downgrade()`.

---

## Developer guidelines

**Rule 1: Never edit a shipped migration.** If a migration has been applied to any environment (dev, staging, production), it is immutable. Fix forward with a new migration.

**Rule 2: Migrations are code, not secrets.** Commit migration files alongside the model changes that require them. A PR without the migration file is incomplete.

**Rule 3: Test migrations.** Every migration should have a test in `tests/migrations/` that verifies the upgrade, checks the resulting schema, and (for reversible changes) verifies the downgrade.

**Rule 4: Use batch mode.** Always use `op.batch_alter_table()` for modifications to existing tables so SQLite users are not left behind.

**Rule 5: Keep migrations provider-agnostic.** Use SQLAlchemy column types. Document any unavoidable dialect-specific code with a comment explaining why.

**Rule 6: Autogenerate is a starting point, not the finish.** Review the generated file. Alembic cannot detect: check constraints, renamed columns (it sees a drop + add), some custom types, server-side defaults on existing rows.

---

## Quick reference

| Task | Command |
|------|---------|
| Apply pending migrations | `alembic upgrade head` |
| Check current version | `alembic current` |
| View history | `alembic history --indicate-current` |
| Roll back one migration | `alembic downgrade -1` |
| Roll back all migrations | `alembic downgrade base` |
| Generate new migration | `alembic revision --autogenerate -m "description"` |
| Preview SQL only | `alembic upgrade head --sql` |
| Stamp without DDL | `alembic stamp head` |

| File | Purpose |
|------|---------|
| `alembic.ini` | Alembic configuration (URL, script location) |
| `alembic/env.py` | Connection wiring, metadata, multi-DB support |
| `alembic/versions/` | All migration files (one per schema change) |
| `core/migrations/runner.py` | Programmatic API used by storage providers |
| `core/migrations_legacy.py` | Reference: old custom migration system |
| `tests/migrations/` | Migration tests |
