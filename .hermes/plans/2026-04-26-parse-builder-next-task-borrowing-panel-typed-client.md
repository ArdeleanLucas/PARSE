# parse-builder next task — BorrowingPanel typed-client cleanup

## Goal

Replace the remaining raw config fetch in `src/components/compare/BorrowingPanel.tsx` with the existing typed CLEF client surface so Compare mode stays contract-consistent and obeys the no-bare-`fetch()` frontend rule on current `origin/main`.

## Why this is the right next task now

- Current rebuild `origin/main` is `5cf12ca` (`feat(compare): make compute payload semantics explicit (#24)`).
- Builder’s previous compute-mode task is now already merged on main via PR #24.
- parse-back-end is currently queued on PR #23 (`https://github.com/TarahAssistant/PARSE-rebuild/pull/23`) for backend config/import HTTP extraction, so the next Builder slice should stay frontend-only and avoid overlapping `python/server.py` work.
- On current main, `BorrowingPanel.tsx` still contains a direct raw fetch:
  - `fetch("/config/sil_contact_languages.json")`
- That violates the active frontend rule in `AGENTS.md`:
  - **No bare `fetch()` calls. Every API call goes through `src/api/client.ts`.**
- The typed client surface already exposes CLEF helpers the panel can use instead:
  - `getClefConfig()`
  - `getClefCatalog()` if truly needed

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch: `origin/main`
- Current head: `5cf12ca`
- Open PRs right now:
  - PR #23 — parse-back-end handoff only: `https://github.com/TarahAssistant/PARSE-rebuild/pull/23`

### Relevant current-main files
- `src/components/compare/BorrowingPanel.tsx`
  - still bootstraps contact languages with raw `fetch("/config/sil_contact_languages.json")`
- `src/components/compare/BorrowingPanel.test.tsx`
  - currently mocks `globalThis.fetch`
- `src/api/client.ts`
  - already exposes typed CLEF routes including `getClefConfig()`
- `docs/plans/parseui-current-state-plan.md`
  - compute-mode semantics are now done on the current line
  - suggested next work is broader shell/frontend cleanup, not another compute-semantics rewrite

## Specific task

Make `BorrowingPanel` use the typed CLEF API client instead of raw config-file fetches.

### Required implementation direction
1. Replace the mount-time raw fetch in `BorrowingPanel.tsx` with the existing typed client helper.
2. Preserve current user-facing behavior:
   - contact-language options still load on panel mount
   - allowed-language filtering still respects the comparative context already on disk
   - source-language selection UX and save behavior stay unchanged
3. Update tests so they mock the typed client helper(s) instead of `globalThis.fetch`.
4. Keep the slice narrow; do not widen into backend or unrelated Compare churn.

## In scope
- `src/components/compare/BorrowingPanel.tsx`
- `src/components/compare/BorrowingPanel.test.tsx`
- `src/api/client.ts` only if a tiny helper adjustment is genuinely required
- any directly adjacent types needed for the typed client call

## Out of scope
- `python/server.py`
- parse-back-end PR #23’s config/import extraction lane
- compute-mode semantics (already merged in PR #24)
- large compare-table refactors
- CLEF algorithm changes

## Validation requirements
Run and report at least:
- `npm run test -- --run src/components/compare/BorrowingPanel.test.tsx`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

Also do a focused Compare-mode smoke if possible:
- open a concept with borrowing adjudication data
- verify contact-language choices still appear
- verify changing decision/source language still behaves correctly

## Academic / UX considerations
- Borrowing adjudication depends on trustworthy language labels; the panel should read them from the same typed CLEF contract used elsewhere, not a side-path config fetch.
- Do not silently change which languages appear without documenting the rule in the PR body.
- Preserve adjudication reproducibility: this is a contract cleanup, not an analysis-policy change.

## Reporting requirements
Open a fresh implementation PR from current `origin/main`.
In the PR body, include:
- the exact raw fetch removed
- which typed client helper replaced it
- confirmation that no backend contract changed
- exact tests run

## What comes after this task
If this lands cleanly, the next Builder/frontend cleanup can continue the same theme: remove remaining contract-hygiene violations and keep Compare/Annotate UI surfaces on the typed client/store paths without reopening already-solved compute semantics.
