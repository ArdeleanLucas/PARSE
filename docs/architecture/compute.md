# Compute architecture

This page is the maintainable reference for PARSE compute execution after MC-384 Milestone A. The canonical design input is the local architecture specification at `/mnt/c/Users/Lucas/Desktop/parse/compute-architecture-differentiation-spec.md`.

## Overview

PARSE keeps one user-facing compute system but differentiates execution by intent:

- Fast lexeme/concept-window path: scoped work uses `run_mode != 'full'` and/or `concept_ids`; it should avoid long-file chunking overhead and return quickly for interactive fieldwork.
- Robust long-file path: full-speaker/full-pipeline work runs through the job system and, after MC-384 Milestone A, long ORTH Tier-1 transcribe work is isolated and chunked so a Khan01-scale recording cannot kill the parent server.

The guiding rule is intent first, duration second. A full-pipeline request expresses robust intent; a concept-window request expresses fast intent. Duration only decides whether a robust ORTH request needs chunking.

## Compute modes

`python/server_routes/jobs.py:48` defines `_resolve_compute_mode()`. Resolution order is:

1. CLI `--compute-mode` override.
2. `PARSE_USE_PERSISTENT_WORKER=true`, which selects `persistent`.
3. `PARSE_COMPUTE_MODE`, accepting `thread`, `subprocess`, or `persistent`.
4. Default `thread`.

Mode meanings:

- `thread`: legacy in-process background thread. Lowest process overhead, weakest crash containment.
- `subprocess`: per-job process launched by `python/server_routes/jobs.py:362` `_compute_subprocess_entry()`. Better crash containment for the whole job.
- `persistent`: long-lived worker in `python/workers/compute_worker.py` that dispatches jobs through `_dispatch()` at `python/workers/compute_worker.py:417` and can keep models warm.

## Nested subprocess wrappers

MC-384 extends the existing nested-subprocess pattern. PR #412 introduced the shared IPA subprocess envelope and standalone IPA full-mode routing:

- `python/server_routes/annotate.py:2704` — `_isolated_subprocess_error_result()` builds the structured subprocess error result and assigns `oom_suspect`/`timeout` where applicable.
- `python/server_routes/annotate.py:2782` — `_speaker_ipa_subprocess_entry()` serializes standalone speaker-IPA child outcomes.
- `python/server_routes/annotate.py:3001` — `_run_in_isolated_subprocess()` owns spawn, timeout, result-file parsing, and envelope error conversion.
- `python/server_routes/annotate.py:3107` — `_compute_full_pipeline_ipa_in_subprocess()` now delegates to the shared helper.
- `python/server_routes/annotate.py:3120` — `_compute_speaker_ipa_in_subprocess()` wraps standalone `compute_type='ipa'` full-mode calls.
- `_compute_speaker_ortho_in_subprocess`: `TODO_LINE` (MC-384-C).

These nested wrappers are separate from `PARSE_COMPUTE_MODE=subprocess`. The outer compute mode chooses how the job is launched; the nested wrappers isolate a memory-heavy step inside that job.

## Chunking primitives

PR #411 added `python/workers/audio_chunking.py` as the shared chunking primitive module (84 LoC):

- `python/workers/audio_chunking.py:12` — `ChunkSpan`, the audio-global `{start, end}` span shape.
- `python/workers/audio_chunking.py:18` — `ChunkResult`, the per-chunk result shape used by job/MCP outputs.
- `python/workers/audio_chunking.py:26` — `split_audio_duration(total_seconds, chunk_seconds)`.
- `python/workers/audio_chunking.py:56` — `merge_chunk_segments(per_chunk_segments, spans)`, which offsets chunk-local segments back into audio-global time.

## Tier-1 vs Tier-2 ORTH

ORTH has two tiers with different memory profiles:

- Tier-1 coarse ORTH uses `provider.transcribe()` and is the Khan01 OOM vector. Current main calls it in `python/server_routes/annotate.py:2460`; MC-384-D moves the long-file/full-mode call behind chunked isolation.
- Tier-2 word alignment (`tiers.ortho_words`) runs after coarse ORTH and is already windowed enough for Milestone A. It remains unchanged and recomputes once over the merged Tier-1 result.

MC-384-D uses adjacent chunks with no overlap for Milestone A. The line citation for the final chunked Tier-1 loop is `TODO_LINE`.

## Environment variables

