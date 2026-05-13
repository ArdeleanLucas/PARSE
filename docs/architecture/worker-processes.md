# Worker process architecture

This page is the process-topology companion to [Compute architecture](compute.md). It records the worker/process design that landed in MC-384 Milestone A on 2026-05-12, with PR #417 as the current head of the slice.

## What changed in the worker slice

| PR | Shipped worker/process contract |
| --- | --- |
| [#411](https://github.com/ArdeleanLucas/PARSE/pull/411) | Added pure audio chunking primitives in `python/workers/audio_chunking.py`: `ChunkSpan`, `ChunkResult`, `split_audio_duration()`, and `merge_chunk_segments()`. |
| [#412](https://github.com/ArdeleanLucas/PARSE/pull/412) | Added the shared nested spawn helper `_run_in_isolated_subprocess()` and routed full-mode IPA through standalone subprocess isolation across thread, per-job subprocess, and persistent-worker modes. |
| [#413](https://github.com/ArdeleanLucas/PARSE/pull/413) | Added full-mode ORTH subprocess isolation and wired ORTH dispatch through the same nested isolation layer in every outer compute launcher. |
| [#414](https://github.com/ArdeleanLucas/PARSE/pull/414) | Added long-file Tier-1 ORTH chunking inside the isolated ORTH child, defaulting to 10-minute adjacent chunks with temp-WAV cleanup, between-chunk cancellation, and structured `chunks[]` results. |
| [#415](https://github.com/ArdeleanLucas/PARSE/pull/415) | Taught TypeScript contracts and batch-result components to tolerate `chunks[]` and new structured error codes. |
| [#416](https://github.com/ArdeleanLucas/PARSE/pull/416) | Added the maintained compute architecture page, MCP result schema, and Khan01 Milestone A regression harness. |
| [#417](https://github.com/ArdeleanLucas/PARSE/pull/417) | Added live chunk-progress display in the top job strip and partial/all-error chunk coloring in the batch report. |

## Layer model

PARSE now has three distinct worker layers. They are intentionally separate; do not collapse their responsibilities in future changes.

1. **Outer compute launcher** — selected by `_resolve_compute_mode()` in `python/server_routes/jobs.py`.
   - `thread`: one background thread in the HTTP server process.
   - `subprocess`: one spawned Python process per compute job plus a parent monitor thread.
   - `persistent`: one long-lived `parse-compute-worker` process with queues and a parent monitor thread.
2. **Nested heavy-step isolation** — selected by compute intent, not by outer launcher.
   - Full-mode IPA and ORTH run through `_run_in_isolated_subprocess()` in `python/server_routes/annotate.py`.
   - Concept-window/scoped ORTH and IPA stay on the fast path; they do not pay the full-mode isolation/chunking cost.
3. **Chunking inside the isolated ORTH child** — selected by duration.
   - Long full-mode ORTH splits Tier-1 transcription into adjacent audio slices.
   - Chunks are not separate worker processes; they are sequential provider calls inside the isolated ORTH subprocess.
   - Tier-2 `ortho_words` is rebuilt once after Tier-1 chunks are merged back to audio-global timestamps.

## Code anchors

| Concern | Source anchor |
| --- | --- |
| Mode resolution | `python/server_routes/jobs.py:48-64` `_resolve_compute_mode()` chooses CLI override, persistent shortcut, `PARSE_COMPUTE_MODE`, then default `thread`. |
| Outer launcher | `python/server_routes/jobs.py:247-289` `_launch_compute_runner()` dispatches to thread, per-job subprocess, or persistent mode. |
| Per-job subprocess | `python/server_routes/jobs.py:291-360` starts the spawned child and parent monitor; `python/server_routes/jobs.py:362-438` is the child entry. |
| Persistent worker startup | `python/server.py:783-814` starts `WorkerHandle`; `python/workers/compute_worker.py:87-123` waits for the ready event. |
| Persistent worker event bridge | `python/workers/compute_worker.py:267-333` patches server job-state functions into queue emitters; `python/workers/compute_worker.py:170-243` drains events in the parent monitor thread. |
| Persistent worker dispatch | `python/workers/compute_worker.py:409-465` mirrors compute aliases; `python/workers/compute_worker.py:468-574` owns preload, ready, dispatch, error, and keep-alive loop. |
| Nested isolation helper | `python/server_routes/annotate.py:3171-3283` owns spawn, timeout, result-file parsing, and error-code mapping for full-mode ORTH/IPA children. |
| Full-mode ORTH routing | `python/server_routes/annotate.py:3299-3335` routes full-mode ORTH to the nested child and keeps scoped ORTH on the fast path. |
| Chunked ORTH loop | `python/server_routes/annotate.py:2554-2601` measures duration, splits spans, slices temp WAVs, emits chunk progress, classifies chunk errors, and merges segments. |
| Worker status endpoint | `python/server_routes/jobs.py:1121-1133` returns `{mode, alive, pid, jobs_in_flight}` for persistent-worker observability. |

## Process topology

### Default `thread` mode

```text
Browser / MCP / chat tool
        |
        v
HTTP server process
  _launch_compute_runner(mode="thread")
        |
        +-- background Thread -> _run_compute_job(job_id, compute_type, payload)
                                  |
                                  +-- full IPA/ORTH? -> spawn nested isolated child
                                  |                     -> write result JSON
                                  |                     -> parent reads envelope
                                  |
                                  +-- scoped ORTH/IPA? -> run fast path in thread
```

Use this mode for ordinary development and fast scoped jobs. It has the least process overhead, but memory-heavy model failures still share the HTTP server address space unless the full-mode nested wrapper is reached.

### `subprocess` mode

```text
HTTP server process
  _launch_compute_runner(mode="subprocess")
        |
        +-- spawn per-job child: _compute_subprocess_entry(...)
        |       |
        |       +-- imports server and dispatches compute type
        |       +-- full IPA/ORTH? -> spawn nested isolated child
        |       +-- writes /tmp/parse-compute-<job_id>.json
        |       +-- tees stderr to /tmp/parse-compute-<job_id>.stderr.log
        |
        +-- parent monitor thread joins child, reads result JSON,
            and updates the in-memory job registry for normal status polling
```

This mode protects the HTTP server from per-job CUDA/torch/process failures. It costs a fresh Python import/model load per job.

### `persistent` mode

```text
HTTP server process
  _start_persistent_worker()
        |
        +-- WorkerHandle
              | job_queue / event_queue
              v
           parse-compute-worker process
             - installs stderr tee at /tmp/parse-compute-worker.stderr.log
             - preloads wav2vec2 Aligner once; STT/ORTH providers best-effort
             - patches server._set_job_progress/_complete/_error and
               _publish_stt_partial_segment to emit queue events
             - loops over jobs and dispatches via _dispatch()
                     |
                     +-- full IPA/ORTH? -> spawn nested isolated child
                     +-- any one job failure emits an error event; worker stays alive
```

Persistent mode is an explicit operator choice via `--compute-mode=persistent`, `PARSE_COMPUTE_MODE=persistent`, or `PARSE_USE_PERSISTENT_WORKER=true`. If the worker is requested but fails to signal ready, the server should refuse to boot rather than silently degrading to threads.

## Full-mode ORTH path after MC-384

```text
/api/compute/ortho or full pipeline ORTH
        |
        v
outer launcher dispatch table
        |
        v
_compute_speaker_ortho_dispatch()
        |
        +-- run_mode != "full" -> _compute_speaker_ortho() fast concept-window path
        |
        +-- run_mode == "full" -> _compute_speaker_ortho_in_subprocess()
                                  -> _run_in_isolated_subprocess()
                                  -> _speaker_ortho_subprocess_entry()
                                  -> _compute_speaker_ortho(provider=None)
                                           |
                                           +-- duration <= threshold -> one provider.transcribe()
                                           +-- duration > threshold  -> split_audio_duration()
                                                                        -> temp WAV per chunk
                                                                        -> provider.transcribe(slice)
                                                                        -> merge_chunk_segments()
                                                                        -> chunks[] metadata
```

The Khan01 failure class is closed at two levels: the parent server is insulated by full-mode ORTH subprocess isolation, and long Tier-1 ORTH is bounded by default 10-minute chunks so one 4.5-hour recording no longer requires one monolithic provider call.

## Runtime contracts and observability

| Surface | Contract |
| --- | --- |
| Job status polling | Unchanged across all modes: parent job state is updated through `_set_job_progress`, `_set_job_complete`, and `_set_job_error`. |
| Persistent worker health | `GET /api/worker/status` returns `{mode, alive, pid, jobs_in_flight}`; non-persistent modes report `alive: null`. |
| Per-job subprocess result | `/tmp/parse-compute-<job_id>.json` is a transient `{ok, result|error, traceback}` envelope consumed by the parent monitor. |
| Per-job subprocess logs | `/tmp/parse-compute-<job_id>.stderr.log` exists for crash tails and must tee, not replace, inherited stderr. |
| Persistent worker logs | `/tmp/parse-compute-worker.stderr.log` is also tee-backed so `[WORKER]` lifecycle lines stay visible in the parent terminal. |
| Chunk progress | ORTH emits messages of the form `ORTH chunk N/M (STARTs-ENDs)`; the header job strip parses that message into `Chunk N of M`. |
| Chunk result schema | `chunks[]` entries use `idx`, `span`, `status`, optional `error_code`, and optional `error`; see [MCP schema](../mcp-schema.md#compute-job-result-shapes). |

## Maintenance invariants

- Keep the three dispatch tables synchronized: `python/server_routes/jobs.py::_compute_subprocess_entry`, `python/server_routes/jobs.py::_run_compute_job`, and `python/workers/compute_worker.py::_dispatch`.
- Full-mode ORTH and IPA must route through nested subprocess isolation in every outer compute mode. Scoped/concept-window jobs should stay fast and should not chunk.
- Provider objects must not cross process boundaries. Full-pipeline ORTH should acquire its provider inside the child/subprocess path rather than passing a cached parent provider into a child.
- Child log files must use `install_child_tee()` from `python/shared/subprocess_tee.py`; never replace `sys.stderr`/`sys.stdout` outright in a spawned compute child.
- `status == "error"` is the nested subprocess sentinel. Successful application-level partial failures should use structured fields such as `chunks[].status`, `error_code`, `failure_reason`, or `partial_*`, not a successful payload with top-level `status: "error"`.
- Chunk cancellation is between chunks for Milestone A. Completed chunks remain usable, remaining chunks report `cancelled`, and the top-level result can be `partial_cancelled`.
- The UI and MCP/API contracts are consumers of the same `chunks[]` schema; update TypeScript types, `docs/mcp-schema.md`, and this page together when the schema changes.

## Regression gates for worker/process changes

For changes touching this architecture, run the narrow gate that matches the changed surface and explain any skips in the PR:

```bash
PYTHONPATH=python python3 -m pytest -q \
  python/test_audio_chunking.py \
  python/test_compute_speaker_ipa_subprocess_isolation.py \
  python/test_compute_speaker_ortho_subprocess_isolation.py \
  python/test_compute_speaker_ortho_chunking.py \
  python/test_khan01_milestone_a_regression.py \
  python/server_routes/test_compute_dispatch_parity.py \
  python/server_routes/test_jobs_compute_subprocess_tee.py

npx vitest run \
  src/components/parse/__tests__/HeaderJobStrip.test.tsx \
  src/components/shared/__tests__/BatchReportTableRow.test.tsx
```

Backend/server PRs still need the normal backend gate from `AGENTS.md`; frontend PRs still need the normal Vitest/TypeScript gate.
