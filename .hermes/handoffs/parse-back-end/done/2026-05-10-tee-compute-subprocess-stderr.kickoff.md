<parse-back-end_kickoff status="done">
  <worktree branch="fix/tee-compute-subprocess-stderr" repo="ArdeleanLucas/PARSE" />
  <task>Introduce python/shared/subprocess_tee.py::install_child_tee(log_path), wire it into python/server_routes/jobs.py::_compute_subprocess_entry and python/workers/compute_worker.py::worker_main, and preserve per-child log/faulthandler behavior while teeing live output to inherited fd 1/2.</task>
  <result>Completed in PR #340, merged as 386f80e8dd0dba9da2547adb346c6bbfb6cc37f3.</result>
</parse-back-end_kickoff>