- `PARSE_ORTH_DEFAULT_CHUNK_MINUTES`: MC-384-D default chunk size for long ORTH Tier-1; expected default is `10`. Final declaration line: `TODO_LINE`.
- `PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC`: existing hard timeout for compute subprocesses; used by `python/server_routes/jobs.py:320` for per-job subprocess mode and by `python/server_routes/annotate.py:3037` for nested isolated subprocesses, default `14400`.
- `PARSE_USE_PERSISTENT_WORKER`: shortcut selecting persistent worker mode; read by `python/server_routes/jobs.py:61` and documented in `scripts/parse-run.sh:27`.
- `PARSE_COMPUTE_MODE`: explicit compute launcher mode; read by `python/server_routes/jobs.py:63` and documented in `scripts/parse-run.sh:28`.
- `PARSE_FULL_PIPELINE_MIN_MEM_GB`: full-pipeline host-memory preflight threshold; read by `python/server_routes/annotate.py:2584` and documented in `scripts/parse-run.sh:30`.

## Subprocess timeout configuration

`PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC` defaults to `14400` seconds (4 hours). PR #412 changed nested isolated subprocess timeout handling in `python/server_routes/annotate.py:3037`-`3043`: any positive finite value is respected exactly. The previous 60-second minimum floor was removed for the nested wrapper, so test and debug runs can use values such as `1` second. Values that are zero, negative, non-finite, missing, or unparsable fall back to `14400`.

The older per-job `PARSE_COMPUTE_MODE=subprocess` launcher still reads the same variable at `python/server_routes/jobs.py:320`; its floor behavior is separate from the nested helper and should be audited before changing that outer launcher contract.

## Subprocess result envelope

`_run_in_isolated_subprocess()` (`python/server_routes/annotate.py:3001`) uses an internal JSON envelope where child entries write `{ok: true, result: ...}` for successful computations and `{ok: false, error: ..., traceback: ...}` for child failures. `_compute_full_pipeline_ipa_in_subprocess()` (`python/server_routes/annotate.py:3107`) then treats `sub_result.get('status') == 'error'` as the hard subprocess-error sentinel generated by `_isolated_subprocess_error_result()` (`python/server_routes/annotate.py:2704`).

Contract for subprocess entries: a successful computation must not return a dict whose `status` field is the literal string `error`. If application-level partial failure needs to be surfaced, use a different key such as `failure_reason` or `partial`, or raise and let the subprocess envelope convert the failure. Returning `status='error'` from successful application code collides with the envelope sentinel.

## When chunking fires

| User/API intent | Duration | Flags/env | Expected path |
| --- | ---: | --- | --- |
| Concept-window ORTH (`run_mode != 'full'`) | any | default | Fast scoped path; no chunking. |
| Full-pipeline ORTH, short audio | at or below threshold | default | Robust wrapper may run, but `chunks` is empty or a single non-chunked result depending on MC-384-D implementation. |
| Full-pipeline ORTH, long audio | greater than `PARSE_ORTH_DEFAULT_CHUNK_MINUTES` | default | Tier-1 ORTH chunks, each isolated; Tier-2 recomputes once after merge. |
| MCP/agent full ORTH with `force_robust=true` | any | payload flag | Robust path; duration still decides whether the robust path chunks. |
| MCP/agent scoped ORTH with `fast_mode=true` or `concept_ids` | any | payload flag/scope | Fast scoped path; no chunking. |
| Cancel requested mid-run | long audio | job cancel flag | Between-chunk polling only for Milestone A; completed chunks remain ok, remaining chunks report cancelled. |

## Khan01 incident summary

Khan01 is the motivating fieldwork failure: a 1.6 GB concatenated WAV, roughly 4.5 hours, killed the backend during full-file ORTH. Memory preflight passed at job start, but peak ORTH inference exceeded WSL memory headroom. IPA already had nested subprocess protection; ORTH did not.

MC-384 Milestone A closes the incident by containing long ORTH work in isolated subprocesses and splitting Tier-1 transcribe into default 10-minute chunks. A chunk-level failure produces structured result data instead of taking down the parent server.

## Result contract

Chunked compute results add a `chunks` array with per-chunk status. See `docs/mcp-schema.md` for the agent-facing schema. Backward-compatible callers that only read the top-level `status`, `filled`, `total`, and `ortho_words` fields continue to work.

## Maintenance rules

When adding a new `compute_type`, keep these routing tables in agreement:

- `python/server_routes/jobs.py:362` `_compute_subprocess_entry()`; standalone IPA full-mode dispatch is at `python/server_routes/jobs.py:391`.
- `python/server_routes/jobs.py:1025` `_run_compute_job()` thread-mode IPA full-mode dispatch.
- `python/workers/compute_worker.py:417` `_dispatch()`; standalone IPA full-mode dispatch is at `python/workers/compute_worker.py:424`.
- Future ORTH subprocess/chunk dispatch citations remain pending until MC-384-C/D.

A compute type that works in one mode but not another is a contract bug. Add or update tests before shipping a new alias.

## Finalization checklist for MC-384-E

Before opening the PR, replace every `TODO_LINE` citation with grep-verified line numbers from current `origin/main`, after MC-384-A/B/C/D have merged.
