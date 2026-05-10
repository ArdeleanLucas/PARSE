# Restore live ORTH/IPA/STT terminal logs during lexeme rerun jobs

**Date:** 2026-05-10
**Agent:** parse-back-end
**Branch:** `fix/lexeme-rerun-child-stdout-tee` off origin/main

---

## Background

When the new `/api/compute/lexemes_rerun_by_tag` job (PR #338) runs, the parent terminal shows nothing but the FE poll wallpaper:

```
[backend] 127.0.0.1 - - [10/May/2026 15:05:11] "POST /api/compute/lexemes_rerun_by_tag/status HTTP/1.1" 200 -
[backend] 127.0.0.1 - - [10/May/2026 15:05:12] "POST /api/compute/lexemes_rerun_by_tag/status HTTP/1.1" 200 -
[backend] 127.0.0.1 - - [10/May/2026 15:05:13] "POST /api/compute/lexemes_rerun_by_tag/status HTTP/1.1" 200 -
...
```

The `[ORTH] loaded model …`, `[STT] xx% complete`, `[ORTH]/[IPA] concept-window i/N concept='X' → 'text'` lines (from `python/server_routes/annotate.py:1363`, `python/ai/providers/local_whisper.py`, `python/ai/providers/hf_whisper.py`, `python/ai/stt_pipeline.py`) all stop reaching the parent terminal — even though the same code emits them inside the rerun child. This is a regression vs. pre-#334 behavior.

### Root cause

PR #334 ("fix(lexeme): fence rerun IPA and ORTH subprocesses", commit `5bc9828`, 2026-05-09) introduced subprocess fencing for the per-concept rerun call. Inside `_lexeme_rerun_subprocess_entry` the spawned child unconditionally rebinds **both** stdout and stderr to a per-PID logfile and does **not** tee to the inherited fd 2:

```python
# python/server_routes/lexeme_rerun.py:123-133
def _lexeme_rerun_subprocess_entry(kind: str, payload: dict[str, Any], result_path: str) -> None:
    import faulthandler
    import os as _os
    import sys as _sys

    log_path = _child_log_path(_os.getpid(), kind)
    log_fh = open(log_path, "w", buffering=1, encoding="utf-8")
    _sys.stdout = log_fh
    _sys.stderr = log_fh
    faulthandler.enable(file=log_fh, all_threads=True)
    ...
```

So every print inside the child lands in `/tmp/parse-lexeme-rerun-{ipa|ortho}-{pid}.log`.

PR #335 ("fix(lexeme): capture rerun child diagnostics", commit `187a166`) added `_read_child_log_tail` that reads ≤50 lines on **failure** and stuffs them into the JSON `stderr_tail` field — but never replays anything to the parent's terminal.

On success, `_run_interval_in_subprocess` calls `_cleanup_child_log(child_pid, kind)` (line 247) which `os.remove`s the file silently. So during a successful tagged-rerun job the only thing the parent terminal sees is the FE polling `/api/compute/lexemes_rerun_by_tag/status`.

PR #338 (commit `0c79e82`, 2026-05-10) wrapped this rerun-by-tag in a compute job that the FE polls — making the silence very visible because the previously-synchronous endpoint now runs in a worker thread that exclusively spawns the silent children for every concept.

---

## Scope (one PR, minimal surface)

Make the per-PID child log a **tee** (parent stderr **and** the log file) instead of a replacement. This restores live transcription text in the parent terminal while preserving the OOM/segfault `stderr_tail` capture #335 added.

### Single change: `python/server_routes/lexeme_rerun.py::_lexeme_rerun_subprocess_entry`

Before:

```python
log_path = _child_log_path(_os.getpid(), kind)
log_fh = open(log_path, "w", buffering=1, encoding="utf-8")
_sys.stdout = log_fh
_sys.stderr = log_fh
faulthandler.enable(file=log_fh, all_threads=True)
```

After (sketch — implementer's choice on exact factoring):

```python
log_path = _child_log_path(_os.getpid(), kind)
log_fh = open(log_path, "w", buffering=1, encoding="utf-8")

# Preserve the parent's inherited stderr (fd 2) so live progress / model-load /
# concept-window lines still surface to the user's terminal. The per-PID log
# file remains the source of truth for _read_child_log_tail on OOM/segfault.
inherited_err = _os.fdopen(_os.dup(2), "w", buffering=1, encoding="utf-8", errors="replace")
tee = _LexemeRerunTee(log_fh, inherited_err)
_sys.stdout = tee
_sys.stderr = tee
faulthandler.enable(file=log_fh, all_threads=True)  # keep faulthandler on the file only — it requires a real fd
```

Add a small Tee helper in the same module (private, starts with `_`):

```python
class _LexemeRerunTee:
    """Write-side tee for child stdout/stderr.

    Writes to every wrapped stream, swallowing per-stream errors so a closed
    inherited stderr never crashes the child.
    """

    def __init__(self, *streams: Any) -> None:
        self._streams = tuple(streams)

    def write(self, data: str) -> int:
        n = 0
        for s in self._streams:
            try:
                n = s.write(data)
                s.flush()
            except Exception:
                pass
        return n or len(data)

    def flush(self) -> None:
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:  # pragma: no cover - faulthandler uses log_fh directly
        raise OSError("LexemeRerunTee has no single fileno")
```

Notes:

- Use `os.dup(2)` (not `sys.stderr`) because `multiprocessing.spawn` may have already replaced `sys.stderr` by the time the entry function runs; fd 2 still points at the parent's inherited terminal stream.
- `faulthandler.enable` needs a real fd, so keep it pointed at `log_fh` only — segfault tracebacks still go to the per-PID log for `_read_child_log_tail` to recover.
- Do **not** change `_cleanup_child_log` or `_read_child_log_tail`. The on-failure tail capture is correct; it only became invisible because nothing was teeing on success.

### Out of scope

- Any change to `_run_interval_in_subprocess` parent-side timeout/exit-code handling.
- Any change to PR #335's `stderr_tail` JSON field on errors.
- Removing the per-PID logfile entirely (it stays — `_read_child_log_tail` on OOM/segfault still depends on it).
- Frontend changes (none needed — this only affects the parent's terminal stream).
- Touching `lexeme_rerun_handlers.py`, `tag_filtered_rerun_handlers.py`, `annotate.py`, or any other compute path.
- Any other "missing log text" regression outside the lexeme rerun subprocess fence.

---

## Files to modify

- `python/server_routes/lexeme_rerun.py` — add `_LexemeRerunTee`, change `_lexeme_rerun_subprocess_entry` to dup fd 2 and tee.
- `python/server_routes/test_lexeme_rerun_subprocess_isolation.py` — extend with the regression tests below.

---

## Tests (regression coverage required)

The existing `python/server_routes/test_lexeme_rerun_subprocess_isolation.py` already exercises the subprocess entry. Add:

1. **`test_child_stderr_reaches_parent_fd2`** — most important regression. Spawn the real child via `_run_interval_in_subprocess` against a stub `_run_ortho_interval` (monkeypatched to `print("[ORTH] concept-window 1/1 concept='c1' → 'hello'", file=sys.stderr)` then return `"hello"`). Capture parent fd 2 by `os.pipe()` + `os.dup2(write_end, 2)` around the call. Assert the captured bytes contain the `[ORTH]` line.

2. **`test_child_stdout_reaches_parent_fd1`** — same shape but the stub uses bare `print(...)`. Assert the parent-side fd 1 capture contains the line.

3. **`test_child_log_still_captured_on_failure`** — stub raises `RuntimeError("boom")` after printing two lines. Assert the resulting `LexemeRerunSubprocessError.stderr_tail` contains both lines AND the parent fd 2 capture also contains them (proves tee, not replacement).

4. **`test_child_log_cleaned_up_on_success`** — preserve the existing assertion that `/tmp/parse-lexeme-rerun-{kind}-{pid}.log` does not exist after a successful run.

5. **`test_tee_swallows_closed_inherited_stream`** — directly construct `_LexemeRerunTee(open(os.devnull, "w"), closed_stream)`, write, assert no exception bubbles. (Defensive — `multiprocessing.spawn` can land in odd terminal states.)

Mock the actual ORTH/IPA work end-to-end. Do NOT load real wav2vec2 or HF Whisper in CI.

---

## Validation

BLOCK_LIVE_PROCESS_ISOLATION

Standard gates from the worktree root:

```bash
npm run test --silent
PYTHONPATH=python python -m pytest python/ -x -q
npm run typecheck
npm run build
```

Targeted module run for fast iteration:

```bash
PYTHONPATH=python python -m pytest python/server_routes/test_lexeme_rerun_subprocess_isolation.py -x -q
```

Isolated backend smoke (`PARSE_PORT=18766` against `/tmp/parse-isolation-rerun-stdout-tee/`, NEVER `/home/lucas/parse-workspace`):

- Seed a tiny fixture: one speaker, two tagged concept windows.
- POST `/api/lexemes/rerun-by-tag` with the tag.
- Capture the parent server's stderr stream during the run (e.g. tee `parse-run` stderr to a file, or run `python -u -c "import server; server.main()"` with stderr redirected).
- Assert the captured stream contains at least one `[ORTH]`/`[IPA]` line **and** at least one `concept-window` line during the job (not only after).
- `/api/config` stays 200 throughout.

Mock providers in unit tests; no real wav2vec2 or HF Whisper inference in CI.

`git fetch origin --quiet --prune` before reporting `mergeStateStatus`. PR must be on `ArdeleanLucas/PARSE`. Do NOT merge.

---

## Acceptance criteria

- A live rerun-by-tag job emits `[ORTH]`/`[IPA]`/`[STT]` lines and `concept-window i/N concept='…' → 'text'` to the parent terminal as the work happens.
- Per-PID log file at `/tmp/parse-lexeme-rerun-{kind}-{pid}.log` still exists during the run and is still cleaned up on success.
- On OOM/segfault/timeout, `LexemeRerunSubprocessError.stderr_tail` is still populated (PR #335 behavior preserved).
- `faulthandler` segfault tracebacks still land in the per-PID log file.
- All four standard gates green.
- Fresh `mergeStateStatus=CLEAN` after refetch.
- One PR on `ArdeleanLucas/PARSE`.

---

## Reply format

After the PR is open:

1. PR URL (must contain `ArdeleanLucas/PARSE`).
2. ≤5 bullets: tee helper added, dup-fd-2 entry change, regression tests added, isolated smoke evidence, no FE changes.
3. List of files modified with line ranges.
4. One pasted line from the isolated smoke capture proving a live `[ORTH]`/`[IPA]` line reached the parent stderr during the job.
5. Tail of the validation output.

Refetch before reporting mergeable status. Do NOT merge.
