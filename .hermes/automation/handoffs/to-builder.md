# parse-builder handoff — post-PR45 Actions menu contract cleanup bundle

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-builder-next-task-post-pr45-actions-menu-contract-bundle.md`

Short version:
- PR #36 remains the active Builder lane
- PR #45 queued the compute-contract successor slice
- the next Builder task after that is the remaining **ParseUI Actions menu contract cleanup** bundle
- audit remaining Actions-menu handlers in `ParseUI.tsx`
- normalize ad hoc inline export/import logic onto shared typed-client-backed helpers where justified
- add focused Actions-menu regression coverage
- keep the visible UI identical
- stay frontend-only and non-overlapping with PRs #36, #45, #47, #42, #41, and #43
