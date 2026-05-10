---
agent: parse-back-end
queued_by: parse-coordinator
queued_at: 2026-05-10T14:20:00Z
status: done
related_prs:
  - 339
  - 340
  - 344
---

# Consolidate lexeme rerun child tee onto shared subprocess helper

## Goal

Delete the duplicate in-file `_LexemeRerunTee` from `python/server_routes/lexeme_rerun.py` and use `install_child_tee` from `python/shared/subprocess_tee.py` instead.

## Why this is next

PR #339 restored live `[ORTH]`/`[IPA]`/`[STT]` lexeme-rerun output with a narrow in-file tee. PR #340 introduces the reusable `python/shared/subprocess_tee.py` helper for compute subprocess and persistent-worker entries. Once PR #340 lands on `main`, lexeme rerun should share that helper so future spawn-child stderr fixes have one implementation.

## Grounded context

- PR #339: `fix(lexeme): tee rerun child output` landed `_LexemeRerunTee` in `python/server_routes/lexeme_rerun.py`.
- PR #340: `fix(compute): tee child stderr to parent terminal` adds `python/shared/subprocess_tee.py::install_child_tee`.
- Coordinator grep target after this follow-up:
  `grep -rn 'sys\.stderr *= *open' python/ | grep -v test_ | grep -v shared/subprocess_tee.py` returns nothing.

## Specific task / scope boundary

In scope, one small backend PR (≤30 LoC production delta preferred):

1. In `python/server_routes/lexeme_rerun.py`, import `install_child_tee` from `shared.subprocess_tee`.
2. Delete the private `_LexemeRerunTee` class.
3. In `_lexeme_rerun_subprocess_entry`, replace the local `open(...)` + `os.dup(...)` + `_LexemeRerunTee(...)` stream setup with:
   `log_fh, inherited_out, inherited_err = install_child_tee(log_path)`
   or the closest project-style equivalent that keeps handles alive for the child lifetime.
4. Preserve existing `_read_child_log_tail`, `_cleanup_child_log`, timeout/OOM handling, and faulthandler behavior.
5. Update `python/server_routes/test_lexeme_rerun_subprocess_isolation.py` only if it imports or asserts the local tee class directly.

Out of scope:

- Any frontend change.
- Any parse-run/browser/manual smoke.
- Any change to `python/server_routes/jobs.py` or `python/workers/compute_worker.py` beyond import fallout.
- Removing per-PID child log files.

## Required validation

Run from a fresh worktree off current `origin/main` after PR #340 is merged:

```bash
git fetch origin --quiet --prune
PYTHONPATH=python python -m pytest python/server_routes/test_lexeme_rerun_subprocess_isolation.py python/shared/test_subprocess_tee.py -x -q
PYTHONPATH=python python -m pytest python/ -x -q
uvx ruff check python/ --select E9,F63,F7,F82
grep -rn 'sys\.stderr *= *open' python/ | grep -v test_ | grep -v shared/subprocess_tee.py
```

The final grep must produce no output.

## Completion

Completed by PR #344 (`refactor: reuse shared subprocess tee for lexeme reruns`). Coordinator re-ran the stderr-fence audit (`search_files` for `sys\.stderr\s*=\s*open`) and refreshed `docs/architecture/compute-subprocess-stdio.md` so the active queue no longer points at a shipped follow-up.
