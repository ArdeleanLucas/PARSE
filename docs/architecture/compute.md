# Compute architecture

This page is the maintainable reference for PARSE compute execution after the MC-384 compute-architecture series (PRs #411-#440). The canonical design input was the local architecture specification at `/mnt/c/Users/Lucas/Desktop/parse/compute-architecture-differentiation-spec.md`; this page now records the shipped runtime contract in the repo.

For the process-level view of the worker/subprocess changes, see [Worker process architecture](worker-processes.md). For operator knobs, see [Environment variables](../environment-variables.md).

## Overview

PARSE keeps one user-facing compute system but differentiates execution by intent:

- Fast lexeme/concept-window path: scoped work uses `run_mode != 'full'` and/or `concept_ids`; it should avoid long-file chunking overhead and return quickly for interactive fieldwork.
- Robust long-file path: full-speaker/full-pipeline work runs through the job system; after the completed MC-384 series, long Tier-1 ORTH/STT transcribe work is chunked so a Khan01/Fail01-scale recording cannot crash ORTH or silently truncate STT.

The guiding rule is intent first, duration second. A full-pipeline request expresses robust intent; a concept-window request expresses fast intent. Duration only decides whether a robust Tier-1 ORTH/STT request needs chunking.

## Mental model for developers

Think of PARSE compute as four layers, not one worker:

```text
Browser / MCP / scripts
        |
        v
Job registry and launcher (python/server_routes/jobs.py)
        |
        +-- thread mode: in-process background job
        +-- subprocess mode: one outer child per job
        +-- persistent mode: long-lived python/workers/compute_worker.py
        |
        v
Stage route modules
        +-- STT:   python/server_routes/media.py
        +-- ORTH:  python/server_routes/annotate.py
        +-- IPA:   python/server_routes/annotate.py + python/ai/ipa_transcribe.py
        |
        v
Heavy-stage safeguards
        +-- duration chunking for long full-file STT and full-mode ORTH
        +-- nested isolated subprocesses for full-file STT, full-mode ORTH, full-mode IPA
        +-- unified device resolver in python/ai/device.py
```

A long full-pipeline recording flows like this:

```text
full pipeline request
  -> job snapshot + progress/log stream
  -> optional normalize
  -> STT full-file stage
       if duration > PARSE_STT_DEFAULT_CHUNK_MINUTES:
         split -> transcribe chunk N -> merge segments into audio-global time
       write flat coarse_transcripts/<speaker>.json segments cache
  -> ORTH full-mode stage
       if duration > PARSE_ORTH_DEFAULT_CHUNK_MINUTES:
         split -> transcribe Tier-1 chunk N -> merge Tier-1 text/windows
       run Tier-2 forced alignment once over the merged Tier-1 result
       write merged annotation tiers
  -> IPA full-mode stage
       run over existing intervals/windows, not whole-audio chunks
       return coverage_shrink_warning if overwrite would sharply reduce coverage
  -> final job result with per-stage status, chunks[], device, logs
```

Key files and responsibilities:

| File | Responsibility |
|---|---|
| `python/server_routes/jobs.py` | Job registry, compute launcher mode resolution, outer thread/subprocess dispatch, snapshots, cancellation surface. |
| `python/workers/compute_worker.py` | Persistent-worker process loop and compute dispatch for `PARSE_COMPUTE_MODE=persistent`. |
| `python/server_routes/media.py` | Full-file STT, STT chunk loop, STT subprocess entry/wrapper, STT cache write. |
| `python/server_routes/annotate.py` | Full-pipeline orchestration, ORTH chunk loop, Tier-2 alignment, IPA subprocess wrappers, isolated subprocess helper. |
| `python/workers/audio_chunking.py` | Shared `ChunkSpan`, `ChunkResult`, split, and merge primitives. |
| `python/ai/device.py` | Stage/global/config/default device resolver for STT, ORTH, and IPA. |
| `src/components/shared/BatchReportTableRow.tsx` | UI interpretation of `chunks[]` as all-ok, all-error, partial, or none. |

When debugging, start at the job boundary. Confirm job id, status, progress messages, `chunks[]`, `device`, and logs before changing provider/model code.

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

## Subprocess isolation

MC-384 uses two distinct isolation layers. Keep them conceptually separate:

1. **Outer job launcher** — selected by `_resolve_compute_mode()` in `python/server_routes/jobs.py`. `thread` is the low-overhead default, `subprocess` launches one child process per compute job, and `persistent` routes jobs through the long-lived worker in `python/workers/compute_worker.py`.
2. **Nested heavy-stage isolation** — selected by compute intent. Full-file STT, full-mode ORTH, and full-mode IPA run in spawn children via `_run_in_isolated_subprocess()` even when the outer launcher is still `thread`.

Current import-stable entrypoints:

| Stage | Child entrypoint | Parent wrapper | Scope that uses it |
|---|---|---|---|
| STT | `server_routes.media._run_stt_job_subprocess_entry` | `server_routes.media._run_stt_job_in_subprocess` | Full-file STT only. Scoped/concept-window STT stays in-process. |
| ORTH | `server_routes.annotate._speaker_ortho_subprocess_entry` | `server_routes.annotate._compute_speaker_ortho_in_subprocess` | Full-mode ORTH from standalone compute or full pipeline. Scoped/concept-window ORTH stays in-process. |
| IPA | `server_routes.annotate._full_pipeline_ipa_subprocess_entry` and `_speaker_ipa_subprocess_entry` | `server_routes.annotate._compute_full_pipeline_ipa_in_subprocess` and `_compute_speaker_ipa_in_subprocess` | Full-mode IPA from standalone compute or full pipeline. Concept-window IPA stays in-process. |

`python/server_routes/jobs.py::_launch_compute_subprocess()` and `_compute_subprocess_entry()` are the **outer** per-job subprocess path. They may wrap an entire job, which can then launch a nested child for one heavy stage. This means a `PARSE_COMPUTE_MODE=subprocess` full-pipeline STT step can involve two processes beyond the parent: the outer compute child plus the nested STT child. That is expected; the first layer protects job orchestration, the second layer protects memory-heavy model calls.

Nested children serialize `{ok: true, result: ...}` or `{ok: false, error, traceback}` to a result file. Parent wrappers convert child failure into structured job errors and keep stdout/stderr visible through tee-backed logs.

## Chunking primitives

PR #411 added `python/workers/audio_chunking.py` as the shared chunking primitive module for robust Tier-1 ORTH and STT paths (84 LoC):

- `python/workers/audio_chunking.py:12` — `ChunkSpan`, the audio-global `{start, end}` span shape.
- `python/workers/audio_chunking.py:18` — `ChunkResult`, the per-chunk result shape used by ORTH/STT job and MCP outputs.
- `python/workers/audio_chunking.py:26` — `split_audio_duration(total_seconds, chunk_seconds)`.
- `python/workers/audio_chunking.py:56` — `merge_chunk_segments(per_chunk_segments, spans)`, which offsets chunk-local segments back into audio-global time.

## Tier-1 vs Tier-2 ORTH

ORTH has two tiers with different memory profiles:

- Tier-1 coarse ORTH uses `provider.transcribe()` and is the Khan01 OOM vector. Current main calls it through `_transcribe_ortho_with_fallback()` and the chunk loop in `python/server_routes/annotate.py:2669`-`2716` for long full-mode files.
- Tier-2 word alignment (`tiers.ortho_words`) runs after coarse ORTH and is already windowed enough for the current long-file contract. It remains unchanged and recomputes once over the merged Tier-1 result.

The shipped MC-384 Tier-1 chunking path uses adjacent chunks with no overlap. The final chunked Tier-1 loop is `python/server_routes/annotate.py:2669`-`2716`: it measures duration, splits with `split_audio_duration()` at `python/server_routes/annotate.py:2677`, runs each temporary slice, records per-chunk status/errors, and merges with `merge_chunk_segments()` at `python/server_routes/annotate.py:2716`.

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

## Device resolver

MC-384-Z centralizes STT, ORTH, and IPA device placement in `python/ai/device.py`. The resolver is evaluated at call time, imports torch lazily, and resolves `auto` to `cuda` only when `torch.cuda.is_available()` and `torch.cuda.device_count() > 0`; otherwise `auto` resolves to `cpu`. Explicit `cuda` / `cuda:N` requests warn and fall back to CPU when CUDA is unavailable.

Device precedence, highest first:

| Priority | Source | Scope | Accepted values |
|---|---|---|---|
| 1 | `PARSE_STT_DEVICE`, `PARSE_ORTH_DEVICE`, `PARSE_IPA_DEVICE` | Per stage | `auto`, `cpu`, `cuda`, `cuda:N` |
| 2 | `PARSE_COMPUTE_DEVICE` | Global fallback for STT/ORTH/IPA | `auto`, `cpu`, `cuda`, `cuda:N` |
| 3 | `ai_config.json` section `device` | Caller config (`stt`, `ortho`, `wav2vec2`) | `auto`, `cpu`, `cuda`, `cuda:N` |
| 4 | Code section default | Usually `auto` | `auto`, `cpu`, `cuda`, `cuda:N` |

`PARSE_STT_FORCE_CPU` is preserved as a backwards-compatible alias for `PARSE_STT_DEVICE=cpu`; it wins before the normal STT device chain and still forces faster-whisper CPU/int8 fallback semantics.

IPA retains one compatibility gate from the old wav2vec2 WSL safety model: explicit `wav2vec2.allow_wsl_cuda=false` forces CPU before the unified resolver is consulted. When that key is omitted or true, IPA uses the same precedence chain as STT and ORTH. This is the MC-384-Z behavior change: the absent-key default now allows CUDA-capable WSL machines to use the resolver instead of silently pinning IPA to CPU. Existing copied configs that explicitly set false remain conservative until edited.

Result observability uses the current wire key `device`. PR notes and user task descriptions may call this `resolved_device`; in the shipped payload, the resolved/effective device appears as `device` on STT, ORTH, and IPA stage results and in `[STT]` / `[ORTH]` / `[IPA]` completion logs.

## Environment variables

The full operator reference is [Environment variables](../environment-variables.md). Compute-specific knobs are summarized here because they are part of the architecture contract:

| Variable | Default | Contract |
|---|---:|---|
| `PARSE_STT_DEFAULT_CHUNK_MINUTES` | `10` | Full-file STT chunk size. `0` disables duration chunking; invalid values fall back to 10. |
| `PARSE_ORTH_DEFAULT_CHUNK_MINUTES` | `10` | Full-mode ORTH Tier-1 chunk size. `0` disables duration chunking; invalid values fall back to 10. |
| `PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC` | `60` | Destructive IPA overwrite warning threshold. `0` disables `coverage_shrink_warning`; this is not an IPA duration-chunking knob. |
| `PARSE_COMPUTE_DEVICE` | `auto` | Global STT/ORTH/IPA device fallback. |
| `PARSE_STT_DEVICE` | unset | STT-specific device override. |
| `PARSE_ORTH_DEVICE` | unset | ORTH-specific device override. |
| `PARSE_IPA_DEVICE` | unset | IPA-specific device override when `wav2vec2.allow_wsl_cuda` is not explicitly false. |
| `PARSE_STT_FORCE_CPU` | unset | Truthy backwards-compatible alias for `PARSE_STT_DEVICE=cpu`. |
| `PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC` | `14400` | Timeout for the outer subprocess launcher and nested isolated children. The nested helper honors any positive finite value exactly. |
| `PARSE_COMPUTE_MODE` | backend default `thread` | Outer compute launcher: `thread`, `subprocess`, or `persistent`. |
| `PARSE_USE_PERSISTENT_WORKER` | unset | Truthy shortcut selecting `persistent`. |
| `PARSE_FULL_PIPELINE_MIN_MEM_GB` | backend default `12` | Host-memory preflight threshold before memory-heavy full-pipeline stages. |

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
| Full-pipeline ORTH, short audio | at or below `PARSE_ORTH_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Robust subprocess wrapper may run, but Tier-1 uses one provider call and returns `chunks: []`. |
| Full-pipeline ORTH, long audio | greater than `PARSE_ORTH_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Tier-1 ORTH chunks, each isolated; Tier-2 recomputes once after merge. |
| Full-file STT, short audio | at or below `PARSE_STT_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Single-shot `_run_stt_job()` path; `chunks: []`. |
| Full-file STT, long audio | greater than `PARSE_STT_DEFAULT_CHUNK_MINUTES * 60` (default 600s) | default | Tier-1 STT chunks; per-chunk results emitted in `chunks[]`, merged cache remains flat segments. |
| Full-file STT with chunking disabled | any | `PARSE_STT_DEFAULT_CHUNK_MINUTES=0` | Single-shot STT regardless of duration; `chunks: []`. |
| Scoped/concept-window STT (`run_mode != 'full'`) | any | payload scope | `_compute_speaker_stt()` path; windows are already bounded, so no audio-duration chunking. |
| MCP/agent full ORTH with `force_robust=true` | any | payload flag | Robust path; duration still decides whether the robust path chunks. |
| MCP/agent scoped ORTH with `fast_mode=true` or `concept_ids` | any | payload flag/scope | Fast scoped path; no chunking. |
| Cancel requested mid-run | long audio | job cancel flag | Between-chunk polling; completed chunks remain `ok`, remaining chunks report `cancelled`, and top-level status is `cancelled` or `partial_cancelled` depending on stage/path. |

## Performance and resource characteristics

The robust path buys failure isolation and bounded decoder state at some cost:

- Long STT/ORTH runs perform one provider call per chunk instead of one monolithic call. This reduces peak memory and repetition-loop blast radius, but adds temp-WAV slicing and per-call setup overhead.
- Nested subprocess isolation adds spawn/import/model-load overhead for full-file STT, full-mode ORTH, and full-mode IPA. Scoped concept-window work intentionally bypasses this overhead.
- `persistent` outer mode can keep selected models warm for repeated jobs, but full-mode heavy stages may still spawn nested children for crash containment. Do not assume persistent mode removes nested isolation.
- Smaller chunks are safer for hostile recordings but can increase total wall time; larger chunks reduce overhead but increase OOM/decoder-loop risk. The field default is 10 minutes because it bounds Khan01/Fail01-scale recordings without excessive chunk count.

Planning rules of thumb:

| Recording length | Default chunk count | What to expect |
|---:|---:|---|
| 1 hour | 6 chunks | Practical on most configured workstations; a 16 GB laptop may still take hours if CPU-only. |
| 2 hours | 12 chunks | Watch memory and progress; prefer one speaker at a time on laptops. |
| 3 hours | 18 chunks | Treat as a long unattended job; inspect partial chunk outcomes before trusting downstream IPA/Compare work. |
| 4.5 hours | 27 chunks | Khan01-scale; defaults are intended to prevent parent-backend death, not to make review instantaneous. |

Hardware guidance:

- **16 GB laptop:** keep chunking enabled; drop STT/ORTH chunks to 5 minutes after any `oom_suspect`; run one stage/speaker at a time; consider CPU fallback for unstable CUDA stacks.
- **CUDA workstation:** keep 10-minute defaults first; use stage-specific device overrides only when completion logs or result `device` show a real placement problem.
- **Server/high-RAM box:** defaults are suitable for batch work, but still read `chunks[]`; provider errors are often data-specific rather than pure capacity issues.
- **CPU-only:** supported but slow. Benchmark a 10-minute slice before scheduling a multi-hour corpus.

Chunking helps when the risk is memory pressure, decoder state poisoning, or the need for visible progress. It adds overhead when files are already short, models are already stable, or the goal is a controlled old-path benchmark. That is why `0` disables duration chunking but is not the fieldwork default.

## Debugging chunked jobs

For long-file regressions, debug in this order:

1. **Job state:** `GET /api/jobs/active`, `job_status`, or `compute_status` for terminal status and progress.
2. **Stage result:** inspect `result.chunks[]` or `result.results.<stage>.chunks[]` for `span`, `status`, `error_code`, and `error`.
3. **Logs:** use `job_logs` and backend logs to find the first failing chunk/stage. Nested subprocess failures should include traceback or crash-log tail data.
4. **Device:** compare result `device` against `PARSE_{STAGE}_DEVICE`, `PARSE_COMPUTE_DEVICE`, config `device`, and CUDA availability.
5. **Persistence:** remember that STT caches only flat merged `segments[]`; `chunks[]` is job-result-only.
6. **Retry strategy:** lower chunk size before disabling chunking. Disable chunking only when reproducing old monolithic behavior is the experiment.

User-facing recovery details live in [Processing long recordings](../user-guides/processing-long-recordings.md) and [Troubleshooting long files](../troubleshooting/long-files.md).

## Khan01 incident summary

Khan01 is the motivating fieldwork failure: a 1.6 GB concatenated WAV, roughly 4.5 hours, killed the backend during full-file ORTH. Memory preflight passed at job start, but peak ORTH inference exceeded WSL memory headroom. IPA already had nested subprocess protection; ORTH did not.

The completed MC-384 architecture closes the incident by containing long ORTH work in isolated subprocesses and splitting Tier-1 transcribe into default 10-minute chunks. A chunk-level failure produces structured result data instead of taking down the parent server.

## Result contract

Chunked compute results add a `chunks` array with per-chunk status. See `docs/mcp-schema.md` for the agent-facing schema and examples. Backward-compatible callers that only read top-level fields such as `status`, `filled`, `total`, `segments`, and `ortho_words` continue to work.

Important fields:

| Field | Producers | Lifecycle |
|---|---|---|
| `chunks[]` | Full-file STT and full-mode ORTH job results | Present in job results for chunk-aware paths; empty for short/single-shot paths; not persisted to STT cache. |
| `device` | STT, ORTH, IPA | Resolved/effective device. This is the shipped wire key for what PR notes may call `resolved_device`. |
| `coverage_shrink_warning` | IPA overwrite runs | Optional warning object in IPA/full-pipeline results; not a hard failure. |
| `duration_sec` | STT | Source audio duration used for chunking decisions. |

STT preserves its cache contract: `_write_stt_cache()` receives the merged flat `segments` list only, while `chunks[]` remains a job-result diagnostic envelope. ORTH writes merged annotation tiers and returns chunk diagnostics in the job result rather than persisting a separate chunk cache.

UI consumers parse the same contract: the header job strip recognizes `STT chunk N/M (...)` and `ORTH chunk N/M (...)` progress messages, and the batch report colors mixed `chunks[]` outcomes as partial rather than all-green/all-red.

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

MC-384-Z (PR #440) added the unified device resolver (`python/ai/device.py`) and per-stage device environment overrides for STT, ORTH, and IPA. This doc refresh reconciles architecture, environment, MCP/schema, user-guide, developer, and release-note references after #440.
