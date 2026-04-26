# parse-back-end handoff — worktree hygiene cleanup

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-back-end-next-task-worktree-hygiene.md`

Short version:
- current rebuild `origin/main` is healthy
- the local worktree inventory is too noisy
- prune stale review/audit worktrees safely
- protect open PR lanes (`#41`, `#36`) and the dirty ambiguous `parse-builder-auto` tree
- report before/after counts and exact removals
