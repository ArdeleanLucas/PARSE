# MC-320 — Root and non-doc markdown audit

> **Capture-time audit plan (2026-04-21):** this plan records the markdown sweep performed on the `docs/mc-317-branch-cleanup-commands` branch after Stage 3 / PR #58 removed the legacy frontend runtime.

## Objective
Audit markdown files outside `docs/` for stale PARSE runtime, workflow, or branch assumptions, then patch any file that still reads like current operational guidance when it is no longer accurate.

## Scope
- Inventory every `*.md` file outside `docs/`.
- Confirm whether requested legacy files like `PROJECT_PLAN.md`, `CODING.md`, `INTERFACES.md`, and `doc/TASK.md` still exist in this repo.
- Audit the files that do exist for stale live instructions.
- Patch only the misleading markdown that is still current-facing.

## Capture-time facts
- Repo/worktree: `/home/lucas/gh/worktrees/parse/mc-317-branch-cleanup-commands`
- Current delivery branch: `docs/mc-317-branch-cleanup-commands`
- Stage 3 / PR #58 removed `parse.html`, `compare.html`, `review_tool_dev.html`, `js/`, and legacy launchers from the live repo.
- Current branch policy: branch from `origin/main` unless Lucas explicitly says otherwise.

## Audit method
1. List markdown files outside `docs/`.
2. Search for named files the user explicitly cares about (`PROJECT_PLAN.md`, `CODING.md`, `INTERFACES.md`, `doc/TASK.md`, and `TASK.md`).
3. Read any existing current-facing markdown files and search for stale runtime markers (deleted files, deleted branches, old frontend assumptions).
4. Patch if needed.
5. Re-run `git diff --check`, `npm run test -- --run`, and `./node_modules/.bin/tsc --noEmit`.
6. Run independent review before commit.

## Completion criteria
- We know exactly which markdown files outside `docs/` still exist.
- Any stale live instructions in those files are corrected.
- If the requested legacy/spec files do not exist in this repo, that is explicitly documented in the outcome.
