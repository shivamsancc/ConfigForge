<p align="center">
  <img src=".github/logo.svg" alt="ConfigForge" width="420">
</p>

<p align="center">
  <a href="https://github.com/shivamsancc/ConfigForge"><img alt="repo" src="[https://github.com/shivamsancc/ConfigForge/blob/main/static/logo.svg?logo=github"></a>
  <img alt="status" src="https://img.shields.io/badge/status-active-brightgreen">
  <img alt="python" src="https://img.shields.io/badge/python-3.8%2B-blue">
  <img alt="dependencies" src="https://img.shields.io/badge/dependencies-zero-success">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-lightgrey">
</p>

<p align="center">
  A shared, self-hosted tool for generating Datadog SNMP/ICMP collector config YAML<br>
  from a team-maintained inventory of network devices, bandwidth caps, and subnets &mdash;<br>
  with a fully dynamic, user-defined tagging system for organizing everything your own way.
</p>

---

## Why this exists

Network teams often track device inventory in a spreadsheet and hand-roll monitoring
config from it. ConfigForge replaces that with a small shared web server: one person
runs it on an always-on machine, and everyone on the team opens it in a browser to
manage the same dataset together &mdash; no per-person spreadsheet copies, no merge
conflicts, no "whose version is current?"

## Features

- **Devices, Bandwidth Capping, and Subnets** &mdash; full CRUD for your inventory,
  with both a table view and a card view, instant client-side search on every page,
  and a responsive layout down to mobile.
- **Generate YAML** &mdash; one config file per Collector Region, built from your
  current devices and bandwidth caps, with live preview and download. Devices
  configured for ICMP or SNMP Trap automatically skip the SNMPv3 credential form
  entirely, since they don't need it.
- **Fully dynamic tags** &mdash; Collector Region is the one categorization that's
  permanently built in (it's mandatory and drives generation). Everything else
  &mdash; Device Class, Region, Environment, Country, or anything you invent &mdash;
  is created on demand through **Manage Tags**, not hardcoded. A tag only exists
  once you create it, and it only shows up as a field on Devices, Bandwidth
  Capping, and/or Subnets if you say it should.
- **One tag, many sections** &mdash; a tag can apply to Devices, Bandwidth Capping,
  and Subnets all at once, sharing a single value list across every section it's
  enabled for. Define "Environment" once, use it everywhere.
- **Subnet-based tag inheritance** &mdash; tag a subnet by CIDR, and any device
  whose IP falls inside that range automatically inherits the tag for any value it
  doesn't already set itself. The matched subnet is also written into the
  generated YAML (`subnet: 10.1.1.0/24`) so it's traceable from the output alone.
- **Excel import/export** &mdash; export your current data as an `.xlsx` template
  (including your custom tag columns), edit it offline, and re-import with a merge
  or replace mode. Credential column headers are alias-tolerant (`Auth Key`,
  `authKey`, `AuthKey` all map to the same field), and rows with an invalid IP or
  CIDR are skipped with a clear count rather than silently corrupting your data.
- **Dependency-checked deletion** &mdash; removing a tag, a tag value, or a
  Collector Region that's still in use warns you with the affected record count
  before letting you proceed.
- **IP address validation** &mdash; both client-side (instant feedback while
  typing) and server-side (so a bad value can't sneak in through the API directly).
- **Dashboard** &mdash; inventory totals, breakdowns by Collector Region and any
  custom tag (correctly accounting for subnet-inherited values, not just
  directly-stored ones), plus a recent-activity feed.
- **Audit log + YAML history** &mdash; every change is attributed to whoever made
  it (a one-time name prompt remembered in your browser, not a login system), and
  every generation is saved so you can look back at what was produced and when.
- **Zero pip dependencies.** Everything &mdash; the HTTP server, the SQLite
  storage layer, AES-256-GCM credential encryption, the YAML serializer, and the
  `.xlsx` reader/writer &mdash; is implemented against the Python standard library
  only. This is deliberate: ConfigForge is built to run on a locked-down machine
  with no internet access and no ability to `pip install` anything.
- **Safe upgrades.** Every schema change ships as a versioned, idempotent
  migration that runs automatically on server startup (see
  [Upgrading](#upgrading) below) &mdash; updating to a new version is just
  "copy in the new files, restart."

## Quickstart

```bash
python3 server.py
```

That's it. This starts the server on port 8420 with a local `configforge.db` file
next to the script, and opens your default browser to it automatically.

To point it at a shared network drive so a whole team shares one dataset, or to
change the port:

```bash
python3 server.py --db /path/to/shared/configforge.db --port 8420
```

Run `python3 server.py --help` for the full list of options (`--host`,
`--no-browser`, etc).

**Requirements:** Python 3.8+. Nothing else &mdash; no `pip install` needed.

## Upgrading

Updating ConfigForge is: copy the new `.py` files over the old ones, restart the
server. That's the whole process &mdash; no manual migration script to remember,
no risk of forgetting a step.

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

## How credentials are protected

SNMPv3 `authKey`/`privKey` values are encrypted at rest with AES-256-GCM, using a
key embedded in `storage.py`. This protects the raw `.db` file itself (e.g. if
someone copies it off a shared drive or finds it in a backup) but is **not** an
access-control mechanism for the running app &mdash; anyone who can reach the
server's HTTP port can use it normally, the same way anyone with the original
spreadsheet could read it. This is a deliberate, documented tradeoff in favor of
staying simple and dependency-free; if your environment needs real authentication,
put ConfigForge behind a reverse proxy or VPN.

## Architecture

```
server.py       entry point -- argument parsing, runs migrations, opens the browser, starts the HTTP server
handler.py      REST API (devices/bandwidth/subnets/tags/lists/audit/history/generate/export)
storage.py      SQLite (WAL mode), credential encryption, CIDR matching, usage-count helpers
migrations.py   versioned, idempotent schema migrations -- see "Upgrading" above
logic.py        core conversion: groups devices by Collector Region, resolves tags, builds YAML-ready dicts
yamldump.py     pure-Python YAML serializer matching PyYAML's default output
aesgcm.py       pure-Python AES-256-GCM (zero dependencies)
xlsxwriter.py   pure-Python .xlsx writer (zero dependencies)
static/         the frontend: plain HTML/CSS/JS, no build step, no CDN
```

The frontend is intentionally framework-free &mdash; plain HTML/CSS/JS served as
static files, with [SheetJS](https://sheetjs.com/) vendored locally for `.xlsx`
parsing. There's no build step: edit a `.js` file, refresh the browser.

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

See the docstring at the top of `handler.py` for the complete request/response
contract.

## Contributing

Issues and pull requests are welcome at
[github.com/shivamsancc/ConfigForge](https://github.com/shivamsancc/ConfigForge).
A few things worth knowing before you dive in:

- **Any schema change goes in `migrations.py`**, never as an ad-hoc `ALTER` in
  `storage.py`. Add a new numbered `migrate_N` function; never edit an existing
  one after release.
- Keep the zero-pip-dependency constraint for anything in the backend that ships
  by default &mdash; it's the whole point of the project working on locked-down
  machines. If you need a real dependency for an optional feature, gate it behind
  a try/except with a clear fallback message.
- The frontend has no build step on purpose. Please don't introduce one without
  discussing it first &mdash; that's a deliberate tradeoff, not an oversight.
- `yamldump.py` and `aesgcm.py` are both verified against their "real"
  counterparts (PyYAML and pycryptodome) in extensive fuzz tests during
  development. If you touch either file, please re-verify against the real
  library before submitting.

## License

MIT &mdash; see [LICENSE](LICENSE).
