# parse-builder handoff — post-PR52 compare/config cleanup bundle

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-builder-next-task-post-pr52-compare-config-cleanup-bundle.md`

Short version:
- this is the next bundled frontend cleanup task after the currently open Builder implementation pair (`#50`, `#52`)
- ship one fresh implementation PR from current `origin/main`
- replace the remaining bare CLEF fetch in `BorrowingPanel` with the typed client path
- make `configStore.update()` use the real `updateConfig()` persistence route
- harden `CognateControls` so failed saves do not silently look successful
- absorb/supersede the still-relevant work from closed micro-PRs `#27`, `#29`, and `#31`
- keep the visible UI identical
- stay frontend-only and non-overlapping with PRs `#50` and `#52`
