> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../../).

# MC-319 — Stale docs that still read like live instructions

> **Capture-time audit plan (2026-04-21):** this file records the stale-doc sweep performed on the `docs/mc-317-branch-cleanup-commands` branch. Treat the repo/worktree facts below as audit-time context, not evergreen operating defaults.

## Objective
Find PARSE docs that still read as current operational guidance even though they point to deleted branches, removed vanilla-JS runtimes, or obsolete workflows, then patch them so the repo is safer to operate from.

## Scope
- Search current docs for stale live-instruction patterns, not just `AGENTS.md` references.
- Include both active docs and archived docs that still read like actionable runbooks.
- Patch only the docs that are genuinely misleading in current repo reality.
- Keep historical content as history; prefer banners/notes over rewriting substantive past work.

## Capture-time repo facts
- Canonical repo: `/home/lucas/gh/ardeleanlucas/parse`
- Active PR worktree: `/home/lucas/gh/worktrees/parse/mc-317-branch-cleanup-commands`
- Current delivery branch: `docs/mc-317-branch-cleanup-commands`
- Current frontend reality: React SPA is the live frontend; Stage 3 / PR #58 removed `parse.html`, `compare.html`, `review_tool_dev.html`, `js/`, and legacy launchers from the live repo.
- Current branch policy: branch from `origin/main` unless Lucas explicitly says otherwise.

## Audit method
1. Search docs for deleted branch names, removed runtime files, and imperative present-tense instructions.
2. Classify hits into:
   - active docs that still misdirect current work
   - archived docs that need an explicit historical banner
   - already-historical docs that are safe to leave alone
3. Patch only the misleading ones.
4. Re-run `git diff --check`, `npm run test -- --run`, and `./node_modules/.bin/tsc --noEmit`.
5. Run independent review before commit.

## Candidate stale markers
- deleted branches like `feat/parseui-unified-shell`, `docs/parseui-planning`, `feat/parse-react-vite`
- removed files like `parse.html`, `compare.html`, `review_tool_dev.html`, `js/compare/*`, `js/annotate/*`
- old instruction phrases like `Load this file in every session`, `Read this, then build`, `Work on ... branch`, `current` / `next` / `priority` in archived docs

## Completion criteria
- Repo has no docs that accidentally instruct current work through deleted branches or removed frontend surfaces without being labeled historical.
- Any remaining historical docs that stay in place are clearly marked as historical.
- This PR (currently #77) contains the stale-doc cleanup evidence and validation.
