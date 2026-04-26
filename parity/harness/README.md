# PARSE parity diff harness

Single end-to-end oracle-vs-rebuild parity runner.

## Why this exists

This harness replaces the old plan of writing one evidence doc per surface. Instead of separate Tags / Import / Compute / Job-diagnostics writeups, it runs the same fixture against both repositories and compares:

- API responses
- async job lifecycle traces
- LingPy and NEXUS exports
- persisted JSON artifacts in the workspace

Current scope is a first-pass shared fixture that exercises:

1. `GET /api/config`
2. `POST /api/concepts/import`
3. `POST /api/tags/import`
4. `POST /api/onboard/speaker` + `POST /api/onboard/speaker/status`
5. `GET /api/annotations/{speaker}`
6. `POST /api/lexeme-notes/import`
7. `GET /api/export/lingpy`
8. `GET /api/export/nexus`

## Local run

From the rebuild repo root:

```bash
PYTHONPATH=. python3 -m parity.harness.runner \
  --oracle-repo /home/lucas/gh/ardeleanlucas/parse \
  --rebuild-repo $(pwd) \
  --output-dir parity/harness/output/local \
  --keep-temp
```

The command is report-only: it exits `0` and writes the current diff instead of failing the run when differences are present.

## Output

- `report.md` — human-readable diff summary
- `report.json` — normalized machine-readable capture bundle
- `oracle-server.log` / `rebuild-server.log` — backend logs for the run
- `oracle-workspace/` / `rebuild-workspace/` when `--keep-temp` is enabled

## Fixture contract

Fixtures live under `parity/harness/fixtures/`:

- `concepts-import.csv`
- `tags-import.csv`
- `onboard-concepts.csv`
- `lexeme-notes.csv`
- `workspace/` seed JSON files

`prepare_fixture_bundle()` also synthesizes a deterministic silent WAV at runtime so the repo does not need to carry binary audio fixtures.

## CI

GitHub Actions runs two parity-harness checks:

1. fast unit coverage for the harness module
2. a report-only end-to-end oracle-vs-rebuild run with artifacts uploaded from `parity/harness/output/ci/`

The long-term plan is to extend this one harness with additional scenarios instead of creating new per-surface parity evidence documents.
