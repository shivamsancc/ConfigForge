# ConfigForge Frontend

## Deploying

Drop everything in `static/` into the backend's `static/` folder (the one
`server.py` serves from — currently empty). Nothing else to configure;
it's plain HTML/CSS/JS with zero build step and zero CDN dependency
(SheetJS is vendored locally as `xlsx.full.min.js`), so it works fully
offline.

```
cp static/*.html static/*.js static/*.css /path/to/yaml-server/static/
```

Then open `http://<server>:8420/` in a browser.

## Views

- **Devices** — table + add/edit modal, dropdowns for Collector Region /
  Device Class / Device Category / Device Type (sourced from Manage
  Lists), masked SNMPv3 credential fields with show/hide toggle, Excel
  import with sheet picker + merge/replace mode.
- **Bandwidth Capping** — same CRUD + import pattern, all free-text fields.
- **Manage Lists** — add/remove items per list; removing a value in use
  shows a usage-count warning first (via `GET /api/lists/{name}/usage`)
  but still allows the removal.
- **Generate YAML** — runs `/api/generate`, shows tabbed per-region YAML
  previews with per-group stats and downloads, a toast with SNMP/ICMP
  totals, an automatic popup listing any devices missing SNMPv3
  credentials, a persistent banner for the same (visible even after the
  popup is dismissed), a "View list" link for devices missing Collector
  Region, and a low-priority stats line for skipped/orphaned rows.
- **YAML History** — list of past generations, click through to the full
  snapshot.
- **Audit Log** — flat list of logged actions with a formatted details
  blob.

## Editor name / attribution

Once per browser session (`sessionStorage`), the app prompts for a name
and sends it as `_actor` on every write. Purely for audit-log
attribution — there's no login or access control.

## What's been tested

Ran end-to-end against a mock backend (same documented API contract,
in-memory instead of SQLite) using Playwright, with zero console/page
errors across:

- Add devices with full creds / missing creds / missing region — badges
  (`SNMP`, `SNMP ⚠`, `missing *`) render correctly
- Password show/hide toggle
- Bandwidth row add, including an orphaned IP with no matching device
- Manage Lists add/remove, including the usage-warning confirm dialog
- Generate: missing-creds modal auto-opens, banners persist after
  dismissal, YAML preview tabs and per-group stats render correctly
- YAML History: entry auto-created by generate, detail view opens
- Audit Log: entries logged for every action above
- **Excel import** for both Devices and Bandwidth: file picker, sheet
  dropdown (including fallback when no sheet is named `devices` /
  `bandwidth_capping`), merge mode, credential column aliasing (e.g.
  `Auth Key` → `authKey`), skipping rows with no IP, and a tricky
  interface name (`Eth 54.200`) surviving import as a string

One thing this hasn't been tested against: the real backend's actual
response shapes for `saveDevice`/`saveBandwidth` (the mock returns
`{device: ...}` / `{bandwidth: ...}` per the documented contract — worth
a quick smoke test against the real `handler.py` once you wire this in,
in case the real responses differ in some field name).
