# parse-builder handoff — decision import/export contract follow-up

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-builder-next-task-annotate-parity-bundle.md`

Short version:
- PR #41 already owns `RegionManager`
- PR #43 already owns the offset-shell regression salvage slice
- the next Builder task is now the still-broken **Decisions** workflow
- unify Actions-menu and right-panel load/save behavior
- stop exporting whole enrichments as `parse-decisions.json`
- salvage `src/lib/decisionPersistence.ts` and any justified store changes from `parse-builder-auto` selectively, not blindly
- stay frontend-only and non-overlapping with PRs #43, #42, and #44
