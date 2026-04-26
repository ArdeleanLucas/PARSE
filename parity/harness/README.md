# PARSE parity diff harness

Single end-to-end oracle-vs-rebuild parity runner.

## Why this exists

This harness replaces the old plan of writing one evidence doc per surface. Instead of separate Tags / Import / Compute / Job-diagnostics writeups, it runs the same fixture against both repositories and compares:

- API responses
- async job lifecycle traces
- LingPy and NEXUS exports
- persisted JSON artifacts in the workspace

## Current Round 2 scope

The shared fixture now exercises every §6 contract group in `docs/plans/option1-parity-inventory.md` via deterministic, report-only probes. The emitted `report.json` includes a `coverage` section that maps each contract group to the concrete scenario keys used for Round 2 sign-off.

1. annotation data (`GET/POST /api/annotations`, `GET /api/stt-segments`)
2. project config + pipeline state (`GET/PUT /api/config`, `GET /api/pipeline/state/{speaker}`)
3. enrichments / tags / notes / imports
4. auth status + poll/logout + invalid key failure envelope
5. STT / normalize / onboard job lifecycle coverage
6. offset detect-from-pair + apply
7. suggestions + lexeme search
8. chat session surfaces + invalid chat run / unknown status failure handling
9. generic compute (`full_pipeline`) + job observability
10. export + media contract (`LingPy`, `NEXUS`, spectrogram URL shape)
11. CLEF config/catalog/providers/report + contact-lexeme fetch

### Round 2 operation breadth

The sequential scenario also covers the explicit Round 2 user-facing surfaces:

- CSV concept import
- speaker onboard
- CLEF config + fetch
- batch transcription run (`full_pipeline` contract path)
- LingPy + NEXUS export with cognate decisions saved in enrichments
- tag merge
- enrichment / lexeme-note save-load

### Failure-mode coverage

The harness asserts matching **status code + error envelope** for at least these negative paths:

- invalid annotation save
- missing speaker
- malformed CLEF config
- export with empty wordlist (LingPy 500, plus current NEXUS zero-character behavior)

## Canonicalization + allowlist

Round 2 adds:

- `canonicalization.md` — float rounding, stable list sorting, UUID masking, path relativization, timestamp masking
- `allowlist.yaml` — explicit accepted-diff rules only; permanent rules must carry a real reason + `reason_ref`
- `SIGNOFF.md` — sign-off template with diff counts, allowlist counts, and P0/P1 coverage checkboxes

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
- `workspace/project.json`
- `workspace/source_index.json`
- `workspace/concepts.csv`
- `workspace/parse-enrichments.json`
- `workspace/annotations/Base01.parse.json`
- `workspace/annotations/Base02.parse.json`

`prepare_fixture_bundle()` also synthesizes deterministic silent WAVs at runtime so the repo does not need to carry binary audio fixtures.

## CI

GitHub Actions runs two parity-harness checks:

1. fast unit coverage for the harness module
2. a report-only end-to-end oracle-vs-rebuild run with artifacts uploaded from `parity/harness/output/ci/`

The CI summary reports:

- raw diff count
- allowlisted diff count
- remaining unallowlisted diff count

The long-term rule remains the same: extend this one harness instead of spawning new one-off parity evidence docs.
