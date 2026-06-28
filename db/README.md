# db/

This directory is the default location for ConfigForge's SQLite database.

## Default database

`configforge.db` is created here automatically the first time `server.py`
starts with no `--db` flag:

```bash
python3 server.py
# opens db/configforge.db
```

## Using a custom path

Point `--db` at any writable file path — a shared network drive, a Docker
volume, a different local path:

```bash
python3 server.py --db /mnt/shared/configforge.db
python3 server.py --db ~/my-configforge.db
```

The database file does not need to exist beforehand; ConfigForge creates it
and runs all migrations on first start.

## Schema

The schema is defined and evolved entirely through `core/migrations.py`.
Never modify the database by hand; always add a new numbered migration instead.

## Backups

SQLite databases are single files — back them up with a file copy:

```bash
cp db/configforge.db db/configforge.db.bak
```

For consistent snapshots of a live database, use SQLite's backup API or
`.dump`:

```bash
sqlite3 db/configforge.db .dump > backup.sql
```

## Git

Database files are excluded from version control (see `.gitignore`).
Only this README is tracked — the `.db` files themselves are runtime
artifacts and should not be committed.
