# ConfigForge

A shared, self-hosted tool for generating Datadog SNMP/ICMP collector
config YAML from a team-maintained inventory of network devices,
bandwidth caps, and subnets — with a flexible custom-tagging system for
organizing everything your own way.

![status](https://img.shields.io/badge/status-active-brightgreen) ![python](https://img.shields.io/badge/python-3.8%2B-blue) ![deps](https://img.shields.io/badge/dependencies-zero-success)

## Why this exists

Network teams often track device inventory in a spreadsheet and hand-roll
monitoring config from it. ConfigForge replaces that with a small shared
web server: one person runs it on an always-on machine (or a shared
drive's host), and everyone on the team opens it in a browser to manage
the same dataset together — no per-person spreadsheet copies, no merge
conflicts, no "whose version is current?"

## Features

- **Devices, Bandwidth Capping, and Subnets** — full CRUD for your
  inventory, with both a table view and a card view.
- **Generate YAML** — one config file per Collector Region, built from
  your current devices + bandwidth caps, with live preview and download.
- **Dynamic tags** — define your own tag lists (e.g. `Country`,
  `Environment`, `Business Unit`) and apply them to Devices, Bandwidth
  Capping, and/or Subnets. A tag can be shared across multiple sections
  at once, so you define a value list once and reuse it everywhere it's
  relevant.
- **Subnet-based tag inheritance** — tag a subnet by CIDR, and any device
  whose IP falls inside that range automatically inherits the tag for any
  value it doesn't already set itself.
- **Excel import/export** — export your current data as an `.xlsx`
  template (including your custom tag columns), edit it offline, and
  re-import with a merge or replace mode. Credential column headers are
  alias-tolerant (`Auth Key`, `authKey`, `AuthKey` all map to the same
  field).
- **Dependency-checked deletion** — removing a tag, list value, or tag
  definition that's still in use warns you with the affected record count
  before letting you proceed.
- **Dashboard** — inventory totals, breakdowns by Collector Region,
  Device Class, and any custom tag, plus a recent-activity feed.
- **Audit log + YAML history** — every change is attributed to whoever
  made it (a lightweight per-session name prompt, not a login system),
  and every generation is saved so you can look back at what was
  produced and when.
- **Zero pip dependencies.** Everything — the HTTP server, the SQLite
  storage layer, AES-256-GCM credential encryption, the YAML serializer,
  and the `.xlsx` reader/writer — is implemented against the Python
  standard library only. This is deliberate: ConfigForge is built to run
  on a locked-down machine with no internet access and no ability to
  `pip install` anything.

## Quickstart

```bash
python3 server.py
```

That's it. This starts the server on port 8420 with a local
`configforge.db` file next to the script, and opens your default browser
to it automatically.

To point it at a shared network drive so a whole team shares one
dataset, or to change the port:

```bash
python3 server.py --db /path/to/shared/configforge.db --port 8420
```

Run `python3 server.py --help` for the full list of options
(`--host`, `--no-browser`, etc).

**Requirements:** Python 3.8+. Nothing else — no `pip install` needed.

## How credentials are protected

SNMPv3 `authKey`/`privKey` values are encrypted at rest with AES-256-GCM,
using a key embedded in `storage.py`. This protects the raw `.db` file
itself (e.g. if someone copies it off a shared drive or finds it in a
backup) but is **not** an access-control mechanism for the running app —
anyone who can reach the server's HTTP port can use it normally, the same
way anyone with the original spreadsheet could read it. This is a
deliberate, documented tradeoff in favor of staying simple and
dependency-free; if your environment needs real authentication, put
ConfigForge behind a reverse proxy or VPN.

## Architecture

```
server.py       entry point -- argument parsing, opens the browser, starts the HTTP server
handler.py      REST API (devices/bandwidth/subnets/tags/lists/audit/history/generate/export)
storage.py      SQLite (WAL mode), credential encryption, CIDR matching, usage-count helpers
logic.py        core conversion: groups devices by Collector Region, resolves tags, builds YAML-ready dicts
yamldump.py     pure-Python YAML serializer matching PyYAML's default output
aesgcm.py       pure-Python AES-256-GCM (zero dependencies)
xlsxwriter.py   pure-Python .xlsx writer (zero dependencies)
static/         the frontend: plain HTML/CSS/JS, no build step, no CDN
```

The frontend is intentionally framework-free — plain HTML/CSS/JS served
as static files, with [SheetJS](https://sheetjs.com/) vendored locally
for `.xlsx` parsing. There's no build step: edit a `.js` file, refresh
the browser.

## REST API

All endpoints are under `/api/`. A few representative examples:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/devices` | List all devices |
| `POST` | `/api/devices` | Create or update a device |
| `DELETE` | `/api/devices/{id}` | Delete a device |
| `POST` | `/api/devices/import` | Bulk import (merge or replace) |
| `GET` | `/api/tags` | List all tag definitions |
| `POST` | `/api/tags` | Create or update a tag definition |
| `DELETE` | `/api/tags/{id}` | Delete a tag (409 if in use, unless `?force=true`) |
| `POST` | `/api/generate` | Generate YAML from current data, save a history entry |
| `GET` | `/api/export/devices.xlsx` | Download devices as an Excel template |

See the docstring at the top of `handler.py` for the complete request/
response contract.

## Contributing

Issues and pull requests are welcome. A few things worth knowing before
you dive in:

- Keep the zero-pip-dependency constraint for anything in the backend
  that ships by default — it's the whole point of the project working on
  locked-down machines. If you need a real dependency for an optional
  feature, gate it behind a try/except with a clear fallback message.
- The frontend has no build step on purpose. Please don't introduce one
  without discussing it first — that's a deliberate tradeoff, not an
  oversight.
- `yamldump.py` and `aesgcm.py` are both verified against their "real"
  counterparts (PyYAML and pycryptodome) in extensive fuzz tests during
  development. If you touch either file, please re-verify against the
  real library before submitting.

## License

MIT — see [LICENSE](LICENSE).
