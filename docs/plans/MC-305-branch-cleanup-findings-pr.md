# MC-305 — Branch cleanup findings PR

> **Historical note:** this task captured the branch-cleanup recommendation state before the later pruning pass completed. Keep it as task history; the repo has since moved to `origin/main` as the only base for new work.

## Objective
Submit a docs-only PR that captures the current PARSE GitHub branch-cleanup recommendations based on live remote branch state, PR state, and prior cleanup audits.

## Scope
1. Work in a docs branch cut from `origin/main` (historical note: `docs/parseui-planning` was the old rolling docs lane and has since been deleted).
2. Re-audit the current branch set against `origin/main`.
3. Write a concise findings memo with three buckets:
   - delete now
   - keep as rolling branches
   - do not delete yet / inspect first
4. Include worktree caveats for `feat/annotate-react` and `feat/compare-react`.
5. Open a PR and request review from `TrueNorth49`.

## Key facts from current audit
- `docs/phase4-c5-c6-signoff` still has open PR #7, so it should not be deleted.
- Historical finding at capture time: `feat/parseui-unified-shell` was still treated as the rolling code branch.
- Historical finding at capture time: `docs/parseui-planning` was still treated as the rolling docs branch.
- Historical finding at capture time: `feat/annotate-ui-redesign` and `feat/parse-ai-connect-onboarding` still carried commits not present on `main`; both were deleted in the later cleanup pass.
- `feat/compare-react` has no surviving code delta relative to `main`, but still has a local attached worktree.

## Completion criteria
- New findings doc written in `docs/plans/`.
- Docs branch committed and pushed.
- PR to `main` opened with reviewer `TrueNorth49`.
- Mission Control and daily logs updated.
