# parse-back-end handoff — post-PR46 compute + offset HTTP contract bundle

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-back-end-next-task-post-pr46-compute-offset-http-bundle.md`

Short version:
- PR #46 is the current parse-back-end implementation lane
- the next parse-back-end task after that is the backend-only **compute + offset HTTP contract** bundle
- extract the inline compute/offset routes from `python/server.py` into app-layer HTTP helpers
- preserve all compatibility behavior (`jobId`/`job_id`, typed/generic status, `/api/{computeType}/status` alias, snake_case/camelCase offset inputs)
- add dedicated backend route-level tests and keep OpenAPI honest
- stay backend-only and non-overlapping with PRs #46, #45, #42, #41, #43, and #36
