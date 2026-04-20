# MC-317 — Branch cleanup deletion commands PR

## Objective
Create a docs-only PR that records the exact currently validated PARSE branch-deletion commands for the canonical lowercase repo, without executing any deletions in this task.

## Scope
1. Re-verify the live branch state on `ArdeleanLucas/PARSE` against current `origin/main`.
2. Distinguish safe remote deletes, safe local merged deletes, worktree-blocked deletes, and optional force-delete snapshot branches.
3. Write an operator memo with exact commands grounded in the current audit.
4. Open a docs-only PR from `origin/main` and request review.

## Key facts to preserve
- Canonical active repo: `/home/lucas/gh/ardeleanlucas/parse`
- Archival clone: `/home/lucas/gh/ArdeleanLucas/PARSE`
- Current reference trunk at capture time: `origin/main` = `13d16b2cba8daf747cf8e9ca8701f9dd169b16c9`
- Current live GitHub branch set contains 12 non-`main` remote branches, all verified as merged leftovers (`git cherry = 0`, branch-only commits vs `origin/main` = `0`)
- Local cleanup must treat worktree-attached branches separately
- No destructive action is part of MC-317; this task is documentation + PR only

## Files in scope
- `docs/plans/MC-317-branch-cleanup-command-pr.md`
- `docs/plans/branch-cleanup-delete-commands-2026-04-21.md`
- PR metadata/body

## Constraints
- Branch from `origin/main` in `/home/lucas/gh/ardeleanlucas/parse`
- Do not delete any branch in this task
- Keep uppercase-clone archival cleanup out of the default command set
- Run the standard PARSE docs-only validation gate before opening the PR

## Completion criteria
- Exact command memo written under `docs/plans/`
- Commands reflect the re-verified current branch state, not the earlier pre-PR-#76 snapshot
- `git diff --check` passes
- `npm run test -- --run` passes
- `./node_modules/.bin/tsc --noEmit` passes
- PR opened on `ArdeleanLucas/PARSE` with a clickable link
