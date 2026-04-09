# MC-305 — Branch cleanup findings PR

## Objective
Submit a docs-only PR that captures the current PARSE GitHub branch-cleanup recommendations based on live remote branch state, PR state, and prior cleanup audits.

## Scope
1. Work in the canonical docs lane: `docs/parseui-planning` -> `main`.
2. Re-audit the current branch set against `origin/main`.
3. Write a concise findings memo with three buckets:
   - delete now
   - keep as rolling branches
   - do not delete yet / inspect first
4. Include worktree caveats for `feat/annotate-react` and `feat/compare-react`.
5. Open a PR and request review from `TrueNorth49`.

## Key facts from current audit
- `docs/phase4-c5-c6-signoff` still has open PR #7, so it should not be deleted.
- `feat/parseui-unified-shell` has been merged repeatedly and should remain the rolling code branch.
- `docs/parseui-planning` is the rolling docs branch.
- `feat/annotate-ui-redesign` and `feat/parse-ai-connect-onboarding` still carry commits not present on `main`.
- `feat/compare-react` has no surviving code delta relative to `main`, but still has a local attached worktree.

## Completion criteria
- New findings doc written in `docs/plans/`.
- Docs branch committed and pushed.
- PR to `main` opened with reviewer `TrueNorth49`.
- Mission Control and daily logs updated.
