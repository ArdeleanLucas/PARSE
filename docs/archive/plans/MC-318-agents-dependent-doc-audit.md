> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../../).

# MC-318 — AGENTS.md dependent docs audit

## Objective
Audit every current PARSE doc that explicitly relies on `AGENTS.md` and refresh any stale references so the repo's operator-facing documentation matches the updated `AGENTS.md` and current repo reality.

## Scope
- Search the canonical PR worktree for references to `AGENTS.md`
- Separate active operator docs from archived historical docs
- For active docs, verify whether the referenced `AGENTS.md` claims still hold after the 2026-04-21 refresh
- Patch only stale or misleading references
- Keep historical/archive docs historical unless they incorrectly present stale branch guidance as current instructions

## Key facts before editing
- Canonical repo: `/home/lucas/gh/ardeleanlucas/parse`
- Active docs PR worktree: `/home/lucas/gh/worktrees/parse/mc-317-branch-cleanup-commands`
- Current delivery branch: `docs/mc-317-branch-cleanup-commands`
- `AGENTS.md` was just refreshed on this branch to fix:
  - impossible future update date
  - old integration-branch wording
  - outdated `>=132` test-floor references
  - stale “integration changes” pre-push wording

## Audit method
1. Search the repo for `AGENTS.md` references.
2. Group results into:
   - active docs (`docs/plans/*`, `doc/*`, root docs)
   - archive/history docs (`docs/archive/**` and clearly historical memos)
3. Read each active referencing doc and compare its claims against current `AGENTS.md` + repo reality.
4. Patch only the stale docs.
5. Re-run docs validation (`git diff --check`) plus PARSE gates (`npm run test -- --run`, `./node_modules/.bin/tsc --noEmit`).
6. Run independent review on the docs diff before final commit.

## Candidate docs to inspect first
- `AGENTS.md`
- `docs/plans/parsebuilder-todo.md`
- `docs/plans/parseui-current-state-plan.md`
- `docs/plans/react-vite-pivot.md`
- `docs/plans/repo-state-cleanup-and-architecture-unification.md`
- Any other non-archived doc returned by the search

## Completion criteria
- Every current non-archived doc that depends on `AGENTS.md` is checked
- Stale operator-facing references are corrected
- Archived historical references are either left as history or clearly labeled if they still read like live instructions
- PR branch updated, validated, and ready for Lucas review
