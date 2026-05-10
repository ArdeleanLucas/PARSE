# Compute subprocess stdio contract

**Date:** 2026-05-10  
**Related PRs:** #339 (`fix(lexeme): tee rerun child output`), #340 (`fix(compute): tee child stderr to parent terminal`)  
**Coordinator audit:** compute-child stdout/stderr fence regression introduced by PR #334 and made visible in job-tracked reruns by PR #338.

## Contract

PARSE compute children that run under `multiprocessing.get_context("spawn")` may write a per-child logfile for OOM/segfault post-mortems, but they must not redirect stdout/stderr away from the parent terminal.

Use this shape:

```text
parent terminal fd 1/2
        ▲
        │ inherited fd dup via os.dup(1)/os.dup(2)
spawned child entry
        │
        ├─ sys.stdout/sys.stderr -> _Tee(log_fh, inherited fd)
        │
        └─ per-child logfile -> faulthandler + parent crash-tail recovery
```

The canonical helper is `python/shared/subprocess_tee.py::install_child_tee(log_path)`:

1. opens the log file line-buffered;
2. duplicates inherited fd 1 and fd 2;
3. rebinds `sys.stdout` and `sys.stderr` to write-side tees;
4. keeps `faulthandler.enable(...)` pointed at the real log file descriptor.

## Why this exists

PR #334 fenced lexeme rerun ORTH/IPA work in child processes so GPU/model failures could not poison the parent process. The entry function opened a per-PID log and rebound child stdout/stderr there. That preserved failure tails but removed live parent-terminal progress. PR #338 then made tagged reruns job-tracked, so Lucas saw only `/api/compute/lexemes_rerun_by_tag/status` polling while `[ORTH]`, `[IPA]`, `[STT]`, and concept-window lines disappeared.

PR #339 restored lexeme-rerun live output. PR #340 generalized the fix for compute subprocesses and persistent workers.

## Entry inventory

| Entry | File/lines at audit | Current stdio behavior | Status |
|---|---:|---|---|
| Lexeme rerun child | `python/server_routes/lexeme_rerun.py:154` | Local `_LexemeRerunTee` writes to per-PID log + inherited fd 1/2. | Fixed by #339; dedupe queued in `.hermes/handoffs/parse-back-end/2026-05-10-consolidate-subprocess-tee.md`. |
| Compute subprocess child | `python/server_routes/jobs.py:321`, install at `:337` | Calls `install_child_tee('/tmp/parse-compute-{job_id}.stderr.log')`. | Fixed by #340. |
| Persistent compute worker | `python/workers/compute_worker.py:454`, install at `:463` | Calls `install_child_tee('/tmp/parse-compute-worker.stderr.log')`. | Fixed by #340. |

## Confirmed-clean entries

These were checked during the 2026-05-10 audit and should not be re-flagged as stderr-fence regressions:

| Entry | Why clean |
|---|---|
| `python/server_routes/annotate.py:_full_pipeline_ipa_subprocess_entry` (`:2546`) | Spawn child writes checkpoint/result files but does not replace `sys.stderr` with a logfile. |
| `python/ai/tools/artifact_tools.py:202-220` | Temporarily captures `sys.stderr` into `StringIO` only around local `source_index` helper calls and restores `sys.stderr` in `finally`; not a long-running compute child. |
| `subprocess.run(..., capture_output=True)` wrappers | Short-lived external processes (`ffmpeg`, `ffprobe`, tasklist, script boot checks) intentionally capture child process output; they are not PARSE compute child entries that emit live ORTH/IPA/STT progress. |

## Audit command

Run this before approving new spawn-child compute work:

```bash
grep -rn 'sys\.stderr *= *open' python/ | grep -v test_ | grep -v shared/subprocess_tee.py
```

Expected result after #340: no output. If a future match appears in a `multiprocessing.spawn` child entry, replace it with `install_child_tee(log_path)` or prove the child is not a live progress path.
