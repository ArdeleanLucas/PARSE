# MC-384 compute architecture release notes

> Last updated: 2026-05-14. Covers the MC-384 series that landed across PRs #411–#440.

## Summary

MC-384 turns PARSE long-recording compute from monolithic best-effort model calls into an inspectable, chunk-aware, subprocess-isolated architecture. The fieldwork motivation was simple: Khan01/Fail01-scale recordings should not crash the parent backend, silently stop after a decoder loop, or leave users guessing which part of a file succeeded.

## User-visible improvements

- **Reliable long-file STT and ORTH** — full-file STT and full-mode ORTH now split recordings longer than 10 minutes into adjacent Tier-1 chunks by default.
- **Chunk progress in the UI** — active job progress messages such as `STT chunk 2/7 (600s–1200s)` and `ORTH chunk 2/7 (600s-1200s)` are surfaced as chunk progress instead of a generic spinner.
- **Partial-result reporting** — batch reports can distinguish all-green, partial, errored, and cancelled chunk outcomes instead of flattening everything into one success/failure cell.
- **Safer parent backend** — full-file STT, full-mode ORTH, and full-mode IPA run inside nested isolated subprocesses, so crashes/OOMs are serialized into job errors instead of killing the server process.
- **Clearer device control** — STT, ORTH, and IPA now share the same device resolver (`python/ai/device.py`) with global and per-stage environment overrides.
- **IPA coverage warning** — destructive IPA overwrite reruns now report `coverage_shrink_warning` when newly projected coverage is much shorter than existing IPA coverage.
- **Better long-run logs** — STT/ORTH/IPA completion summaries include the effective device and chunk count/coverage where applicable.

## Behavior changes and compatibility notes

| Area | Change | Compatibility note |
|---|---|---|
| STT chunking | Full-file STT chunks at `PARSE_STT_DEFAULT_CHUNK_MINUTES=10` by default. | `coarse_transcripts/<speaker>.json` remains a flat merged `segments[]` cache; `chunks[]` is job-result-only. Set `PARSE_STT_DEFAULT_CHUNK_MINUTES=0` only for controlled old-path debugging. |
| ORTH chunking | Full-mode ORTH chunks Tier-1 transcription at `PARSE_ORTH_DEFAULT_CHUNK_MINUTES=10`, then runs Tier 2 once over the merged segments. | Scoped/concept-window ORTH stays fast and unchunked. Set `PARSE_ORTH_DEFAULT_CHUNK_MINUTES=0` only for controlled old-path debugging. |
| Subprocess isolation | Full-file STT, full-mode ORTH, and full-mode IPA are wrapped in nested isolated subprocess helpers even when the outer compute launcher is `thread`. | `PARSE_COMPUTE_MODE=subprocess` is still a separate outer launcher choice; nested isolation is selected by compute intent. |
| Device resolver | `PARSE_{STAGE}_DEVICE` → `PARSE_COMPUTE_DEVICE` → config `device` → `auto`. | Accepted values: `auto`, `cpu`, `cuda`, `cuda:N`. Explicit unavailable CUDA falls back to CPU with a warning. |
| `PARSE_STT_FORCE_CPU` | Preserved as a truthy alias for `PARSE_STT_DEVICE=cpu`. | Existing CPU fallback scripts still work. Prefer `PARSE_STT_DEVICE=cpu` in new docs/scripts. |
| `wav2vec2.allow_wsl_cuda` | Missing/true now allows wav2vec2/IPA to use the unified resolver; explicit false still forces CPU. | Existing copied configs that set `allow_wsl_cuda:false` remain conservative. Remove or set true to let `PARSE_IPA_DEVICE`/`PARSE_COMPUTE_DEVICE` choose CUDA on WSL. |
| IPA overwrite shrink warning | `PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC=60` by default. | Warning is returned in job results as `coverage_shrink_warning`; it does not block the run. Set `0` to disable. |

## New and changed environment variables

