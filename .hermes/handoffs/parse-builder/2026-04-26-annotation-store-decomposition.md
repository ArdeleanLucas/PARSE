---
agent: parse-builder
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - TranscriptionRunModal sequence wraps (PR #114 essentially done at 298 LoC)
related_skills:
  - parse-react-shell-refactor-planning
  - parse-react-shell-refactor-execution
  - parse-vitest-hoisted-store-mocks
  - test-driven-development
---

# parse-builder follow-on — annotationStore.ts decomposition

**Why this exists:** With BatchReportModal (#112) and TranscriptionRunModal (#114) both essentially done at sub-300 LoC after a single big extraction each, the next-largest frontend monolith is `src/stores/annotationStore.ts` at 753 LoC. **Different pattern from React components** — this is a Zustand store, so decomposition is helper-extraction + (optionally) slice-extraction, not component-extraction.

## Working environment

Same rule. AGENTS.md PR #74 + screenshot link convention (PR #89) + screenshot SHA256 verification (your standard from PR #97 onward) + **NEW**: refetch before reporting PR status (per the skill PR I just opened).

**Critical for store work**: use the `parse-vitest-hoisted-store-mocks` skill. Zustand store mocks are the #1 cause of false-green Vitest runs in this repo. Hoist failures will silently mis-mock the store and tests will pass for the wrong reasons.

## Goal

Reduce `src/stores/annotationStore.ts` from 753 LoC to ≤500 LoC by lifting pure helpers and history logic into sibling files. Behavior must stay byte-equivalent.

## Probable cuts (verify against actual file before starting)

Per the file's symbol map:

- **Pure helpers** (~lines 1-160, ~150 LoC) → `src/stores/annotationStore/helpers.ts`:
  - `nowIsoUtc`, `blankRecord`, `ensureCanonicalTiers`, `deepClone`
  - `CANONICAL_TIER_ORDER` constant
  - `TIER_LABEL` + `tierLabel` (~10 LoC)
  - Optional: `scheduleAutosave` + the `autosaveTimers` map if it's coherent in isolation

- **History sub-module** (~lines 77-145, ~70 LoC) → `src/stores/annotationStore/history.ts`:
  - `HistoryEntry`, `SpeakerHistory` types
  - `HISTORY_CAP` constant
  - `emptyHistory`, `pushHistoryDelta`

- **Main store stays** in `src/stores/annotationStore.ts` (just imports from sibling files):
  - `AnnotationStore` interface (lines 163-254)
  - `useAnnotationStore = create<AnnotationStore>()((set, get) => ({...}))` (lines 255+)

Final tree:

```
src/stores/annotationStore.ts        (orchestrator + create() call, ≤450 LoC)
src/stores/annotationStore/
  helpers.ts                          (pure functions + canonical tier constants)
  helpers.test.ts                     (paired test)
  history.ts                          (history sub-module)
  history.test.ts                     (paired test)
```

OR keep them as flat siblings (`src/stores/annotationStoreHelpers.ts`, `annotationStoreHistory.ts`) — your call based on existing repo conventions. Check what other stores have done.

## Sequence

**1-2 PRs total.** This is a smaller monolith than the modals, and the cuts are cleaner because most of the file is pure functions with no React/store coupling.

Suggested:

- **PR A** — Lift pure helpers to `helpers.ts` (~150 LoC reduction)
- **PR B** — Lift history sub-module to `history.ts` (~70 LoC reduction; can fold into PR A if time-tight)

After both: annotationStore.ts ~530 LoC. If still above 500, evaluate orchestrator floor (same escape-hatch pattern as TranscriptionLanes #107).

## Procedure (per PR)

Same as your prior frontend extractions:

1. **Refetch first** — `git fetch origin && git checkout -B feat/<slug> origin/main`. Main has been moving fast.
2. Re-derive line numbers via grep — do NOT trust this prompt's line numbers.
3. Cut + lift verbatim. Add `export` for previously-private symbols the test file needs.
4. Update `annotationStore.ts` imports.
5. Add paired test file with one `it()` per scenario; **hoisted-mock pattern from `parse-vitest-hoisted-store-mocks` skill required** (this is a store; mocking gotchas apply).
6. Run gates: `npm run typecheck`, `npm run test -- --run`, `npm run build`. **All `useAnnotationStore` consumer tests must stay green** (high blast-radius file; many components consume it).
7. Browser regression: open Annotate, edit + save an interval, verify autosave fires, hit undo/redo, **markdown-link screenshot in PR body, SHA256 verified distinct**.

## Scope guardrails

- Do not change `AnnotationStore` interface shape — public API stable
- Do not change `useAnnotationStore` exports — callers shouldn't need import-path updates
- Do not change autosave behavior or history semantics — pure structural lift
- Do not touch `src/components/annotate/` files even if they consume the store
- Do not refactor any existing test that mocks `useAnnotationStore`

## Acceptance (cumulative)

- `wc -l src/stores/annotationStore.ts` ≤ 500 (or documented floor with rationale per PR #82 escape-hatch pattern)
- 1-2 new helper files under `src/stores/annotationStore/` (or sibling), each with paired tests
- All existing tests pass without modification
- Browser regression markdown-link screenshot in each PR
- Coordinator (parse-gpt) reviews and merges

## After this lands

Next monolith is `src/api/client.ts` (1048 LoC, untyped client surface). That one's a typed-client extraction — different pattern again. Coordinator will queue separately.

## Out-of-band notes

- This is the first store-level decomposition in the rebuild. Take it slower than a component extraction; store mocking gotchas have bitten this repo before.
- If you discover the store has dead code (unused selectors, unused state fields), flag in PR body but do not delete in this task — separate cleanup PR after extraction lands.
