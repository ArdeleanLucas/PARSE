# ParseUI current-state execution plan

**Updated:** 2026-04-26
**Applies to:** `origin/main`
**Code branch policy:** new work branches from `origin/main` (per `AGENTS.md`); historical pivot branches like `feat/parseui-unified-shell` are archived
**Docs branch for planning:** branch from `origin/main` (historical docs lane `docs/parseui-planning` was deleted after merge cleanup)

## TLDR

The original wiring TODO (`docs/archive/plans/parseui-wiring-todo.md`) is archived — its early tasks all landed. The remaining ParseUI work is now mostly **compute-mode reconciliation and verification**, with the decisions story now explicit: unified-shell decision import/export uses a canonical `parse-decisions/v1` payload built from `manual_overrides.*`, while annotate-only prior-region state is isolated under a separate legacy localStorage key.

## Live sources of truth

1. `AGENTS.md` — branch policy, deferred-validation policy, and the live client/server contract table
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
- Decisions import/export now share a canonical `parse-decisions/v1` payload (`manual_overrides.cognate_decisions`, `manual_overrides.cognate_sets`, `manual_overrides.speaker_flags`, `manual_overrides.borrowing_flags`) across the Actions menu and right rail
- Manage Tags bulk-selection wiring
- Spectrogram Worker — TS port (`src/workers/spectrogram-worker.ts`), `useSpectrogram` hook, AnnotateView `<canvas>` overlay wired (MC-297, PR #31)

## What is genuinely still open

### 0. xAI/OpenAI onboarding selector ✅ DONE (Stage 2 of docs audit 2026-04-20)

Speaker onboarding now requires an explicit provider choice:

- `src/components/compare/SpeakerImport.tsx` — provider radio group (xAI / OpenAI) pre-populated from `getAuthStatus()`; Start is disabled until one is selected.
- `src/api/client.ts::onboardSpeaker(speakerId, audioFile, csvFile, provider)` — provider included as multipart field.
- `python/server.py::_api_post_onboard_speaker` — validates provider in `{"xai", "openai"}` and that its API key env var is set.
- Chat runtime provider routing in `python/ai/provider.py::OpenAIChatRuntime` (merged via PR #48, #56) — xAI keys route to `https://api.x.ai/v1` with model swap to `grok-3-mini`.

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

All 5 processing actions (normalize, STT, IPA, full pipeline, cross-speaker match) now use `useActionJob` with proper start → poll → progress → complete/error lifecycle. Topbar status indicator shows progress bars, completion flashes, and error messages with dismiss. Buttons disabled while running. Reset Project clears all in-flight jobs. No `console.error`-only failure paths remain. Tests at landing time: 132 passing. For the current enforced suite floor, see `AGENTS.md`.

### 4. ~~Unify the decisions story~~ ✅ DONE (current line)

The canonical persisted decisions artifact for the React unified shell is now explicit:

```json
{
  "format": "parse-decisions/v1",
  "version": 1,
  "manual_overrides": {
    "cognate_decisions": { "<conceptId>": { "decision": "accepted|split|merge", "ts": 0 } },
    "cognate_sets": { "<conceptId>": { "A": ["Speaker01"] } },
    "speaker_flags": { "<conceptId>": { "Speaker01": true } },
    "borrowing_flags": { "<conceptId>": { "Speaker01": { "decision": "borrowed", "sourceLang": "fa" } } }
  }
}
```

Current rules:

- The Actions menu and right-rail Decisions panel both call the same import/export helpers and the same hidden JSON input.
- Canonical compare adjudication persists under `manual_overrides.cognate_decisions`.
- Read compatibility still tolerates legacy top-level `cognate_decisions` in existing enrichments, but canonical export/import rewrites that data into `manual_overrides.cognate_decisions`.
- Decisions import replaces only the decisions-backed `manual_overrides` categories listed above while preserving non-decision enrichments (for example `reference_forms`, similarity scores, or other enrichment payloads).
- Annotate-only prior-region state is intentionally **not** the canonical decisions artifact; `RegionManager` now stores it only in localStorage key `parse-annotate-region-decisions-v1` so it cannot be mistaken for compare-mode decisions.

Implication for future work:
- new comparative decision affordances should extend the canonical `parse-decisions/v1` payload via `manual_overrides.*`
- annotate-local convenience state should stay clearly segregated from enrichments-backed compare decisions

### 5. Verify compute-mode semantics against the server

`useComputeJob` is already mounted in ParseUI, so the remaining work is to verify:

- that each selected `computeMode` maps to a real supported server compute type
- whether additional payload is needed (speaker subset / concept scope)
- whether refresh semantics should reload enrichments only or also re-run compute

### 6. Deferred validation backlog after contract reconciliation

Once the Actions / compute / decisions contract is coherent, keep the downstream testing list current — but do **not** let it block other implementation stages:

- Use `docs/plans/deferred-validation-backlog.md` as the single source.
- C5 (LingPy TSV export verification) and C6 (full Annotate/Compare browser regression) live on that backlog — run them in the order of real testing once onboarding/import and end-to-end flows are usable.
- C7 / legacy-cleanup is no longer mechanically blocked on C5/C6; it still requires a scoped PR and Lucas review/merge (see AGENTS.md § Deferred Validation Backlog).

### 7. Remove vanilla JS entrypoints ✅ DONE (PR #58)

Stage 3 landed in PR #58: `js/`, `parse.html`, `compare.html`, `review_tool_dev.html`, `start_parse.sh`, `Start Review Tool.bat`, and the `forceSpaCompareRoute` Vite plugin are gone. `src/ParseUI.tsx` + the React SPA is now the sole frontend.

## Execution order

1. ~~**Fix the two known contract gaps** (`/api/normalize`, `/api/onboard/speaker`)~~ ✅ Done (PR #33)
2. **Do not** reopen completed annotate/compare wiring tasks from the historical TODO.
3. Audit `src/ParseUI.tsx`, `src/api/client.ts`, and `python/server.py` together.
4. Wire remaining Actions menu handlers to the typed client surface.
5. Verify compute-mode semantics and payload expectations against the server.
6. Re-run targeted tests and full test suite.
7. Keep the deferred validation backlog current and return to it when real-data testing is ready.

## Explicit non-goals for the next slice

- Do not branch from historical/deleted pivot lanes such as `feat/annotate-ui-redesign`; start from `origin/main`
- Do not add raw `fetch()` calls to `ParseUI.tsx` just because the historical TODO says so
- Do not treat C5/C6 as prerequisites for other implementation stages; keep them on the deferred validation backlog until real onboarding/import testing is live

## Suggested next implementation brief

If starting the next code slice now, the brief should be:

> Contract gaps are fixed, and the canonical decisions artifact is now `parse-decisions/v1` over `manual_overrides.*`. Audit remaining ParseUI Actions menu handlers against the live typed client/server contract, verify compute-mode semantics and payload expectations, keep the deferred validation backlog current, and continue broader React-shell cleanup as Lucas requests.
