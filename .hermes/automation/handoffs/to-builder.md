# parse-builder handoff — post-PR36 compute contract bundle

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-builder-next-task-post-pr36-compute-contract-bundle.md`

Short version:
- PR #36 already owns the Decisions contract work
- PRs #41 and #43 already own the remaining annotate slices
- the next Builder task is now the active-shell **compare compute contract**
- audit `ParseUI` + `RightPanel` compute-mode semantics against the live server contract
- tighten types where safe
- add regression coverage for Run / Refresh / CLEF Configure / Sources Report / auto-chained similarity / job rehydration
- patch production code only where the audit proves a real drift
- stay frontend-only and non-overlapping with PRs #36, #41, #43, #42, and #47 (with PR #46 already landed on main)
