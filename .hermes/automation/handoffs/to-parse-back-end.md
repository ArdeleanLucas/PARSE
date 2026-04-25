# To parse-back-end

Status: pending

Current instruction:
- Implement the next backend-safe PARSE-rebuild slice in `/home/lucas/gh/worktrees/PARSE-rebuild/parse-back-end-auto` on `auto/parse-back-end`.
- Follow the full prompt at `.hermes/plans/2026-04-25_234447-parse-back-end-job-observability-handoff-prompt.md`.

Lane boundary:
- This is the backend lane.
- Stay out of `src/**` and all parse-builder-owned frontend shell work.
- Safe ownership for this slice is `python/server.py`, `python/app/http/**`, and backend Python tests only.

Short version:
1. Extract the generic jobs/worker-status HTTP handler cluster out of `python/server.py`.
2. Prefer a new helper such as `python/app/http/job_observability_handlers.py`.
3. Add direct tests first, then keep thin wrappers in `server.py`.
4. Re-run targeted Python validation plus full rebuild gates.

Grounded seam locations:
- `_api_get_jobs()` — around `python/server.py:6760`
- `_api_get_job()` — around `python/server.py:6786`
- `_api_get_job_logs()` — around `python/server.py:6795`
- `_api_get_jobs_active()` — around `python/server.py:6821`
- `_api_get_job_error_logs()` — around `python/server.py:6826`
- `_api_get_worker_status()` — around `python/server.py:6873`
