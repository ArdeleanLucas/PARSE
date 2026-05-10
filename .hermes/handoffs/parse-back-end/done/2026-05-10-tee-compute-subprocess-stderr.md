# Tee compute-subprocess and persistent-worker stderr to parent fd 2

**Date:** 2026-05-10
**Agent:** parse-back-end
**Branch:** `fix/tee-compute-subprocess-stderr`
**PR:** ArdeleanLucas/PARSE#340
**Status:** done — merged as `386f80e8dd0dba9da2547adb346c6bbfb6cc37f3`

## Goal

Restore live parent-terminal output for compute subprocess and persistent worker children that previously redirected `sys.stderr` only into per-child log files.

## Scope completed

- Added `python/shared/subprocess_tee.py::install_child_tee(log_path)`.
- Wired `python/server_routes/jobs.py::_compute_subprocess_entry` to tee `/tmp/parse-compute-{job_id}.stderr.log`.
- Wired `python/workers/compute_worker.py::worker_main` to tee `/tmp/parse-compute-worker.stderr.log`.
- Added focused tee regression tests for the shared helper, compute subprocess path, and persistent worker path.

## Evidence

- PR #340 merged with green CI.
- Smoke/test markers from the lane:
  - `[ORTH] concept-window 1/1 concept='tee-c1' → 'tee-hello'`
  - `[WORKER] dispatching job_id=tee-worker`

## Follow-up

Because Lane A (#339) landed first with a local `_LexemeRerunTee`, coordinator queued `../2026-05-10-consolidate-subprocess-tee.md` to deduplicate lexeme rerun onto the shared helper.
