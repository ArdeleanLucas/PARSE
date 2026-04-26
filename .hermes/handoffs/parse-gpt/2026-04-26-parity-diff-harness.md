---
agent: parse-gpt
queued_by: lucas
queued_at: 2026-04-26
status: executing
---

# parse-gpt task — single parity diff harness

Replace the per-surface parity evidence track with one shared harness under `parity/harness/`.

## Scope

Build a report-only oracle-vs-rebuild runner that uses the same deterministic fixture on both sides and diffs:

- API responses
- LingPy export
- NEXUS export
- persisted JSON artifacts
- async job lifecycle traces

## Acceptance

- runs locally
- emits a markdown + JSON diff report for the current oracle/rebuild state
- includes committed fixture inputs
- ships first-pass automated coverage for the harness module
- runs in GitHub Actions and uploads the current diff artifact while keeping CI green

## Direction

- stop spawning new one-off parity evidence docs for each P1 surface
- extend this harness over time instead
- first-pass scenario should cover import/admin/export flows because they exercise multiple persistence and job surfaces at once
