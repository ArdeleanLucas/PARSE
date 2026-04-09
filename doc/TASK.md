# ParseUI — Wiring Task List

> **File:** `src/ParseUI.tsx`
> **Branch target:** `feat/parseui-unified-shell`
> **Last audited:** 2026-05-14
> **Items:** 46 total — 9 data, 7 annotate actions, 14 compare actions, 9 actions-menu items, 3 tags-mode, 4 minor cleanup

All items reference line numbers in the **current** `src/ParseUI.tsx` on `feat/parseui-unified-shell`.
Each item lists the real hook or store it should call instead of the current mock/stub.

---

## 🔴 Section 1 — Data Still Mock / Hardcoded (9 items)

| # | What | Line(s) | Real source |
|---|---|---|---|
| 1 | `CONCEPTS` array used directly (not derived from store) | 863, 865 | `configStore` → `concepts` field (array of `{id, label}`) |
| 2 | `SPEAKERS.length` in speaker-count display span | 1300 | `speakers.length` from `useConfigStore` |
| 3 | `SPEAKERS` in speaker select `<option>` list | 1311 | `speakers` array from `useConfigStore` (partially fixed — verify render) |
| 4 | `MOCK_FORMS` object — IPA, utterances, arabicSim, persianSim, cognate, flagged | 51–57, 1158 | `annotationStore` (IPA / utterances) + `enrichmentStore` (sims) + compute results (cognate / flagged) |
| 5 | `reviewed = 0` in progress bar numerator | 864 | Count of concepts where **every** speaker has at least one annotation interval in `annotationStore` |
| 6 | Reference forms hardcoded — Arabic `رماد` and Persian `خاکستر` | 1129–1138 | `enrichmentStore` → per-concept `arabic_ref` / `persian_ref` fields |
| 7 | Borrowings alert text — hardcoded `Fail01` speaker name | ~1210 | `useComputeJob` result or `enrichmentStore` per-concept borrowing data |
| 8 | Status panel — `"11 speakers / 82 concepts"` hardcoded strings | 1370–1376 | `speakers.length` + `concepts.length` from `useConfigStore` |
| 9 | `"Missing"` badge on concept header in Annotate view | 691 | Check `annotationStore.records[activeSpeaker]` — badge only when no interval exists for this concept |

---

## 🔴 Section 2 — Annotate Mode Actions Not Wired (7 items)

| # | What | Line(s) | Real hook / store call |
|---|---|---|---|
| 10 | IPA field — local `useState` only; not loaded from or saved to store | 712–718 | Load from `annotationStore.records[speaker].tiers.ipa[conceptId]`; onChange → update store |
| 11 | Ortho field — same issue as IPA | 721–728 | Load from `annotationStore.records[speaker].tiers.ortho[conceptId]`; onChange → update store |
| 12 | **Save Annotation** button — no `onClick` handler | 733 | `annotationStore.saveSpeaker(speaker)` + create/update interval for active concept |
| 13 | **Mark Done** button — no `onClick` handler | 736 | `tagStore.tagConcept(tagId, conceptId)` with a `"confirmed"` tag |
| 14 | **SkipBack** (prev segment) button — no `onClick` | 555 | Seek WaveSurfer to previous region start via `regionsRef` |
| 15 | Right-rail **Save annotations** button — no handler | ~1471 | Same as item 12 — `annotationStore.saveSpeaker(speaker)` |
| 16 | Spectrogram toggle — renders CSS placeholder only | 604 | Port `js/shared/spectrogram-worker.js` → `src/workers/spectrogram-worker.ts` + `useSpectrogram` hook; wire to canvas |

---

## 🔴 Section 3 — Compare Mode Actions Not Wired (14 items)

| # | What | Line(s) | Real hook / store call |
|---|---|---|---|
| 17 | **Accept** concept button — no handler | 1116 | `tagStore.tagConcept(tagId, conceptId)` with `"confirmed"` tag |
| 18 | **Flag** concept header button — no handler | 1113 | `tagStore.tagConcept(tagId, conceptId)` with `"problematic"` tag |
| 19 | Reference form audio **play** buttons (`Volume2`) — no handler | 1127, 1135 | `new Audio(referenceAudioUrl).play()` or route through `useWaveSurfer` for reference WAV |
| 20 | Cognate **Accept grouping** button — no handler | 1190 | Write cognate decision to `annotationStore` or `decisions.json` via API |
| 21 | Cognate **Split** button — no handler | 1193 | Same — write split decision |
| 22 | Cognate **Merge** button — no handler | 1196 | Same — write merge decision |
| 23 | Cognate **Cycle** button — no handler | 1199 | Same — cycle through grouping options |
| 24 | Borrowings section — static, not reactive to concept selection | 1207 | Re-fetch / filter `enrichmentStore` data when `activeConcept` changes |
| 25 | **Notes** field — local state, not persisted | 1220 | `annotationStore` notes field or `decisions.json` via POST |
| 26 | Right-rail **Compute: Run** button — only closes menu | 1351 | `useComputeJob` → `POST /api/compute/contact-lexemes` + poll for result |
| 27 | Right-rail **Compute: Refresh** button — no handler | 1354 | Re-fetch enrichments via `enrichmentStore.load()` |
| 28 | Right-rail **Save decisions** button — no handler | 1407 | `useImportExport` → `POST /api/export/decisions` |
| 29 | Right-rail **Load decisions** button — no handler | 1405 | `useImportExport` → file picker → import decisions JSON |
| 30 | Per-speaker row **flag** — `f.flagged` is read-only display, never mutated | 1176 | Write flag to annotation record in `annotationStore`; toggle on click |

