# Compute architecture

This page is the maintainable reference for PARSE compute execution after MC-384 Milestone A. The canonical design input is the local architecture specification at `/mnt/c/Users/Lucas/Desktop/parse/compute-architecture-differentiation-spec.md`.

For the process-level view of the worker changes that landed across PRs #411-#417, see [Worker process architecture](worker-processes.md).

## Overview

PARSE keeps one user-facing compute system but differentiates execution by intent:

- Fast lexeme/concept-window path: scoped work uses `run_mode != 'full'` and/or `concept_ids`; it should avoid long-file chunking overhead and return quickly for interactive fieldwork.
- Robust long-file path: full-speaker/full-pipeline work runs through the job system and, after MC-384 Milestone A, long Tier-1 ORTH/STT transcribe work is chunked so a Khan01/Fail01-scale recording cannot crash ORTH or silently truncate STT.

The guiding rule is intent first, duration second. A full-pipeline request expresses robust intent; a concept-window request expresses fast intent. Duration only decides whether a robust Tier-1 ORTH/STT request needs chunking.

## Compute modes

`python/server_routes/jobs.py:48` defines `_resolve_compute_mode()`. Resolution order is:

1. CLI `--compute-mode` override.
2. `PARSE_USE_PERSISTENT_WORKER=true`, which selects `persistent`.
3. `PARSE_COMPUTE_MODE`, accepting `thread`, `subprocess`, or `persistent`.
4. Default `thread`.

Mode meanings:

- `thread`: legacy in-process background thread. Lowest process overhead, weakest crash containment.
- `subprocess`: per-job process launched by `python/server_routes/jobs.py:362` `_compute_subprocess_entry()`. Better crash containment for the whole job.
- `persistent`: long-lived worker in `python/workers/compute_worker.py` that dispatches jobs through `_dispatch()` at `python/workers/compute_worker.py:409` and can keep models warm.

## Nested subprocess wrappers

MC-384 extends the existing nested-subprocess pattern. PR #412 introduced the shared IPA subprocess envelope and standalone IPA full-mode routing; PR #413 added ORTH isolation, and PR #428 added full-file STT isolation:

- `python/server_routes/jobs.py:291` — `_launch_compute_subprocess()` launches the outer per-job subprocess selected by `PARSE_COMPUTE_MODE=subprocess`.
- `python/server_routes/jobs.py:362` — `_compute_subprocess_entry()` dispatches the outer per-job child process.
- `python/server_routes/annotate.py:3011` — `_full_pipeline_ipa_subprocess_entry()` serializes full-pipeline IPA child outcomes.
- `python/server_routes/annotate.py:3043` — `_speaker_ortho_subprocess_entry()` serializes ORTH child outcomes for isolated full-mode work.
- `python/server_routes/annotate.py:3067` — `_speaker_ipa_subprocess_entry()` serializes standalone speaker-IPA child outcomes.
- `python/server_routes/annotate.py:3286` — `_run_in_isolated_subprocess()` owns spawn, timeout, result-file parsing, and envelope error conversion for nested children.
- `python/server_routes/annotate.py:3401` — `_compute_full_pipeline_ipa_in_subprocess()` delegates full-pipeline IPA to the shared helper.
- `python/server_routes/annotate.py:3414` — `_compute_speaker_ortho_in_subprocess()` wraps standalone/full-pipeline full-mode ORTH calls.
- `python/server_routes/annotate.py:3453` — `_compute_speaker_ipa_in_subprocess()` wraps standalone `compute_type='ipa'` full-mode calls.
- `python/server_routes/media.py:339` — `_run_stt_job_subprocess_entry()` serializes full-file STT child outcomes.
- `python/server_routes/media.py:371` — `_run_stt_job_in_subprocess()` wraps full-file STT in the shared nested helper.

These nested wrappers are separate from `PARSE_COMPUTE_MODE=subprocess`. The outer compute mode chooses how the job is launched; the nested wrappers isolate memory-heavy STT/ORTH/IPA stages inside that job.

## Chunking primitives

PR #411 added `python/workers/audio_chunking.py` as the shared chunking primitive module for robust Tier-1 ORTH and STT paths (84 LoC):

- `python/workers/audio_chunking.py:12` — `ChunkSpan`, the audio-global `{start, end}` span shape.
- `python/workers/audio_chunking.py:18` — `ChunkResult`, the per-chunk result shape used by ORTH/STT job and MCP outputs.
- `python/workers/audio_chunking.py:26` — `split_audio_duration(total_seconds, chunk_seconds)`.
- `python/workers/audio_chunking.py:56` — `merge_chunk_segments(per_chunk_segments, spans)`, which offsets chunk-local segments back into audio-global time.

