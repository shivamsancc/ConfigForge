# Tests

This directory is reserved for ConfigForge's automated test suite.

The README acknowledges this as a known gap and welcomes contributions.
The modules most in need of tests, in priority order:

## Priority 1 — Pure functions (no mocks needed)

**`core/logic.py`** — `convert_to_collector_configs` is the most important
function in the project: it is the only place that turns inventory data into
YAML config. It accepts plain dicts and returns plain dicts, making it trivially
testable without a database or HTTP server.

Suggested coverage:
- Device with full SNMPv3 creds → appears in correct region file
- Device missing Collector Region → appears in `missingRegionDevices`
- Device with ICMP Config Type → `mode: icmp`, no SNMP fields
- Bandwidth row matched to device by IP → `interface_configs` populated
- Subnet inheritance → device without tag inherits tag from matching subnet
- Overlapping subnets → most-specific (longest prefix) wins

**`formats/yamldump.py`** — Already verified by hand against PyYAML across
thousands of randomized inputs. A regression test should capture that behavior:
run `dump()` and `yaml.dump()` (if PyYAML is available) on the same input and
assert byte-for-byte identity for all types the project actually writes.

**`formats/xlsxwriter.py`** — Write a file, open it with SheetJS or openpyxl
(test-only dep), verify headers and cell values round-trip correctly.

**`core/aesgcm.py`** — Encrypt/decrypt round-trip, tamper detection (flip one
byte in the ciphertext, expect `ValueError`), wrong key detection.

## Priority 2 — Storage layer (requires a temp SQLite file)

**`core/storage.py`** — Use `tempfile.mkstemp()` for an isolated test database,
run `storage.init()`, then verify CRUD operations and credential encryption.

**`core/migrations.py`** — Apply all migrations to a fresh database and confirm
the final schema matches expectations. Also test idempotency: run migrations
twice and confirm no error.

## Priority 3 — Integration tests (requires a running server)

**`core/handler.py`** — Start a `ThreadingHTTPServer` on a random port in a
`setUp` fixture, drive it with `http.client`, assert JSON responses. This
covers the full stack end-to-end.

## Running tests

No test runner is required — Python's built-in `unittest` framework is
sufficient:

```bash
python3 -m unittest discover tests/
```

If `pytest` is available it will also discover and run the same files with no
configuration needed.

## Conventions

- One file per module under test: `test_logic.py`, `test_yamldump.py`, etc.
- Test classes inherit from `unittest.TestCase`.
- No pip dependencies in test files except `pytest` (optional) and `openpyxl`
  (optional, for XLSX round-trip tests). Guard optional deps with
  `@unittest.skipUnless(...)`.
- Tests must pass offline with no internet access.
