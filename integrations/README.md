# Integrations

This directory is reserved for optional integrations that connect ConfigForge
to external systems. No integrations exist yet. This README is the architectural
contract that every future integration must follow.

---

## Architectural contract

### 1. Integrations are optional

ConfigForge starts, runs, and functions correctly with zero integrations present.
Removing every file in this directory must not affect the server, the API,
the database, or the frontend in any way.

### 2. Core never imports integrations

No file inside `core/`, `formats/`, or `server.py` may import from `integrations/`.
The dependency arrow points one way: integrations may know about core; core must
never know about integrations.

### 3. Integrations may import core

An integration is allowed to call `core.storage`, `core.logic`, `formats.yamldump`,
or any other core module. It reads from the inventory; it does not write back
to it except through the documented storage API (`storage.upsert_device`, etc.).

### 4. Integrations may use third-party libraries

Core is constrained to Python's standard library. Integrations have no such
constraint. If an integration needs `requests`, `ldap3`, `pysnmp`, or `boto3`,
it may declare and use those dependencies freely.

### 5. Core must always function without any integration's dependencies installed

An integration's pip dependencies are the user's choice to install. They must
never be imported unconditionally at server startup. Guard every third-party
import with a `try/except ImportError` and emit a clear, actionable error message:

```python
try:
    import requests
except ImportError:
    raise ImportError(
        "The Datadog integration requires 'requests'.\n"
        "Install it with: pip install requests"
    )
```

### 6. Integrations extend ConfigForge; they never redefine the inventory model

The data model — what a device is, what a bandwidth cap is, what a subnet is,
what a tag is — is owned by `core/`. An integration may read it, filter it,
transform it for transmission, and write back to it through the storage API.
It may not introduce parallel data structures that shadow or replace the
canonical inventory.

### 7. Each integration is a self-contained sub-package

Structure:

```
integrations/
    datadog/
        __init__.py     Entry point; handles ImportError for pip deps
        push.py         Pushes generated configs to the Datadog API
        README.md       Setup instructions, required env vars, usage
    netbox/
        __init__.py
        sync.py
        README.md
```

Each integration's README must document: what it does, what pip packages it
needs, what environment variables or config it reads, and how to run it.

### 8. Integrations never crash the server

If an integration fails at import time (missing dep) or at runtime (API
unreachable, bad credentials), it must fail gracefully. The server process
must continue serving requests. Log the error; do not propagate it to the
HTTP handler layer.

---

## Future integrations

Examples of integrations that would belong here:

| Directory | Purpose |
|---|---|
| `datadog/` | Push generated YAML configs directly to the Datadog API |
| `netbox/` | Sync device inventory with a NetBox CMDB instance |
| `snmp_discovery/` | Walk a subnet via SNMP and propose new device additions |
| `ldap/` | Authenticate or authorise users against an LDAP/AD server |
| `servicenow/` | Import/export CMDB records from ServiceNow |
| `slack/` | Post generation summaries and audit events to a Slack channel |
| `grafana/` | Generate Grafana datasource and dashboard provisioning files |
| `opentelemetry/` | Emit inventory-change events as OpenTelemetry spans |
| `prometheus/` | Expose inventory metrics as a Prometheus scrape endpoint |

---

## Current integrations

None. This directory is a documented placeholder.
