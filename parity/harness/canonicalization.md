> **Historical (post-cutover 2026-04-27).** The rebuild→canonical cutover is complete and the CI parity step is now a no-op gate; these harness docs remain only as historical reference plus regression-test context.

# PARSE parity harness canonicalization rules

The parity harness compares oracle vs rebuild after canonicalization so volatile runtime noise does not drown real contract drift.

## Scalar normalization

- **Floating-point timestamps / durations**: round all floats to **6 decimal places**.
- **Generated UUIDs**: mask UUID-looking values as `<uuid>`.
- **Job identifiers**: mask `jobId` / `job_id` values as `<job-id>`.
- **Timestamp metadata fields**: mask fields such as `created`, `modified`, `startedAt`, `completed_at`, `updatedAt`, and ISO-8601 timestamp strings as `<timestamp>`.
- **Absolute paths**: relativize paths under the active oracle/rebuild repo roots and temp workspaces to placeholders like `<oracle-workspace>/...` or `<rebuild-repo>/...`.
- **Path separators**: normalize `\` to `/` before comparison.

## Order normalization

Sort only order-insensitive lists by a stable key:

- tag arrays → `id`, then `label`
- tag concept lists / other scalar label lists → lexical order
- `source_wavs` arrays → `filename`/`path`, then `is_primary`
- job lock resource arrays → `kind`, then `id`

## Do not sort

These arrays are semantically ordered and must remain in runtime order:

- interval timelines (`tiers.*.intervals`)
- job state progressions (`states`)
- log streams (`logs`)
- offset / anchor match lists (`matches`)

## Allowlist interaction

Canonicalization runs **before** allowlist matching.
That means allowlist rules should target canonical JSON paths, not raw volatile values.

## Reporting

Every diff report must include:

- raw diff count
- allowlisted diff count
- remaining unallowlisted diff count
- exact diff path(s)
- allowlist rule id + reason when a rule matched
