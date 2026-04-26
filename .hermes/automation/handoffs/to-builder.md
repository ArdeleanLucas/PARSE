# parse-builder handoff — post-PR41 annotate shell follow-up

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-builder-next-task-annotate-parity-bundle.md`

Short version:
- PR #41 already owns the narrow `RegionManager` annotate parity fix
- this refreshed task is the **remaining** Builder follow-up after that slice
- inspect dirty local Builder WIP in `parse-builder-auto`, but salvage from it selectively on a fresh branch from current `origin/main`
- focus on `src/ParseUI.tsx`, `src/ParseUI.test.tsx`, and only the decision-persistence pieces that still survive oracle + contract audit
- stay frontend-only and do not overlap PR #41 or parse-back-end PR #42
