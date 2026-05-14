# Contributing to PARSE

Thanks for improving PARSE. The project values fieldwork reliability, contract fidelity, and reviewable changes.

## Workflow
1. Branch from current `origin/main` in an isolated worktree.
2. Keep changes scoped to one user-visible or contract-visible outcome.
3. Update docs when behavior, env vars, result schemas, or operator workflow changes.
4. Run the relevant validation gates before opening a PR.
5. Open PRs against `ArdeleanLucas/PARSE` with base `main`.

## Validation expectations
- Frontend changes: `npx vitest run` and `./node_modules/.bin/tsc --noEmit`.
- Backend changes: focused pytest during iteration, then the current backend sweep required by `AGENTS.md`.
- Docs-only changes: `git diff --check`, link/acceptance audit, and any doc drift guard relevant to the touched page.

## Documentation standards
- Keep the root README timeless and user-facing.
- Put task-specific notes in [release notes](../release-notes/) or [architecture decisions](architecture-decisions/).
- Prefer plain-language explanations before implementation detail.
- Keep internal links relative and verify them before submitting.

## Safety
Do not commit local credentials, model binaries, generated workspaces, or machine-local config files. Use examples and templates instead.