---

## 🔴 Section 4 — Actions Menu Items (All Just Close Dropdown) (9 items)

| # | Menu label | Real action |
|---|---|---|
| 31 | **Import Speaker Data** | Trigger `OnboardingFlow` modal or `POST /api/import/upload` |
| 32 | **Run Audio Normalization** | `POST /api/normalize` → poll job → show progress toast |
| 33 | **Run Orthographic STT** | `POST /api/stt` (razhan model) → poll → populate ortho fields |
| 34 | **Run IPA Transcription** | `POST /api/pipeline/run` (`ipa_only`) → poll → populate IPA fields |
| 35 | **Run Full Pipeline** | Sequential orchestration of items 31 → 32 → 33 → 34 with status per step |
| 36 | **Run Cross-Speaker Match** | `POST /api/compute/contact-lexemes` via `useComputeJob` |
| 37 | **Load Decisions** | File picker → parse decisions JSON → hydrate stores |
| 38 | **Save Decisions** | `GET /api/export/lingpy` (LingPy TSV) **or** decisions JSON download |
| 39 | **Reset Project** | Confirmation modal → clear all Zustand stores → reset `localStorage` |

---

## 🔴 Section 5 — Tags Mode Concept Assignment Not Wired (3 items)

| # | What | Line(s) | Real hook / store call |
|---|---|---|---|
| 40 | Concept checkboxes — no `onChange`, no `tagConcept` call | 433 | `tagStore.tagConcept(tagId, conceptId)` / `tagStore.untagConcept(tagId, conceptId)` on toggle |
| 41 | **Apply to selected** button — no handler | 411 | Iterate checked concept IDs → call `tagStore.tagConcept(tagId, conceptId)` for each |
| 42 | **Clear selection** button — no handler | 408 | Reset local checkbox state → all unchecked |

---

## 🟡 Section 6 — Minor Cleanup / Stale Comments (4 items)

| # | What | Line(s) |
|---|---|---|
| 43 | Old TODO comment block about mock waveform in `AnnotateView` JSDoc | 451–468 |
| 44 | `{/* TODO: Replace mock with real hook */}` comment still in render tree | 592–595 |
| 45 | `useEffect` in `AIChat` depends on stale `messages` local array instead of `chatSession.messages` | 127 |
| 46 | `SPEAKERS.length` → `speakers.length` (uppercase constant → store-derived) in speaker count `<span>` | 1300 |

---

## Priority Order (suggested)

```
P0 — Blocking basic use
  #10, #11, #12  (IPA/Ortho load + Save — can't annotate without these)
  #3             (speaker dropdown — verify fix landed)
  #9             (Missing badge — misleads user)

P1 — Data correctness
  #1, #2, #4, #5, #6, #7, #8  (all mock data swaps)
  #46            (trivial SPEAKERS → speakers)

P2 — Compare mode functionality
  #17–#30        (all compare actions)

P3 — Actions menu
  #31–#39        (pipeline orchestration)

P4 — Tags mode
  #40–#42

P5 — Spectrogram (own MC task — MC-297)
  #16

P6 — Cleanup
  #43, #44, #45
```

---

## Related Files

| File | Role |
|---|---|
| `src/ParseUI.tsx` | Primary file — all line refs above point here |
| `src/hooks/useWaveSurfer.ts` | WaveSurfer lifecycle — items 14, 19 |
| `src/hooks/useAnnotationSync.ts` | Annotation persistence — items 10–12, 25 |
| `src/hooks/useChatSession.ts` | Chat — item 45 |
| `src/hooks/useImportExport.ts` | Import/export — items 28, 29, 37, 38 |
| `src/stores/annotationStore.ts` | Annotation records — items 4, 9–13, 20–23, 25, 30 |
| `src/stores/configStore.ts` | Speakers + concepts — items 1–3, 8 |
| `src/stores/enrichmentStore.ts` | Enrichments + reference forms — items 4, 6, 7, 24, 27 |
| `src/stores/tagStore.ts` | Tag assignments — items 13, 17, 18, 40–42 |
| `src/workers/spectrogram-worker.ts` | Spectrogram — item 16 (must be created) |
| `python/server.py` | All API endpoints — items 26, 31–38 |
