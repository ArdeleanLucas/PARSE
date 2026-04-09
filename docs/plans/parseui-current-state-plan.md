# ParseUI current-state execution plan

**Updated:** 2026-04-10
**Applies to:** `origin/main`
**Code branch for implementation:** `feat/parseui-unified-shell`
**Docs branch for planning:** `docs/parseui-planning`

## TLDR

Do not execute `docs/plans/parseui-wiring-todo.md` literally anymore. Most of its early wiring tasks have already landed. The remaining ParseUI work is now mostly **contract reconciliation and verification** around Actions menu flows, compute/decisions persistence, and C5/C6 evidence.

## Live sources of truth

1. `AGENTS.md` — branch policy and release gates
2. `docs/plans/parsebuilder-todo.md` — high-level current status / blocked gate
3. `src/ParseUI.tsx` — implemented UI state and current affordances
4. `src/ParseUI.test.tsx` — regression coverage for landed ParseUI slices
5. `src/api/client.ts` + `python/server.py` — authoritative client/server integration surface

## Already landed on the current line

These are no longer open execution tasks:

- Annotate prefill from stored annotations
- Save Annotation wiring
- Mark Done wiring
- Annotated/Missing badge logic
- Reviewed count from tags
- Compare speaker forms from annotation data
- Reference forms from enrichments
- Compare Accept / Flag concept actions
- Compare notes persistence
- Actions > Import Speaker Data modal
- Compute panel basic Run / Refresh wiring
- Decisions basic load/save wiring in the unified shell
- Manage Tags bulk-selection wiring

## What is genuinely still open

### 1. Reconcile the Actions menu with the **live** contract

The next implementation work is not “add raw fetch calls from the old TODO.” It is:

- verify which actions are fully backed by `python/server.py` today
- normalize ParseUI action handlers to the typed client surface where possible
- avoid creating a second ad hoc API path in `ParseUI.tsx`

#### Specific audit points
- `SpeakerImport` currently uses its own upload flow (`/api/onboard/speaker`) instead of a typed client helper; decide whether to keep that component-owned path or formalize it in `src/api/client.ts`
- `src/api/client.ts` currently exposes helpers such as `startSTT()`, `startNormalize()`, `startCompute()`, and `getLingPyExport()`
- before adding more UI wiring, confirm each corresponding server route exists in `python/server.py`
- if a client helper exists without a server route, fix that mismatch first instead of building more UI on top of it

### 2. Finish Actions menu job behavior, not just button clicks

The remaining Actions work is about **progress, polling, and explicit success/error handling**:

- Audio normalization
- Orthographic STT
- IPA transcription / pipeline step
- Full pipeline orchestration
- Cross-speaker match feedback
- Reset Project confirmation + state reset review

#### Desired outcome
- one action state model for in-flight jobs
- explicit progress/error UI
- no silent background trigger with console-only failure reporting
- action handlers grounded in the current contract, not the historical TODO doc

### 3. Unify the decisions story

Decisions are partially wired, but the plan now needs to answer:

- what is the canonical persisted decisions format?
- are decisions stored in enrichments, in `parse-decisions` localStorage, or both?
- do Actions-menu decision load/save and right-rail decision load/save operate on the same structure?

#### Required follow-up
- inspect current decision writes in `src/ParseUI.tsx`
- inspect any existing `parse-decisions` localStorage readers/writers elsewhere in the app
- pick one canonical format and document it before more UI changes

### 4. Verify compute-mode semantics against the server

`useComputeJob` is already mounted in ParseUI, so the remaining work is to verify:

- that each selected `computeMode` maps to a real supported server compute type
- whether additional payload is needed (speaker subset / concept scope)
- whether refresh semantics should reload enrichments only or also re-run compute

### 5. C5 / C6 evidence after contract reconciliation

Once the Actions / compute / decisions contract is coherent, the next gate is evidence:

- use `docs/plans/phase4-c5-c6-signoff-checklist.md`
- verify LingPy TSV export in the browser (C5)
- verify full Annotate/Compare regression in the browser (C6)

## Execution order

1. **Do not** reopen completed annotate/compare wiring tasks from the historical TODO.
2. Audit `src/ParseUI.tsx`, `src/api/client.ts`, and `python/server.py` together.
3. Resolve client/server mismatches for Actions flows first.
4. Unify decision persistence/load-save behavior.
5. Re-run targeted tests and full test suite.
6. Collect C5/C6 evidence.

## Explicit non-goals for the next slice

- Do not branch from `feat/annotate-ui-redesign`
- Do not add raw `fetch()` calls to `ParseUI.tsx` just because the historical TODO says so
- Do not start C7 cleanup / legacy deletion before Lucas clears C5 and C6

## Suggested next implementation brief

If starting the next code slice now, the brief should be:

> Audit and reconcile ParseUI Actions menu handlers against the live typed client/server contract, then unify decisions persistence/load-save behavior, and only after that proceed to C5/C6 browser evidence.
