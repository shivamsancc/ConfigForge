# SNMP Collector Config Generator — Server (backend only, work in progress)

## Status
Backend is complete and tested end-to-end (including concurrent multi-client
HTTP access). The `static/` folder is currently empty — frontend comes next.
Right now there's no UI; you can only talk to this via curl/HTTP until the
frontend is built.

## Files
- `server.py`     — entry point. Run this.
- `handler.py`    — HTTP request routing + REST API.
- `storage.py`    — SQLite (WAL mode) datastore, credential encryption.
- `logic.py`      — YAML-generation rules (ported from the original logic.js).
- `yamldump.py`   — pure-Python YAML serializer matching PyYAML's output.
- `aesgcm.py`     — pure-Python AES-256-GCM (encrypts authKey/privKey at rest).

All six files are stdlib-only — zero `pip install` needed on the machine
that runs this.

## Running it
```
python3 server.py --db snmp_yaml_generator.db --port 8420
```
Put `--db` on your FSx share so the data is shared and backed up. One
person runs this on one always-on machine; everyone else just opens
`http://<that machine's address>:8420/` in a browser (once the frontend
exists — right now that URL serves nothing since `static/` is empty).

## What's verified
- AES-256-GCM cross-validated against pycryptodome (encrypt/decrypt both
  directions, tamper detection) — confirms the encryption is real, not
  just self-consistent.
- YAML output matches real PyYAML byte-for-byte across 5000+ randomized
  fuzz trials covering realistic device/bandwidth/credential shapes plus
  YAML 1.1 quoting edge cases (binary/octal/hex-looking strings, booleans,
  leading hyphens, etc).
- Conversion logic (Eth-interface regex fix, per-device credential
  completeness, ICMP-forcing rules, mandatory-region exclusion) unit
  tested against the documented behavior from the original browser tool.
- Full REST API smoke-tested live over real HTTP: device/bandwidth CRUD,
  bulk import (merge/replace), managed lists + usage counts, audit log,
  YAML history, and `/api/generate`.
- 10 concurrent HTTP requests against the running server completed
  correctly with no lost writes.

## Known limitation (by design, already discussed)
Credentials are encrypted at rest in the `.db` file using a key derived
from a constant embedded in `storage.py`. This protects the database file
itself (e.g. someone browsing the FSx share directly, or a backup) but
does **not** add any login/access-control to the web app — anyone who can
reach the server's HTTP port can use it normally, and anyone with a copy
of this script can decrypt any copy of the `.db`. That's the explicitly
agreed tradeoff for keeping this simple and dependency-free.

## REST API (for reference while building the frontend)
- `GET  /api/devices` / `POST /api/devices` (upsert) / `DELETE /api/devices/{id}`
- `POST /api/devices/import` — `{devices: [...], mode: "merge"|"replace"}`
- `GET  /api/bandwidth` / `POST /api/bandwidth` / `DELETE /api/bandwidth/{id}`
- `POST /api/bandwidth/import` — same shape as devices/import
- `GET  /api/lists` / `POST /api/lists/{listName}` — `{items: [...]}`
- `GET  /api/lists/{listName}/usage?value=X` — `{count: N}`
- `GET  /api/audit?limit=N`
- `GET  /api/history?limit=N` / `GET /api/history/{id}`
- `POST /api/generate` — runs the conversion + YAML dump, saves a history
  entry, returns `{files, groupStats, missingRegionDevices,
  missingCredsDevices, orphanedBwIps, snmpTotal, icmpTotal, summary}`

All POST bodies accept an optional `"_actor": "name"` field for audit-log
attribution (same model as the old once-per-session prompt()).