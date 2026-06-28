# Tests

This directory is reserved for ConfigForge's automated test suite.
No test code exists yet — this is a known gap explicitly called out in the
project README. Contributions are welcome.

---

## Philosophy

ConfigForge's test philosophy mirrors its architecture:

- **Prefer unit tests over integration tests.** Most of the interesting logic
  (`core/logic.py`, `formats/yamldump.py`, `core/aesgcm.py`) is pure functions
  that take plain Python values and return plain Python values. They can be
  tested without a database, without a running server, and without mocking
  anything.

- **Use the standard library.** Tests run with `python3 -m unittest` — no test
  runner install required. `pytest` is supported as an optional alternative but
  must not be required.

- **Tests must pass offline.** No network calls. No external services. No pip
  packages that are not already available on the machine.

- **Tests document expected behavior.** A failing test should tell you exactly
  what contract was violated, not just that something broke.

---

## Recommended directory layout

Mirror the package structure. Each subdirectory covers one area of the codebase:

```
tests/
    storage/
        test_devices.py       CRUD, encryption round-trip, replace/merge modes
        test_bandwidth.py
        test_subnets.py
        test_tags.py
        test_audit.py
        test_history.py
        test_migrations.py    Apply all migrations to a temp DB; test idempotency
    logic/
        test_convert.py       convert_to_collector_configs: SNMP, ICMP, subnet inheritance
        test_validation.py    is_valid_ip, normalize_group_key, should_be_icmp_only
    handler/
        test_devices_api.py   HTTP round-trips: GET/POST/DELETE /api/devices
        test_generate_api.py  POST /api/generate, verify YAML in response
        test_export_api.py    GET /api/export/devices.xlsx, verify ZIP magic bytes
    formats/
        test_yamldump.py      dump() against PyYAML (if available); edge cases
        test_xlsxwriter.py    write_xlsx(); verify headers and cell values round-trip
        test_aesgcm.py        encrypt/decrypt round-trip; tamper detection; wrong key
    integration/
        README.md             Future end-to-end tests (start server, drive with http.client)
```

Each file follows `test_<module>.py` naming so `unittest discover` picks them
up automatically.

---

## Running tests

No configuration needed. From the repository root:

```bash
# Run all tests
python3 -m unittest discover tests/

# Run one subdirectory
python3 -m unittest discover tests/logic/

# Run one file
python3 -m unittest tests/formats/test_yamldump.py

# With pytest (optional)
pytest tests/
```

---

## Writing a test

```python
# tests/logic/test_validation.py
import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.logic import is_valid_ip, normalize_group_key


class TestIsValidIp(unittest.TestCase):

    def test_valid_ipv4(self):
        self.assertTrue(is_valid_ip('10.0.0.1'))

    def test_invalid_string(self):
        self.assertFalse(is_valid_ip('not-an-ip'))

    def test_empty_string(self):
        self.assertFalse(is_valid_ip(''))


class TestNormalizeGroupKey(unittest.TestCase):

    def test_spaces_become_underscores(self):
        self.assertEqual(normalize_group_key('AWS Mumbai'), 'aws_mumbai')

    def test_leading_trailing_stripped(self):
        self.assertEqual(normalize_group_key('  eu-west  '), 'eu_west')


if __name__ == '__main__':
    unittest.main()
```

---

## Test priorities

In rough priority order, these are the areas that would benefit most from
automated coverage:

1. **`core/logic.py`** — The YAML generation pipeline is the most critical
   path in the project. Pure functions, no mocks needed.

2. **`core/aesgcm.py`** — Encryption correctness. Tamper detection must raise.
   Wrong-key decryption must not silently return garbage.

3. **`formats/yamldump.py`** — Byte-for-byte comparison against PyYAML
   (guarded by `@unittest.skipUnless(importlib.util.find_spec('yaml'), 'PyYAML not installed')`).

4. **`core/migrations.py`** — Apply all migrations to a fresh temp database;
   verify the final schema; confirm running migrations twice is a no-op.

5. **`core/storage.py`** — CRUD for every entity type using a temp SQLite file
   (`tempfile.mkstemp(suffix='.db')`). Tear down in `tearDown`.

6. **`core/handler.py`** — HTTP-level tests using `http.client` against a
   server started on a random ephemeral port in `setUpClass`. These are slower
   and depend on the storage layer, so they belong in the integration bucket.
