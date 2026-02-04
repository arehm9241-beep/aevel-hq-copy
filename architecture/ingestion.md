# SOP: Data Ingestion

## Purpose

Load raw data from the configured source (file path or URL) into a known format and write to `.tmp/` for downstream tools. No transformation of values; only structural normalization (e.g. CSV → JSON).

## Inputs

- **Environment**: `DATA_SOURCE_PATH` (local file) or `DATA_SOURCE_URL` (HTTP/HTTPS). At least one must be set for pipeline runs.
- **Optional**: `DATA_SOURCE_FORMAT` — `json` (default) or `csv`.

## Outputs

- **File**: `.tmp/raw_input.json` — JSON conforming to Raw Input schema in gemini.md (schema_version, records, metadata).
- **Exit**: 0 on success; non-zero on failure (file missing, URL unreachable, invalid format).

## Edge Cases

- If both `DATA_SOURCE_PATH` and `DATA_SOURCE_URL` are set, path takes precedence.
- If source is CSV, first row is headers; map to records with id, timestamp, source, metrics (visits, conversions, revenue).
- Empty file or empty records array: output valid JSON with `records: []` and metadata.
- URL returns 4xx/5xx: fail fast, exit non-zero, do not write partial output.
- Invalid JSON/CSV: fail fast, exit non-zero.

## Golden Rule

SOP updated before any change to ingest_data.py behavior.
