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
- `persistent`: long-lived worker in `python/workers/compute_worker.py` that dispatches jobs through `_dispatch()` at `python/workers/compute_worker.py:409` and can keep models warm.

## Nested subprocess wrappers

MC-384 extends the existing nested-subprocess pattern. Current main has the IPA full-pipeline nested wrapper at `python/server_routes/annotate.py:2950` (`_compute_full_pipeline_ipa_in_subprocess`). After MC-384-B/C merge, this section must cite the new exact wrappers:

- `_run_in_isolated_subprocess`: `TODO_LINE`.
- `_compute_speaker_ipa_in_subprocess`: `TODO_LINE`.
- `_compute_speaker_ortho_in_subprocess`: `TODO_LINE`.

These nested wrappers are separate from `PARSE_COMPUTE_MODE=subprocess`. The outer compute mode chooses how the job is launched; the nested wrappers isolate a memory-heavy step inside that job.

## Tier-1 vs Tier-2 ORTH

ORTH has two tiers with different memory profiles:

- Tier-1 coarse ORTH uses `provider.transcribe()` and is the Khan01 OOM vector. Current main calls it in `python/server_routes/annotate.py:2460`; MC-384-D moves the long-file/full-mode call behind chunked isolation.
- Tier-2 word alignment (`tiers.ortho_words`) runs after coarse ORTH and is already windowed enough for Milestone A. It remains unchanged and recomputes once over the merged Tier-1 result.

MC-384-D uses adjacent chunks with no overlap for Milestone A. The line citation for the final chunked Tier-1 loop is `TODO_LINE`.

## Environment variables

- `PARSE_ORTH_DEFAULT_CHUNK_MINUTES`: MC-384-D default chunk size for long ORTH Tier-1; expected default is `10`. Final declaration line: `TODO_LINE`.
- `PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC`: existing hard timeout for compute subprocesses; used by `python/server_routes/jobs.py:320` and `python/server_routes/annotate.py:2973`, default `14400`.
- `PARSE_USE_PERSISTENT_WORKER`: shortcut selecting persistent worker mode; read by `python/server_routes/jobs.py:61` and documented in `scripts/parse-run.sh:27`.
- `PARSE_COMPUTE_MODE`: explicit compute launcher mode; read by `python/server_routes/jobs.py:63` and documented in `scripts/parse-run.sh:28`.
- `PARSE_FULL_PIPELINE_MIN_MEM_GB`: full-pipeline host-memory preflight threshold; read by `python/server_routes/annotate.py:2584` and documented in `scripts/parse-run.sh:30`.

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

- `python/server_routes/jobs.py:362` `_compute_subprocess_entry()`.
- `python/workers/compute_worker.py:409` `_dispatch()`.
- The thread-mode dispatcher in `python/server_routes/jobs.py` around `TODO_LINE` after the final MC-384 rebase.

A compute type that works in one mode but not another is a contract bug. Add or update tests before shipping a new alias.

## Finalization checklist for MC-384-E

Before opening the PR, replace every `TODO_LINE` citation with grep-verified line numbers from current `origin/main`, after MC-384-A/B/C/D have merged.