## Tier-1 vs Tier-2 ORTH

ORTH has two tiers with different memory profiles:

- Tier-1 coarse ORTH uses `provider.transcribe()` and is the Khan01 OOM vector. Current main calls it through `_transcribe_ortho_with_fallback()` and the chunk loop in `python/server_routes/annotate.py:2669`-`2716` for long full-mode files.
- Tier-2 word alignment (`tiers.ortho_words`) runs after coarse ORTH and is already windowed enough for Milestone A. It remains unchanged and recomputes once over the merged Tier-1 result.

MC-384-D uses adjacent chunks with no overlap for Milestone A. The final chunked Tier-1 loop is `python/server_routes/annotate.py:2669`-`2716`: it measures duration, splits with `split_audio_duration()` at `python/server_routes/annotate.py:2677`, runs each temporary slice, records per-chunk status/errors, and merges with `merge_chunk_segments()` at `python/server_routes/annotate.py:2716`.

MC-384-T (PR #431) added the Tier-2 fallback contract: if forced alignment raises, ORTH preserves the Tier-1 no-parrot pick rather than persisting raw Tier-1 text. MC-384-U (PR #432) then fixed the root cause: a numpy ndarray had crossed into a Tier-2 consumer that called `.numel()`, so `python/ai/forced_align.py:565`-`606` now restores the torch-tensor boundary via `_ensure_audio_tensor()` and `_assert_torch_audio()` before `align_word()` consumes audio. The #431 fallback remains defense-in-depth even though #432 restored the tensor contract.

## Tier-1 STT chunking

Long-form full-file STT now mirrors the ORTH Tier-1 duration gate: files longer than the configured chunk size are split into adjacent chunks before `provider.transcribe()` is called. Each chunk gets a fresh decoder state so a repetition loop in one slice cannot poison the rest of the recording.

- **Entry point:** `_run_stt_job()` in `python/server_routes/media.py`.
- **Subprocess wrap:** `_run_stt_job_in_subprocess()` in `python/server_routes/media.py` — full-file STT runs inside the shared isolated subprocess helper from MC-384-B (#412), preventing a hostile chunk from taking down the parent server. The wrap landed in MC-384-N (#428).
- **Dispatcher boundary:** `_compute_stt()` routes `run_mode != 'full'` to `_compute_speaker_stt()`; only full-file STT enters `_run_stt_job()`.
- **Chunk size:** `PARSE_STT_DEFAULT_CHUNK_MINUTES` (default `10`). Invalid values fall back to `10`; `0` disables duration chunking.
- **Short audio (`duration <= chunk_seconds`):** single-shot `provider.transcribe()` path with `chunks: []` in the returned job result.
- **Long audio (`duration > chunk_seconds`):** `split_audio_duration()` creates adjacent spans; temporary chunk WAVs are transcribed one by one; `merge_chunk_segments()` offsets chunk-local segments and words back into audio-global time.
- **Per-chunk errors:** `MemoryError` and CUDA/OOM-style failures classify as `oom_suspect`; timeout-shaped failures classify as `timeout`; other provider failures classify as `provider_error`. The loop records an error row for that chunk and continues to later chunks.
- **Cancellation:** cancellation is checked between chunks. Completed chunks stay `ok`; remaining chunks are reported as `cancelled`; the top-level result carries `status: 'cancelled'`.
- **Cache:** `coarse_transcripts/<speaker>.json` still stores only the merged flat `segments` list, not `chunks[]`, preserving the pre-MC-384-H cache shape.
- **PR:** MC-384-H / #420.

**Why STT chunks now:** before MC-384-H, STT called `provider.transcribe()` once on the entire WAV. In the 2026-05-13 Fail01 investigation, the 2 h 32 min working WAV hit faster-whisper repetition loops on common Kurdish tokens around minute 14; the decoder then advanced past the failure region and stopped after minute 19. Pre-fix STT produced 40 segments covering about 9.5% of the file, while ORTH already covered the full recording because MC-384-D had chunked its Tier-1 path. PR #420 brings STT to the same long-file parity contract: later chunks still run, partial/error/cancel rows are explicit in `chunks[]`, and the merged segment cache remains backward-compatible.

**IPA does not chunk by audio duration:** IPA Tier-3 acoustic transcribe is interval-driven, not a single whole-file model call. `python/ai/ipa_transcribe.py:transcribe_intervals()` operates on per-interval slices supplied by upstream ORTH word windows, and PR #422 handled IPA shrink-warning behavior separately. This is why no MC-384-K audio-duration chunking lane exists for IPA.

## Environment variables

- `PARSE_ORTH_DEFAULT_CHUNK_MINUTES`: MC-384-D default chunk size for long ORTH Tier-1; default `10`. Read by `_ortho_default_chunk_seconds()` at `python/server_routes/annotate.py:811` and exported by `scripts/parse-run.sh:102` / `scripts/parse-run.sh:399`.
- `PARSE_STT_DEFAULT_CHUNK_MINUTES`: MC-384-H default chunk size for long STT Tier-1; default `10`. Read by `_stt_default_chunk_seconds()` at `python/server_routes/media.py:66` and exported by `scripts/parse-run.sh:104` / `scripts/parse-run.sh:400`.
- `PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC`: MC-384-J2 guard for destructive IPA overwrite reruns; default `60`. Read by `_ipa_overwrite_shrink_threshold_sec()` at `python/server_routes/annotate.py:1980`. This is not an audio-duration chunking knob; it belongs with the compute env-var surface because full-pipeline IPA can surface `coverage_shrink_warning` when newly projected STT/ORTH coverage is much shorter than existing IPA coverage.
- `PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC`: existing hard timeout for compute subprocesses; used by `python/server_routes/jobs.py:320` for per-job subprocess mode and by `python/server_routes/annotate.py:3292` for nested isolated subprocesses, default `14400`.
- `PARSE_USE_PERSISTENT_WORKER`: shortcut selecting persistent worker mode; read by `python/server_routes/jobs.py:61` and documented in `scripts/parse-run.sh:27`.
- `PARSE_COMPUTE_MODE`: explicit compute launcher mode; read by `python/server_routes/jobs.py:63` and documented in `scripts/parse-run.sh:28`.
- `PARSE_FULL_PIPELINE_MIN_MEM_GB`: full-pipeline host-memory preflight threshold; read by `python/server_routes/annotate.py:2837` and documented in `scripts/parse-run.sh:30`.

## Subprocess timeout configuration

`PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC` defaults to `14400` seconds (4 hours). PR #412 changed nested isolated subprocess timeout handling in `python/server_routes/annotate.py:3292` / `python/server_routes/annotate.py:3322`-`3328`: any positive finite value is respected exactly. The previous 60-second minimum floor was removed for the nested wrapper, so test and debug runs can use values such as `1` second. Values that are zero, negative, non-finite, missing, or unparsable fall back to `14400`.

The older per-job `PARSE_COMPUTE_MODE=subprocess` launcher still reads the same variable at `python/server_routes/jobs.py:320`; its floor behavior is separate from the nested helper and should be audited before changing that outer launcher contract.

## Subprocess result envelope

`_run_in_isolated_subprocess()` (`python/server_routes/annotate.py:3286`) uses an internal JSON envelope where child entries write `{ok: true, result: ...}` for successful computations and `{ok: false, error: ..., traceback: ...}` for child failures. `_compute_full_pipeline_ipa_in_subprocess()` (`python/server_routes/annotate.py:3401`) then treats `sub_result.get('status') == 'error'` as the hard subprocess-error sentinel generated by `_isolated_subprocess_error_result()` (`python/server_routes/annotate.py:2957`).

Contract for subprocess entries: a successful computation must not return a dict whose `status` field is the literal string `error`. If application-level partial failure needs to be surfaced, use a different key such as `failure_reason` or `partial`, or raise and let the subprocess envelope convert the failure. Returning `status='error'` from successful application code collides with the envelope sentinel.

## When chunking fires

| User/API intent | Duration | Flags/env | Expected path |
| --- | ---: | --- | --- |
| Concept-window ORTH (`run_mode != 'full'`) | any | default | Fast scoped path; no chunking. |
| Full-pipeline ORTH, short audio | at or below `PARSE_ORTH_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Robust wrapper may run, but `chunks` is empty or a single non-chunked result depending on MC-384-D implementation. |
| Full-pipeline ORTH, long audio | greater than `PARSE_ORTH_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Tier-1 ORTH chunks, each isolated; Tier-2 recomputes once after merge. |
| Full-file STT, short audio | at or below `PARSE_STT_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Single-shot `_run_stt_job()` path; `chunks: []`. |
| Full-file STT, long audio | greater than `PARSE_STT_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Tier-1 STT chunks; per-chunk results emitted in `chunks[]`, merged cache remains flat segments. |
| Full-file STT with chunking disabled | any | `PARSE_STT_DEFAULT_CHUNK_MINUTES=0` | Single-shot STT regardless of duration; `chunks: []`. |
| Scoped/concept-window STT (`run_mode != 'full'`) | any | payload scope | `_compute_speaker_stt()` path; windows are already bounded, so no audio-duration chunking. |
| MCP/agent full ORTH with `force_robust=true` | any | payload flag | Robust path; duration still decides whether the robust path chunks. |
| MCP/agent scoped ORTH with `fast_mode=true` or `concept_ids` | any | payload flag/scope | Fast scoped path; no chunking. |
| Cancel requested mid-run | long audio | job cancel flag | Between-chunk polling only for Milestone A; completed chunks remain ok, remaining chunks report cancelled. |

## Khan01 incident summary

Khan01 is the motivating fieldwork failure: a 1.6 GB concatenated WAV, roughly 4.5 hours, killed the backend during full-file ORTH. Memory preflight passed at job start, but peak ORTH inference exceeded WSL memory headroom. IPA already had nested subprocess protection; ORTH did not.

MC-384 Milestone A closes the incident by containing long ORTH work in isolated subprocesses and splitting Tier-1 transcribe into default 10-minute chunks. A chunk-level failure produces structured result data instead of taking down the parent server.

## Result contract

Chunked compute results add a `chunks` array with per-chunk status. See `docs/mcp-schema.md` for the agent-facing schema. Backward-compatible callers that only read the top-level `status`, `filled`, `total`, `segments`, and `ortho_words` fields continue to work.

STT preserves its cache contract: `_write_stt_cache()` receives the merged flat `segments` list only, while `chunks[]` remains a job-result diagnostic envelope.

PR #417 added two UI consumers of this same contract: the header job strip parses `ORTH chunk N/M (STARTs-ENDs)` progress messages into a live `Chunk N of M` pill, and the batch report colors mixed `chunks[]` outcomes as partial rather than all-green/all-red.

## Maintenance rules

When adding a new `compute_type`, keep these routing tables in agreement:

- `python/server_routes/jobs.py:362` `_compute_subprocess_entry()`; IPA full-mode dispatch is at `python/server_routes/jobs.py:391` and ORTH dispatch uses `_compute_speaker_ortho_dispatch()` at `python/server_routes/jobs.py:397`.
- `python/server_routes/jobs.py:1027` / `python/server_routes/jobs.py:1031` in `_run_compute_job()` for thread-mode IPA/ORTH dispatch.
- `python/workers/compute_worker.py:409` `_dispatch()`; IPA full-mode dispatch is at `python/workers/compute_worker.py:428`, and ORTH full-mode dispatch is at `python/workers/compute_worker.py:430`-`435`.

A compute type that works in one mode but not another is a contract bug. Add or update tests before shipping a new alias.

Future Tier-1 long-file stages should consult this page and reuse `python/workers/audio_chunking.py` rather than inventing stage-local chunk shapes.

## Verification lineage

MC-384-E grep-verified the original MC-384-A/B/C/D/F citations before PR #416 opened. The 2026-05-13 worker-process follow-up re-grounded this page against current `origin/main` after PR #417 and moved the detailed process topology to `docs/architecture/worker-processes.md`.

MC-384-M re-grounded the STT and IPA notes against current `origin/main` after PR #420 (STT chunking) and PR #422 (IPA shrink warnings).

MC-384-I/L/O/P (PRs #423, #425, #426, #427) hardened the test surface around chunked STT after MC-384-M: I added synthetic-audio fixtures for unit-level chunking assertions, L backfilled stale `source_audio_duration_sec` values across existing workspaces, O added the gated real-WAV long-audio regression behind the `long_audio` pytest marker, and P locked the STT cache shape (flat merged segments; `chunks[]` lives only in job result envelopes) plus the chunk-progress UI contract.

MC-384-N (PR #428) closed the full-file STT subprocess-isolation gap by wrapping `_run_stt_job()` in `_run_stt_job_in_subprocess()` and adding the `_run_stt_job_subprocess_entry()` child boundary plus a structured `[STT]` completion summary log. MC-384-S (PR #430) repaired integration-test drift caused by #428 and MC-384-Q (#429) merging in adjacent windows; #429 also added the compute.md drift guard that ties this document to the chunking env-var and top-level subprocess-wrap surface.

MC-384-T (PR #431) added the Tier-2 fallback contract: when forced alignment raises, ORTH preserves the Tier-1 no-parrot pick rather than emitting raw Tier-1 text. MC-384-U (PR #432) fixed the root cause — a numpy ndarray reached a consumer that called `.numel()` — by restoring the torch-tensor contract at the Tier-2 boundary, adding an `isinstance` assertion, and shipping a sentinel test that catches future drift loudly rather than via a logged-and-swallowed `AttributeError`.
