<p align="center">
  <img src="/static/logo.svg" alt="ConfigForge" width="100%">
</p>

<p align="center">
  <a href="https://github.com/shivamsancc/ConfigForge"><img alt="repo" src="https://img.shields.io/badge/github-shivamsancc%2FConfigForge-181717?logo=github"></a>
  <img alt="status" src="https://img.shields.io/badge/status-active-brightgreen">
  <img alt="python" src="https://img.shields.io/badge/python-3.8%2B-blue">
  <img alt="dependencies" src="https://img.shields.io/badge/dependencies-zero-success">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-lightgrey">
</p>

<p align="center">
  A shared, self-hosted tool for generating Datadog SNMP/ICMP collector config YAML<br>
  from a team-maintained inventory of network devices, bandwidth caps, and subnets &mdash;<br>
  with a fully dynamic tagging system and a live, zoomable diagram of how it all connects.
</p>

---

## Why this exists

Network teams often track device inventory in a spreadsheet and hand-roll monitoring
config from it. ConfigForge replaces that with a small shared web server: one person
runs it on an always-on machine, and everyone on the team opens it in a browser to
manage the same dataset together &mdash; no per-person spreadsheet copies, no merge
conflicts, no "whose version is current?"

## Features

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

### Network Tree

A live, zoomable diagram of your whole network &mdash; Subnets on the left,
branching to the Devices inside each one, branching to that device's Bandwidth
Capping rows on the right. It's a real spatial diagram, not a list: cards
connected by curved lines, built for exploring hundreds of devices without
getting lost.

- **Pan and zoom, Google-Maps style** &mdash; scroll or pinch to zoom in on the
  cursor, click-drag the background to pan, with on-screen +/&minus;/reset
  controls. Each column also scrolls independently within itself, so a bucket
  with hundreds of devices stays fully navigable without the whole diagram
  becoming unusably tall.
- **Click to drill in, click again for details** &mdash; click a subnet to reveal
  its devices; click a device to reveal its bandwidth rows. Click the
  already-selected card again to open a details panel with an **Edit** button,
  which opens the exact same edit form used everywhere else in the app &mdash;
  editing from the diagram updates your data immediately, without leaving the
  page.
- **Hover to trace a connection** &mdash; hovering a subnet or device highlights
  the connector lines down to everything beneath it, animated with a flowing-dash
  effect so you can see at a glance which devices and bandwidth rows belong to
  what.
- **At-a-glance bandwidth indicator** &mdash; every device card shows a small
  badge: a green count if it has bandwidth capping configured, a muted dash if it
  doesn't.
- **Unassigned buckets** &mdash; devices whose IP doesn't fall inside any subnet,
  and bandwidth rows whose IP doesn't match any device, show up in their own
  clearly-marked buckets rather than disappearing silently.
- **Filter bar with `key:value` queries** &mdash; type something like
  `collector_region:india` or `country:"AWS US"` (quote multi-word values), or
  use the dropdowns next to it for the same filters without typing. Filtering
  narrows which subnets/devices appear; it never changes the diagram's shape.

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
- **Subnet-based tag inheritance** &mdash; tag a subnet by CIDR, and any device
  whose IP falls inside that range automatically inherits the tag for any value it
  doesn't already set itself. The matched subnet is also written into the
  generated YAML (`subnet: 10.1.1.0/24`) so it's traceable from the output alone.
- **Dependency-checked deletion** &mdash; removing a tag, a tag value, or a
  Collector Region that's still in use warns you with the affected record count
  before letting you proceed. Deleting a tag definition never deletes the records
  that used it &mdash; only the tag reference on them.

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
server.py          entry point -- argument parsing, runs migrations, opens the browser, starts the HTTP server
handler.py         REST API (devices/bandwidth/subnets/tags/lists/audit/history/generate/export)
storage.py         SQLite (WAL mode), credential encryption, CIDR matching, usage-count helpers
migrations.py      versioned, idempotent schema migrations -- see "Upgrading" above
logic.py           core conversion: groups devices by Collector Region, resolves tags, builds YAML-ready dicts
yamldump.py        pure-Python YAML serializer matching PyYAML's default output
aesgcm.py          pure-Python AES-256-GCM (zero dependencies)
xlsxwriter.py       pure-Python .xlsx writer (zero dependencies)
static/
  app.js            shell: routing, global state, sidebar/topbar, theme toggle
  devices.js         Devices view
  bandwidth.js        Bandwidth Capping view
  subnets.js          Subnets view
  tags.js             Manage Tags view (create/scope/delete tag definitions)
  lists.js            Manage Lists view (Collector Region + every tag's value list)
  networktree.js      Network Tree: the pan/zoom diagram, filtering, hover-trace, details popups
  tablecontrols.js     shared client-side sort + pagination, used by Devices/Bandwidth/Subnets
  tagfields.js         shared dynamic-tag rendering, used by every section's forms and tables
  dashboard.js         Dashboard view
  generate.js          Generate YAML view
  history.js / audit.js  YAML History / Audit Log views
  api.js              thin fetch() wrapper for every backend endpoint
  ui.js               icons, toasts, modals, shared helpers
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
| `GET` | `/api/subnets` | List all subnets |
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
- `networktree.js`'s pan/zoom clamps panning and zooming so content can never
  drift fully out of view (see `clampZoomToContent`). If you touch the zoom
  math, test with a real button-click zoom-in followed by selecting a large
  bucket &mdash; that combination is what originally exposed the bug this
  guards against.

## License

MIT &mdash; see [LICENSE](LICENSE).
