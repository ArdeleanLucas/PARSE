# PARSE-rebuild parse-back-end — next task: worktree hygiene cleanup

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Base:** `origin/main` at `c5aee8b` (`fix(compare): bundle frontend contract hardening (#34)`)
**Task owner:** `parse-back-end`
**Priority:** high operational hygiene / unblock coordination clarity
**Scope:** local repo/worktree cleanup only — **no runtime code changes** unless strictly needed for cleanup tooling

## Why this is the right next task now

PARSE-rebuild is functionally healthy on current `origin/main`, but the local worktree inventory has become a coordination hazard:

- total worktrees: **39**
- managed worktrees under `/home/lucas/gh/worktrees/PARSE-rebuild/`: **27**
- `/tmp` review/audit worktrees: **11**
- detached worktrees: **14**

The strategy is working for isolation, but cleanup discipline is lagging. This is now expensive enough to merit a dedicated maintenance pass.

## Current grounded context

### Open PRs that must be protected

1. **PR #41** — `fix(annotate): restore oracle region decision storage`
   - URL: https://github.com/TarahAssistant/PARSE-rebuild/pull/41
   - branch: `feat/annotate-parity-region-manager`
2. **PR #36** — `docs: queue Builder annotate parity bundle`
   - URL: https://github.com/TarahAssistant/PARSE-rebuild/pull/36
   - branch: `docs/parse-builder-next-task-ui-parity-bundle`

### Root checkout warning

The root checkout is **not authoritative** and should not be used as cleanup truth:

- path: `/home/lucas/gh/tarahassistant/PARSE-rebuild`
- branch: `feat/parseui-shell-stage0-rebuild`
- upstream: gone
- local untracked state present

Treat `origin/main` as truth and preserve the root checkout unless you have explicit evidence it is safe to reset later.

### Important local WIP that must be protected for now

`/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-auto` is dirty and currently contains unresolved local state:

- `docs/plans/parseui-current-state-plan.md`
- `src/ParseUI.test.tsx`
- `src/ParseUI.tsx` (conflicted)
- `src/components/annotate/RegionManager.test.tsx`
- `src/components/annotate/RegionManager.tsx`

Do **not** delete or reset `parse-builder-auto` in this task. Escalate it as protected ambiguous state.

## Task

### Phase 1 — Ground and classify

Re-run live grounding before deleting anything:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --prune
gh pr list --repo TarahAssistant/PARSE-rebuild --state open --limit 30 \
  --json number,title,headRefName,baseRefName,mergeStateStatus,url
git worktree list --porcelain
git branch -vv --all | sed -n '1,200p'
```

Classify every worktree as:
1. protected open-PR lane
2. protected ambiguous local WIP
3. stale `/tmp` review/audit tree
4. stale managed merged-lane tree

### Phase 2 — Prune the safest stale review trees first

Immediate likely-safe candidates from the grounded audit:

- `/tmp/parse-rebuild-origin-main-next-backend`
- `/tmp/parse-rebuild-pr14-review`
- `/tmp/parse-rebuild-pr16-review`
- `/tmp/parse-rebuild-pr17-review`
- `/tmp/parse-rebuild-pr3-review`
- `/tmp/parse-rebuild-pr39-review`
- `/tmp/parse-rebuild-pr5-review`
- `/tmp/parse_pr40_review`
- `/tmp/parse_rebuild_main_review`

Conditional `/tmp` candidates that need one quick inspection first:

- `/tmp/parse-rebuild-pr38`
  - currently shows stray `node_modules`
  - remove symlink/junk first, then remove the worktree
- `/tmp/parse-rebuild-audit-main`
  - currently shows stray `-version`
  - inspect whether it is just disposable junk, then remove if safe

### Phase 3 — Evaluate stale managed worktrees after `/tmp` cleanup

After the obvious `/tmp` review trees are gone, inspect clean managed worktrees with no open PR and no dirtiness, especially historical branches/worktrees tied to already merged or superseded slices.

Likely candidates to review for deletion **if still clean and unclaimed**:

- `borrowing-panel-typed-client-impl`
- `cognate-controls-save-hardening-impl`
- `compute-mode-semantics-impl`
- `configstore-update-impl`
- `job-observability-http-slice`
- `parse-back-end-next-task-backend-health-v2`
- `parse-back-end-prompt`
- `parse-builder-hook-order-crash`
- `parse-builder-stage2-prompt`
- `parse-gpt-backend-next-task`
- `parse-gpt-backend-next-task-clef-http-bundle`
- `parse-gpt-backend-next-task-config-import-http`
- `parse-gpt-backend-next-task-tags-export-http`
- `parse-gpt-builder-next-task`
- `parse-gpt-builder-next-task-borrowing-panel-typed-client`
- `parse-gpt-builder-next-task-cognate-controls-persistence`
- `parse-gpt-builder-next-task-cognate-controls-save-hardening`
- `parse-gpt-builder-next-task-compute-mode-semantics`
- `parse-gpt-builder-next-task-configstore-update`
- `parse-gpt-builder-next-task-transcription-lanes-crash-v2`
- `parse-gpt-three-lane-health`
- `parsegpt-next-external-api-prompt`
- `refactor-external-api-http-slice`

Do **not** delete the open Builder docs lane for PR #36.

## Hard constraints

- **Do not touch open PR heads** (`#41`, `#36`)
- **Do not touch `parse-builder-auto`** in this pass
- **Do not use the stale root checkout as truth**
- **Do not rewrite repo runtime files** just to accomplish cleanup
- **Do not delete a worktree only because it is detached** — verify it is stale first

## Validation / evidence required

Before/after report must include:

- worktree count before cleanup
- worktree count after cleanup
- detached count before/after
- `/tmp` count before/after
- exact worktrees removed
- exact local branches removed (if any)
- protected survivors explicitly kept and why

Minimum command evidence:

```bash
git worktree list --porcelain
gh pr list --repo TarahAssistant/PARSE-rebuild --state open --limit 30 \
  --json number,title,headRefName,baseRefName,mergeStateStatus,url
```

## Deliverable

A concise report back to Lucas / parse-gpt with:
- what was removed
- what was intentionally protected
- any ambiguous worktrees that still need human review
- the final inventory counts

## Non-goals

- no frontend parity coding
- no backend HTTP extraction work
- no merge/close decisions on live GitHub PRs
- no reset of the root checkout unless separately requested
