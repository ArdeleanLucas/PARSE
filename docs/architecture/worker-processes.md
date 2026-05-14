# Worker process architecture

This page is the process-topology companion to [Compute architecture](compute.md). It records the worker/process design that landed across MC-384 (PRs #411-#440): outer compute launchers, nested heavy-stage subprocess isolation, and chunk-aware long-file execution.

## What changed in the MC-384 worker/process slice

| PR | Shipped worker/process contract |
| --- | --- |
| [#411](https://github.com/ArdeleanLucas/PARSE/pull/411) | Added pure audio chunking primitives in `python/workers/audio_chunking.py`: `ChunkSpan`, `ChunkResult`, `split_audio_duration()`, and `merge_chunk_segments()`. |
| [#412](https://github.com/ArdeleanLucas/PARSE/pull/412) | Added the shared nested spawn helper `_run_in_isolated_subprocess()` and routed full-mode IPA through standalone subprocess isolation across thread, per-job subprocess, and persistent-worker modes. |
| [#413](https://github.com/ArdeleanLucas/PARSE/pull/413) | Added full-mode ORTH subprocess isolation and wired ORTH dispatch through the same nested isolation layer in every outer compute launcher. |
| [#414](https://github.com/ArdeleanLucas/PARSE/pull/414) | Added long-file Tier-1 ORTH chunking inside the isolated ORTH child, defaulting to 10-minute adjacent chunks with temp-WAV cleanup, between-chunk cancellation, and structured `chunks[]` results. |
| [#415](https://github.com/ArdeleanLucas/PARSE/pull/415) | Taught TypeScript contracts and batch-result components to tolerate `chunks[]` and new structured error codes. |
| [#416](https://github.com/ArdeleanLucas/PARSE/pull/416) | Added the maintained compute architecture page, MCP result schema, and Khan01 long-file regression harness. |
| [#417](https://github.com/ArdeleanLucas/PARSE/pull/417) | Added live chunk-progress display in the top job strip and partial/all-error chunk coloring in the batch report. |
| [#420](https://github.com/ArdeleanLucas/PARSE/pull/420) | Added long-file full-file STT chunking with the same `chunks[]` result shape and flat-cache compatibility. |
| [#427](https://github.com/ArdeleanLucas/PARSE/pull/427) | Hardened the `chunks[]` cache/result split and UI progress contract. |
| [#428](https://github.com/ArdeleanLucas/PARSE/pull/428) | Wrapped full-file STT in nested subprocess isolation. |
| [#440](https://github.com/ArdeleanLucas/PARSE/pull/440) | Added the unified device resolver and per-stage device environment overrides consumed by STT, ORTH, and IPA. |

## Layer model

PARSE now has three distinct worker layers. They are intentionally separate; do not collapse their responsibilities in future changes.

1. **Outer compute launcher** — selected by `_resolve_compute_mode()` in `python/server_routes/jobs.py`.
   - `thread`: one background thread in the HTTP server process.
   - `subprocess`: one spawned Python process per compute job plus a parent monitor thread.
   - `persistent`: one long-lived `parse-compute-worker` process with queues and a parent monitor thread.
2. **Nested heavy-step isolation** — selected by compute intent, not by outer launcher.
   - Full-file STT runs through `server_routes.media._run_stt_job_in_subprocess()`.
   - Full-mode ORTH and IPA run through `server_routes.annotate._run_in_isolated_subprocess()` wrappers.
   - Concept-window/scoped STT/ORTH/IPA stay on fast bounded paths and should not pay full-mode isolation overhead.
3. **Chunking inside isolated Tier-1 stages** — selected by duration.
   - Long full-file STT and full-mode ORTH split Tier-1 transcription into adjacent audio slices.
   - Chunks are not separate worker processes; they are sequential provider calls inside the isolated STT/ORTH subprocess.
   - ORTH Tier 2 `ortho_words` is rebuilt once after Tier-1 chunks are merged back to audio-global timestamps.
   - IPA is interval-driven and does not chunk by whole-audio duration.

## Code anchors

| Concern | Source anchor |
| --- | --- |
| Mode resolution | `python/server_routes/jobs.py::_resolve_compute_mode()` chooses CLI override, persistent shortcut, `PARSE_COMPUTE_MODE`, then default `thread`. |
| Outer launcher | `python/server_routes/jobs.py::_launch_compute_runner()` dispatches to thread, per-job subprocess, or persistent mode. |
| Per-job subprocess | `python/server_routes/jobs.py::_launch_compute_subprocess()` starts the spawned child and parent monitor; `_compute_subprocess_entry()` is the child entry. |
| Persistent worker startup | `python/server.py::_start_persistent_worker()` starts `WorkerHandle`; `python/workers/compute_worker.py` waits for the ready event. |
| Persistent worker dispatch | `python/workers/compute_worker.py::_dispatch()` mirrors compute aliases across outer modes. |
| Nested isolation helper | `python/server_routes/annotate.py::_run_in_isolated_subprocess()` owns spawn, timeout, result-file parsing, and error-code mapping for full-mode ORTH/IPA children; STT calls it through the server shim from `server_routes.media`. |
| Full-file STT routing | `python/server_routes/media.py::_compute_stt()` routes `run_mode='full'` to `_run_stt_job_in_subprocess()` and scoped modes to `_compute_speaker_stt()`. |
| Full-mode ORTH routing | `python/server_routes/annotate.py::_compute_speaker_ortho_dispatch()` routes full-mode ORTH to `_compute_speaker_ortho_in_subprocess()` and scoped ORTH to the fast path. |
| Chunk loops | `python/server_routes/media.py::_run_stt_job()` and `python/server_routes/annotate.py::_compute_speaker_ortho()` measure duration, split spans, slice temp WAVs, emit chunk progress, classify chunk errors, and merge segments. |
| Device resolver | `python/ai/device.py::resolve_compute_device()` applies stage env → global env → config → default precedence. |
| Worker status endpoint | `python/server_routes/jobs.py::_api_get_worker_status()` returns `{mode, alive, pid, jobs_in_flight}` for persistent-worker observability. |

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
                                  +-- full STT?  -> spawn nested STT child
                                  +-- full ORTH? -> spawn nested ORTH child
                                  +-- full IPA?  -> spawn nested IPA child
                                  |
                                  +-- scoped STT/ORTH/IPA? -> run fast bounded path
```

Use this mode for ordinary development and fast scoped jobs. It has the least process overhead, but full-file/full-mode heavy stages still get nested isolation.

### `subprocess` mode

```text
HTTP server process
  _launch_compute_runner(mode="subprocess")
        |
        +-- spawn per-job child: _compute_subprocess_entry(...)
        |       |
        |       +-- imports server and dispatches compute type
        |       +-- full STT/ORTH/IPA? -> spawn nested isolated child
        |       +-- writes /tmp/parse-compute-<job_id>.json
        |       +-- tees stderr to /tmp/parse-compute-<job_id>.stderr.log
        |
        +-- parent monitor thread joins child, reads result JSON,
            and updates the in-memory job registry for normal status polling
```

This mode protects the HTTP server from per-job Python/process failures. It costs a fresh Python import/model load per job and can still use nested heavy-stage isolation inside the child.

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
             - patches server job-state functions into queue emitters
             - loops over jobs and dispatches via _dispatch()
                     |
                     +-- full STT/ORTH/IPA? -> spawn nested isolated child
                     +-- scoped jobs? -> run in worker process
```

Persistent mode is an explicit operator choice via `--compute-mode=persistent`, `PARSE_COMPUTE_MODE=persistent`, or `PARSE_USE_PERSISTENT_WORKER=true`. If the worker is requested but fails to signal ready, the server should refuse to boot rather than silently degrading to threads.

## Full-file STT path after MC-384

```text
/api/stt or /api/compute/stt with run_mode="full"
        |
        v
outer launcher dispatch table
        |
        v
server_routes.media._compute_stt()
        |
        +-- run_mode != "full" -> scoped _compute_speaker_stt() path
        |
        +-- run_mode == "full" -> _run_stt_job_in_subprocess()
                                  -> _run_in_isolated_subprocess()
                                  -> _run_stt_job_subprocess_entry()
                                  -> _run_stt_job()
                                           |
                                           +-- duration <= threshold -> one provider.transcribe()
                                           +-- duration > threshold  -> split_audio_duration()
                                                                        -> temp WAV per chunk
                                                                        -> provider.transcribe(slice)
                                                                        -> merge_chunk_segments()
                                                                        -> chunks[] metadata
```

The Fail01 failure class is closed at two levels: the parent server is insulated by full-file STT subprocess isolation, and long STT decoding is bounded by default 10-minute chunks so a repetition loop in one region does not stop the entire recording.

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
| Chunk progress | STT emits `STT chunk N/M (STARTs–ENDs)` and ORTH emits `ORTH chunk N/M (STARTs-ENDs)`; the header job strip parses those messages into `Chunk N of M`. |
| Chunk result schema | `chunks[]` entries use `idx`, `span`, `status`, optional `error_code`, and optional `error`; see [MCP schema](../mcp/schema.md#compute-job-result-shapes). |
| Resolved device | Stage result payloads expose the resolved/effective device as `device`; completion logs include `device=...`. |

## Maintenance invariants

- Keep the three dispatch tables synchronized: `python/server_routes/jobs.py::_compute_subprocess_entry`, `python/server_routes/jobs.py::_run_compute_job`, and `python/workers/compute_worker.py::_dispatch`.
- Full-file/full-mode STT, ORTH, and IPA must route through nested subprocess isolation in every outer compute mode. Scoped/concept-window jobs should stay fast and should not chunk by whole-audio duration.
- Provider objects must not cross process boundaries. Full-pipeline ORTH/STT should acquire providers inside the child/subprocess path rather than passing cached parent providers into a child.
- Child log files must use `install_child_tee()` from `python/shared/subprocess_tee.py`; never replace `sys.stderr`/`sys.stdout` outright in a spawned compute child.
- `status == "error"` is the nested subprocess sentinel. Successful application-level partial failures should use structured fields such as `chunks[].status`, `error_code`, `failure_reason`, or `partial_*`, not a successful payload with top-level `status: "error"`.
- Chunk cancellation is between chunks. Completed chunks remain usable, remaining chunks report `cancelled`, and the top-level result can be `cancelled` or `partial_cancelled` depending on stage/path.
- The UI, MCP/API docs, and TypeScript contracts are consumers of the same `chunks[]` schema; update `src/api/contracts/*`, `docs/mcp/schema.md`, and this page together when the schema changes.
- Adding or renaming compute env vars requires updating [Compute architecture](compute.md), [Environment variables](../reference/environment-variables.md), and the doc drift guard in `python/test_docs_compute_env_vars.py`.

## Regression gates for worker/process changes

For changes touching this architecture, run the narrow gate that matches the changed surface and explain any skips in the PR:

```bash
PYTHONPATH=python python3 -m pytest -q   python/test_audio_chunking.py   python/test_compute_speaker_ipa_subprocess_isolation.py   python/test_compute_speaker_ortho_subprocess_isolation.py   python/test_compute_speaker_ortho_chunking.py   python/test_stt_chunking_synthetic.py   python/test_stt_subprocess_isolation.py   python/test_khan01_milestone_a_regression.py   python/server_routes/test_compute_dispatch_parity.py   python/server_routes/test_jobs_compute_subprocess_tee.py   python/test_docs_compute_env_vars.py

npx vitest run   src/components/parse/__tests__/HeaderJobStrip.test.tsx   src/components/shared/__tests__/BatchReportTableRow.test.tsx
```

Backend/server PRs still need the normal backend gate from `AGENTS.md`; frontend PRs still need the normal Vitest/TypeScript gate.
