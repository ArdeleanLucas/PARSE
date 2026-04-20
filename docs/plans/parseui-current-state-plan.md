# ParseUI current-state execution plan

**Updated:** 2026-06-14
**Applies to:** `origin/main`
**Code branch policy:** new work branches from `origin/main` (per `AGENTS.md`); historical pivot branches like `feat/parseui-unified-shell` are archived
**Docs branch for planning:** branch from `origin/main` (historical docs lane `docs/parseui-planning` was deleted after merge cleanup)

## TLDR

The original wiring TODO (`docs/archive/plans/parseui-wiring-todo.md`) is archived — its early tasks all landed. The remaining ParseUI work is now mostly **contract reconciliation and verification** around Actions menu flows and compute/decisions persistence, with export/regression checks now tracked on a deferred validation backlog rather than a hard gate.

## Live sources of truth

1. `AGENTS.md` — branch policy, deferred-validation policy, and known contract gaps
2. `docs/plans/parsebuilder-todo.md` — high-level current status / deferred validation backlog
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
- Spectrogram Worker — TS port (`src/workers/spectrogram-worker.ts`), `useSpectrogram` hook, AnnotateView `<canvas>` overlay wired (MC-297, PR #31)

## What is genuinely still open

### 1. ~~Fix known client/server contract mismatches~~ ✅ DONE

All contract gaps have been resolved (PR #33):

| Client surface | Endpoint | Server status |
|---|---|---|
| `onboardSpeaker()` in `client.ts` | `POST /api/onboard/speaker` | ✅ Implemented — multipart upload, background job |
| `pollOnboardSpeaker()` in `client.ts` | `POST /api/onboard/speaker/status` | ✅ Implemented — job poll |
| `startNormalize()` in `client.ts` | `POST /api/normalize` | ✅ Implemented — ffmpeg loudnorm |
| `pollNormalize()` in `client.ts` | `POST /api/normalize/status` | ✅ Implemented — job poll |
| `startSTT()` in `client.ts` | `POST /api/stt` | ✅ Existing |
| `startCompute()` in `client.ts` | `POST /api/compute/{type}` | ✅ Existing |
| `getLingPyExport()` in `client.ts` | `GET /api/export/lingpy` | ✅ Existing |

`SpeakerImport.tsx` now uses the typed client (`onboardSpeaker` + `pollOnboardSpeaker`) instead of raw `fetch()`.

### 2. Reconcile the Actions menu with the **live** contract

The next implementation work is not "add raw fetch calls from the old TODO." It is:

- all actions are now backed by `python/server.py` (see table above — zero gaps)
- normalize remaining ParseUI action handlers to the typed client surface where possible
- avoid creating a second ad hoc API path in `ParseUI.tsx`

### 3. ~~Finish Actions menu job behavior, not just button clicks~~ ✅ DONE (PR #38)

All 5 processing actions (normalize, STT, IPA, full pipeline, cross-speaker match) now use `useActionJob` with proper start → poll → progress → complete/error lifecycle. Topbar status indicator shows progress bars, completion flashes, and error messages with dismiss. Buttons disabled while running. Reset Project clears all in-flight jobs. No `console.error`-only failure paths remain. Tests: 132 passing.

### 4. Unify the decisions story

Decisions are partially wired, but the plan now needs to answer:

- what is the canonical persisted decisions format?
- are decisions stored in enrichments, in `parse-decisions` localStorage, or both?
- do Actions-menu decision load/save and right-rail decision load/save operate on the same structure?

#### Required follow-up
- inspect current decision writes in `src/ParseUI.tsx`
- inspect any existing `parse-decisions` localStorage readers/writers elsewhere in the app
- pick one canonical format and document it before more UI changes

### 5. Verify compute-mode semantics against the server

`useComputeJob` is already mounted in ParseUI, so the remaining work is to verify:

- that each selected `computeMode` maps to a real supported server compute type
- whether additional payload is needed (speaker subset / concept scope)
- whether refresh semantics should reload enrichments only or also re-run compute

### 6. Deferred validation backlog after contract reconciliation

Once the Actions / compute / decisions contract is coherent, keep the downstream testing list current — but do **not** let it block other implementation stages:

- use `docs/plans/deferred-validation-backlog.md`
- return to LingPy TSV export checks when onboarding/import and real-data testing make them meaningful
- return to full Annotate/Compare browser regression when end-to-end testing is actually underway

## Execution order

1. ~~**Fix the two known contract gaps** (`/api/normalize`, `/api/onboard/speaker`)~~ ✅ Done (PR #33)
2. **Do not** reopen completed annotate/compare wiring tasks from the historical TODO.
3. Audit `src/ParseUI.tsx`, `src/api/client.ts`, and `python/server.py` together.
4. Wire remaining Actions menu handlers to the typed client surface.
5. Unify decision persistence/load-save behavior.
6. Re-run targeted tests and full test suite.
7. Keep the deferred validation backlog current and return to it when real-data testing is ready.

## Explicit non-goals for the next slice

- Do not branch from historical/deleted pivot lanes such as `feat/annotate-ui-redesign`; start from `origin/main`
- Do not add raw `fetch()` calls to `ParseUI.tsx` just because the historical TODO says so
- Do not treat C5/C6 as prerequisites for other implementation stages; keep them on the deferred validation backlog until real onboarding/import testing is live

## Suggested next implementation brief

If starting the next code slice now, the brief should be:

> Contract gaps are fixed. Audit remaining ParseUI Actions menu handlers against the live typed client/server contract, wire progress/error UI for in-flight jobs, unify decisions persistence/load-save behavior, keep the deferred validation backlog current, and continue broader JS-removal/unification work as Lucas requests.