- `PARSE_STT_DEFAULT_CHUNK_MINUTES` — default `10`; `0` disables STT duration chunking.
- `PARSE_ORTH_DEFAULT_CHUNK_MINUTES` — default `10`; `0` disables ORTH duration chunking.
- `PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC` — default `60`; `0` disables IPA shrink warnings.
- `PARSE_COMPUTE_DEVICE` — global STT/ORTH/IPA device override.
- `PARSE_STT_DEVICE`, `PARSE_ORTH_DEVICE`, `PARSE_IPA_DEVICE` — stage-specific device overrides.
- `PARSE_STT_FORCE_CPU` — backwards-compatible STT CPU alias.

Full reference: [Environment variables](../environment-variables.md).

## Result schema updates

Job result payloads can now carry:

- `chunks[]` — per-chunk `idx`, `span`, `status`, and optional `error_code`/`error` for long STT/ORTH jobs.
- `device` — the resolved/effective compute device used by a stage. PR notes may call this `resolved_device`; the current wire key is `device`.
- `coverage_shrink_warning` — IPA overwrite diagnostic with `previous_end`, `projected_end`, and `previous_count`.
- `duration_sec` — STT long-run duration metadata.

`chunks[]` is intentionally diagnostic/job-result data. It is not persisted into the STT cache, and ORTH persists reviewed annotation tiers rather than a chunk cache.

Schema reference: [MCP schema: compute job result shapes](../mcp-schema.md#compute-job-result-shapes).

## PR lineage

| PR | Contribution |
|---|---|
| #411 | Shared audio chunking primitives. |
| #412 | Shared nested isolated subprocess helper and full-mode IPA isolation. |
| #413 | Full-mode ORTH subprocess isolation. |
| #414 | Long-file Tier-1 ORTH chunking. |
| #415 | TypeScript contract tolerance for `chunks[]` and structured error codes. |
| #416 | Initial compute architecture docs and Khan01 regression harness. |
| #417 | Chunk progress UI and partial/all-error batch-report coloring. |
| #420 | STT chunking. |
| #422 | IPA coverage shrink warning. |
| #423 | Synthetic STT chunking fixtures. |
| #425 | Duration/coverage refresh around long-audio pipeline state. |
| #426 | Gated real-WAV long-audio STT regression. |
| #427 | `chunks[]` result/cache split and UI progress contract hardening. |
| #428 | Full-file STT subprocess isolation. |
| #429 | compute.md drift guard for env vars/subprocess wrappers. |
| #430 | Integration-test repair after adjacent MC-384 merges. |
| #431 | ORTH Tier-2 fallback preserves the Tier-1 no-parrot pick on alignment failure. |
| #432 | Restored torch-tensor contract at the Tier-2 forced-align boundary. |
| #440 | Unified compute device resolver and per-stage GPU controls. |

## Operator guidance

- For ordinary fieldwork, keep default 10-minute STT/ORTH chunks.
- For one fragile recording, lower the chunk size before rerunning the failed stage rather than disabling chunking.
- Treat `done=true` in pipeline state as "has some intervals," not "covered the full WAV"; check `full_coverage` and `coverage_fraction` before signing off a speaker.
- Read `job_logs` when a chunk reports `oom_suspect`, `timeout`, or `provider_error`; the failed chunk's `span` tells you what interval needs attention.
- If IPA unexpectedly runs on CPU, inspect `PARSE_IPA_DEVICE`, `PARSE_COMPUTE_DEVICE`, `wav2vec2.device`, and whether `wav2vec2.allow_wsl_cuda` is explicitly false.

## Related docs

- [Compute architecture](../architecture/compute.md)
- [Worker process architecture](../architecture/worker-processes.md)
- [Environment variables](../environment-variables.md)
- [Processing long recordings](../user-guides/processing-long-recordings.md)
- [Troubleshooting long files](../troubleshooting/long-files.md)
- [Migration notes](../getting-started/migration.md)
- [MCP schema: compute job result shapes](../mcp-schema.md#compute-job-result-shapes)
