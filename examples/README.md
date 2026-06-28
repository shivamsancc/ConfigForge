# Examples

This directory contains reference material for ConfigForge:

- Sample database dumps (`.db` files) showing a populated inventory
- Reference YAML output produced by Generate YAML from sample data
- Example import spreadsheets (`.xlsx`) with valid device, bandwidth, and subnet rows
- Edge-case inputs useful for manual testing or future automated tests

## Usage

Example databases can be opened with any SQLite browser or loaded directly:

```bash
python3 server.py --db examples/sample.db --no-browser
```

Example YAML files show the expected output for the corresponding sample data,
so you can verify that generation behavior has not changed after a code change.

## Contributing examples

If you add an example database, also commit the generated YAML it produces
(run Generate YAML and save the output alongside the `.db` file). This creates
a lightweight regression reference: if the same input ever produces different
output, something changed in generation logic.
