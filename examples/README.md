# Examples

This directory contains reference material that makes ConfigForge easier to
understand and verify. All files here are safe to delete — they are learning
resources, not application code.

---

## What belongs here

### Sample databases

SQLite database files (`.db`) pre-populated with realistic device, bandwidth,
subnet, and tag data. A sample database lets a new contributor or evaluator
run ConfigForge immediately without entering data by hand.

Run a sample database directly:

```bash
python3 server.py --db examples/sample.db --no-browser
```

### Sample Excel files

`.xlsx` import files demonstrating the expected column layout for:

- Devices (`devices_template.xlsx`)
- Bandwidth capping (`bandwidth_template.xlsx`)
- Subnets (`subnets_template.xlsx`)

These are the same files produced by the export endpoints
(`/api/export/devices.xlsx`, etc.), so they also serve as format documentation.

### Sample generated YAML

YAML files produced by clicking **Generate YAML** against a sample database.
Commit these alongside the `.db` file that produces them. They serve as a
lightweight regression reference: if generation logic ever changes unintentionally,
the same input will no longer produce the same YAML.

Suggested naming:

```
examples/
    sample.db
    sample_aws_mumbai.yaml
    sample_eu_west.yaml
```

### Sample screenshots

Screenshots of the UI showing the dashboard, the device table, the Network Tree,
and the Generate YAML view. These belong in `examples/screenshots/` and are
referenced from the project README. They require no maintenance until the UI
changes.

---

## Convention for contributors

When adding an example:

1. **Name it clearly** — `sample.db` is fine for a generic example; use a
   descriptive name (`multiregion.db`, `icmp_only.db`) when the example
   illustrates a specific scenario.

2. **Commit the expected output alongside the input.** For every `.db` file,
   run Generate YAML and commit the resulting `.yaml` files next to it. This
   creates a regression baseline.

3. **Keep examples small.** A sample database with 10–20 devices across 2–3
   Collector Regions covers every interesting code path. Hundreds of rows add
   no value.

4. **Do not commit real credentials.** Use placeholder values (`authKey: CHANGEME`)
   in any sample database or spreadsheet. The AES-256-GCM encryption in
   `core/aesgcm.py` protects credentials in a real database; example files are
   committed to a public repository.
