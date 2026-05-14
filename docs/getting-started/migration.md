# Migration notes: MC-384 compute architecture

> Last updated: 2026-05-14. This page is for existing PARSE users upgrading from pre-MC-384 long-file behavior to the chunk-aware, subprocess-isolated compute architecture documented in [Compute architecture](../architecture/compute.md).

## What changed

Long-file processing is now safer and more observable by default.

| Area | Previous behavior | Current behavior |
|---|---|---|
| Full-file STT | One provider call could stop early after a decoder loop or fail as one opaque stage. | Full-file STT chunks recordings longer than 10 minutes by default and reports per-chunk outcomes. |
| Full-mode ORTH | Long recordings could OOM the backend during Tier-1 transcription. | Tier-1 ORTH chunks recordings longer than 10 minutes by default, merges results, then runs Tier 2 once. |
| Heavy-stage crashes | Some failures could kill or destabilize the parent backend. | Full-file STT, full-mode ORTH, and full-mode IPA run in nested isolated subprocesses. |
| Job results | Mostly top-level success/error fields. | Results may include `chunks[]`, `device`, `duration_sec`, and IPA `coverage_shrink_warning`. |
| Device selection | Stage/device behavior was split across configs and legacy fallbacks. | STT, ORTH, and IPA share a resolver: stage env → global env → config → `auto`. |

## Do existing users need to change anything?

Usually, no.

If you launch PARSE normally, the new defaults apply automatically:

- `PARSE_STT_DEFAULT_CHUNK_MINUTES=10`
- `PARSE_ORTH_DEFAULT_CHUNK_MINUTES=10`
- full-file STT / full-mode ORTH / full-mode IPA subprocess isolation
- automatic device resolution unless you set env/config overrides

Existing annotation files, STT caches, and enrichments remain readable. The STT cache shape stays backward-compatible: `coarse_transcripts/<speaker>.json` still stores a flat merged `segments[]` list, not `chunks[]`.

## What will feel different

- Long full-speaker runs show chunk progress instead of one long silent provider call.
- A run may finish as **Partial** when some chunks succeeded and others failed.
- Batch reports can show expandable chunk details.
- IPA reruns can warn when projected coverage is much smaller than previous IPA coverage.
- The `device` reported by a stage may now reveal that CUDA fell back to CPU or that a stage-specific override is active.

## New environment variables worth knowing

| Variable | Default | Why you might touch it |
|---|---:|---|
| `PARSE_STT_DEFAULT_CHUNK_MINUTES` | `10` | Lower to `5` for fragile STT; set `0` only for controlled old-path debugging. |
| `PARSE_ORTH_DEFAULT_CHUNK_MINUTES` | `10` | Lower to `5` for ORTH OOM/timeout; set `0` only for controlled old-path debugging. |
| `PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC` | `60` | Set `0` only when expected IPA coverage shrink should not warn. |
| `PARSE_COMPUTE_DEVICE` | `auto` | Force all STT/ORTH/IPA stages to `cpu`, `cuda`, or `cuda:N`. |
| `PARSE_STT_DEVICE` | unset | Override only STT. Useful when STT should stay CPU while ORTH/IPA use CUDA. |
| `PARSE_ORTH_DEVICE` | unset | Override only ORTH. |
| `PARSE_IPA_DEVICE` | unset | Override only IPA when `wav2vec2.allow_wsl_cuda` is not explicitly false. |
| `PARSE_STT_FORCE_CPU` | unset | Legacy STT-only alias for CPU fallback. Prefer `PARSE_STT_DEVICE=cpu` in new scripts. |

Full reference: [Environment variables](../environment-variables.md).

## Updating old local configs

Review `config/ai_config.json` on machines that have carried PARSE for a long time.

1. **Device fields:** `stt.device`, `ortho.device`, and `wav2vec2.device` still matter, but environment variables now take precedence.
2. **IPA WSL CUDA gate:** if `wav2vec2.allow_wsl_cuda=false` is present, IPA stays CPU before the unified resolver is consulted. Remove it or set it true only when the local CUDA stack is stable.
3. **STT CPU fallback scripts:** scripts using `PARSE_STT_FORCE_CPU=1` still work. New scripts should prefer `PARSE_STT_DEVICE=cpu`.
4. **Chunk settings:** do not set chunk env vars globally to `0` unless you intentionally want old monolithic behavior.

## How previous full-pipeline jobs behave differently

A full-pipeline request still follows the same stage order, but long-file stages are now more explicit:

```text
full pipeline
  normalize if selected
  STT full-file path
    split long audio into chunks
    transcribe each chunk
    merge chunk-local segments into audio-global time
  ORTH full-mode path
    split Tier-1 long audio into chunks
    merge Tier-1 output
    run Tier 2 forced alignment once over the merged result
  IPA path
    transcribe existing intervals
    warn if overwrite would shrink coverage sharply
```

If a chunk fails, PARSE should continue where the stage contract allows it and return a structured partial result. Existing callers that only read top-level fields still work, but tools and users should prefer the richer fields when diagnosing long runs.

## Safe upgrade checklist

For an existing workspace:

1. Start PARSE normally and open one known speaker.
2. Run pipeline-state/preflight and confirm duration/coverage values look plausible.
3. Run STT or ORTH on one representative long speaker before batching a corpus.
4. Read the batch report and verify chunk details appear for long full-file stages.
5. Confirm the result `device` matches expectations.
6. If IPA warns about coverage shrinkage, inspect upstream STT/ORTH coverage before accepting the new IPA output.
7. Record any machine-specific env vars in your local launch notes.

## Compatibility notes for scripts and agents

- `chunks[]` is diagnostic job-result data; do not expect it in persisted STT cache files.
- `device` is the shipped wire key for the resolved/effective stage device. Some old PR notes called this `resolved_device`.
- `async=false` compatibility routes are deprecated for some compute flows; prefer job-tracked starts and status polling.
- Treat `done=true` in pipeline-state as "there is some output," not proof of full WAV coverage. Check `coverage_fraction` and `full_coverage`.
- For MCP/API automation, read [MCP schema: compute job result shapes](../mcp-schema.md#compute-job-result-shapes).

## When to disable the new behavior

Only duration chunking has a straightforward off switch:

```bash
PARSE_STT_DEFAULT_CHUNK_MINUTES=0 \
PARSE_ORTH_DEFAULT_CHUNK_MINUTES=0 \
./scripts/parse-run.sh
```

Use this for controlled debugging or benchmarking, not routine fieldwork. Subprocess isolation remains part of the robust full-file/full-mode execution path and should not be treated as a user-facing feature to bypass.

## Related docs

- [Processing long recordings](../user-guides/processing-long-recordings.md)
- [Troubleshooting long files](../troubleshooting/long-files.md)
- [Compute architecture](../architecture/compute.md)
- [MC-384 release notes](../release-notes/mc-384-compute-architecture.md)
