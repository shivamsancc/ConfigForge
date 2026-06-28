# Integrations

This directory is reserved for optional integrations that connect ConfigForge
to external systems.

## What belongs here

An integration reaches outside the ConfigForge process — it makes an HTTP call,
queries an external API, polls SNMP, syncs a CMDB, or pushes data to a
monitoring platform. Each integration is a self-contained sub-package:

```
integrations/
    datadog/        Push generated configs directly to the Datadog API
    netbox/         Sync device inventory with a NetBox instance
    snmp_discovery/ Discover devices via SNMP walk and propose additions
    ldap/           Authenticate users against an LDAP/Active Directory server
    servicenow/     Import/export CMDB records from ServiceNow
    slack/          Post generation reports and audit events to a Slack channel
    grafana/        Generate Grafana datasource and dashboard provisioning files
    opentelemetry/  Emit inventory change events as OTel spans
```

## Rules for integrations

1. **The core must never import from integrations.** Integrations are optional;
   the server starts and runs correctly with none of them present.

2. **Each integration is responsible for its own dependencies.** If an integration
   needs `requests`, `ldap3`, or `pysnmp`, it declares and manages that itself —
   the user installs it only if they want that integration.

3. **Graceful degradation.** If an integration's dependencies are not installed,
   it should fail with a clear, actionable error message rather than crashing
   the server. Use a `try/except ImportError` guard in the integration's
   `__init__.py` and print a helpful install hint.

4. **No business logic.** An integration transforms and transmits ConfigForge's
   existing output — it does not compute new results. If transformation logic
   is needed, put the pure function in `formats/` and call it from the integration.

5. **Versioned and idempotent.** If an integration stores state (e.g. a sync
   cursor), it manages that state in the integration's own config/state file,
   never in ConfigForge's core database.

## Current integrations

None yet. This directory is a placeholder establishing the convention before
the first integration is written.
