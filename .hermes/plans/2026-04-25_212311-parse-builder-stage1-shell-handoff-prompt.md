# PARSE rebuild Stage 1 handoff prompt for `parse-builder`

Paste the block below into a fresh Hermes session running under profile `parse-builder`.

---

You are `parse-builder`, working in parallel with ParseGPT on the PARSE rebuild lane.

## Load and follow these skills first
- `parse-react-shell-refactor-execution`
- `test-driven-development`
- `parse-pr-workflow`
- `daily-log-after-each-job`
- `dogfood`

## Canonical repo + policy for this task
- Active repo for this task: `/home/lucas/gh/tarahassistant/PARSE-rebuild`
- Live/oracle PARSE remains: `/home/lucas/gh/ardeleanlucas/parse`
- Work in the rebuild repo only for this task.
- Use Hermes tools directly (`read_file`, `search_files`, `patch`, `write_file`, `terminal`). Do not route through another coding agent by default.
- Do **not** leave rebuild-repo work as local-only edits; commit, push, and open a PR.
- Rebuild-repo note: `gh pr create --reviewer TrueNorth49` may fail with reviewer-not-found here. Do not block on that; open the PR without reviewer if needed.

## Grounded current-state facts (verified live on 2026-04-25)
- The rebuild repo currently has these relevant remote branches:
  - `origin/docs/rebuild-repo-context`
  - `origin/feat/parseui-shell-stage0-rebuild`
  - `origin/refactor/backend-http-slice`
- Open rebuild PRs:
  - PR #3 — `test(parseui): cover offset anchor shell paths`
    - head: `feat/parseui-shell-stage0-rebuild`
    - base: `docs/rebuild-repo-context`
    - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/3`
  - PR #4 — `refactor: extract backend HTTP helper slice`
    - head: `refactor/backend-http-slice`
    - base: `docs/rebuild-repo-context`
    - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/4`
- PR #3 contains the current Stage-0 shell regression work and changes only:
  - `src/ParseUI.test.tsx`
- PR #3 commits:
  - `2b04531 test(parseui): add stage0 shell regression coverage`
  - `c08263c test(parseui): cover offset anchor shell paths`
- The current ParseUI execution plan already exists in the rebuild repo:
  - `.hermes/plans/2026-04-25_183200-parseui-shell-refactor-plan.md`
- That plan's explicit next action is:
  1. start from the Stage-0 regression baseline,
  2. implement **Stage 1 only** (`ConceptSidebar` + `RightPanel`),
  3. stop and rerun full gates before any offset extraction.

## Architectural stance you must preserve
- This is a **behavior-preserving shell extraction**, not a tree-reset rewrite.
- Treat `src/components/parse/**` as a unified-shell layer only.
- Reuse existing `annotate`, `compare`, `compute`, and `shared` components; do not re-home them.
- `ParseUI.tsx` should shrink toward orchestration/controller code, not grow new abstractions for their own sake.
- TDD is mandatory: write failing tests first, verify red, then implement the minimal extraction.

## Your write lane for this task
You own the Stage-1 shell slice only.

### Write owner
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/components/parse/ConceptSidebar.tsx`
- `src/components/parse/RightPanel.tsx`
- co-located tests for the new Stage-1 files
- a minimal `src/components/parse/` barrel/index only if it clearly reduces import churn

### Read-only unless Lucas explicitly broadens scope
- `python/**`
- `src/api/client.ts`
- `src/api/types.ts`
- `src/stores/*`
- `src/components/annotate/*`
- `src/components/compare/*`
- `src/components/compute/*`
- `src/components/shared/*`
- `.hermes/plans/2026-04-25_181900-parsegpt-next-task-backend-http-slice.md`

If you think a read-only surface must change, stop and document the dependency instead of silently editing it.

## Anti-collision rule with ParseGPT
- ParseGPT currently owns the backend modularization lane in PR #4.
- Do not edit `python/server.py`, `python/app/http/**`, or the PR #4 branch.
- Keep this task entirely inside the ParseUI shell lane.

## Your mission right now
Execute **Stage 1 only** of the shell refactor on top of the Stage-0 test branch.

### Required branch setup
1. Verify repo state yourself:
   - `git status --short --branch`
   - `git rev-parse --abbrev-ref HEAD`
   - `git log --oneline -3`
2. Start from the Stage-0 shell-test branch, not from the backend branch:
   - `git fetch origin --prune`
   - `git switch -c feat/parseui-shell-stage1-islands origin/feat/parseui-shell-stage0-rebuild`
3. Re-run the baseline in that branch:
   - `npm run test -- --run`
   - `./node_modules/.bin/tsc --noEmit`
4. Read these files before editing:
   - `AGENTS.md`
   - `src/ParseUI.tsx`
   - `src/ParseUI.test.tsx`
   - `.hermes/plans/2026-04-25_183200-parseui-shell-refactor-plan.md`

### Required implementation scope
Implement only the small stable UI-island slice from the plan:
1. `ConceptSidebar.tsx`
2. `RightPanel.tsx`
3. rewire `src/ParseUI.tsx` to use them
4. stop after Stage 1 and rerun full gates

### TDD requirements
Before moving production code, add failing tests that protect the Stage-1 behavior.

At minimum, cover:
- `ConceptSidebar` renders the provided concept list and active selection state
- `ConceptSidebar` still triggers concept changes through explicit callbacks
- `RightPanel` preserves speaker-selection behavior in annotate mode
- `RightPanel` preserves speaker-selection behavior in compare mode
- existing shell-level `ParseUI` integration tests still prove mode switching and shell orchestration are intact

Important constraint:
- keep `ConceptSidebar` and `RightPanel` prop-driven in Stage 1
- do **not** pull search/sort/filter state into the sidebar yet
- do **not** start `useOffsetState` or modal extraction in this task
- do **not** rewrite compare or annotate child components in this task

## Validation requirements
### Required after the red/green cycle for each Stage-1 slice
- run the targeted tests for the new/updated files
- confirm the new tests fail first, then pass

### Required before you report completion
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

### Browser review
If the stack is runnable without disturbing another active PARSE session, do a focused browser smoke on:
- mode switching
- concept selection from the sidebar
- right-panel speaker selection in annotate
- right-panel speaker selection in compare
If browser smoke is not practical in the current environment, say exactly why instead of hand-waving.

## PR packaging rules
- Commit the Stage-1 slice on its own branch.
- Open a **stacked PR** against `feat/parseui-shell-stage0-rebuild`, not against the backend branch.
- In the PR body, explicitly say this PR depends on rebuild PR #3 and is intentionally isolated from rebuild PR #4.
- If reviewer assignment fails in this repo, proceed without reviewer and note that in the report.

## Behaviors that must not regress
- mode switching (`annotate`, `compare`, `tags`)
- arrow-key concept navigation outside inputs
- right-panel speaker selection in annotate and compare
- comments import modal path
- batch report visibility and rerun flow
- LingPy export trigger path
- AI chat / provider badge path

## Reporting format
When you reply, use this structure:
1. verified branch/base facts
2. tests added first and how they failed
3. files created/modified
4. validation results
5. PR number + URL
6. unresolved risks or follow-up suggestions

## Stop condition
Stop after Stage 1 is implemented, validated, pushed, and packaged as a PR. Do **not** start the offset workflow extraction in the same task.
