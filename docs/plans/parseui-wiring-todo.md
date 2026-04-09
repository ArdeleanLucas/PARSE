# ParseUI Wiring TODO — historical archive

> **Status:** Historical plan only — do **not** use this file as the live execution guide.
> **Original branch context:** `feat/annotate-ui-redesign`
> **Why archived:** this file predates the current `origin/main` state, the strict branch policy in `AGENTS.md`, and multiple merged ParseUI wiring slices.
> **Already landed since this plan was written:** annotate prefill/save/mark/badge, compare real speaker forms/reference/reviewed count, import modal, notes persistence, compute run/refresh basic wiring, and decisions load/save basics.
> **Current source of truth:** `docs/plans/parseui-current-state-plan.md`
> **Rule:** For new work, start from `origin/main` and use the live client/server contract (`src/api/client.ts`, `python/server.py`) rather than the raw endpoint suggestions below.

---

## Priority 1 — Core Annotation Workflow (thesis-critical)

### TASK 1 — Fix stale `CONCEPTS` / `SPEAKERS` references
**File:** `src/ParseUI.tsx`

- [ ] Line 863: `const concept = CONCEPTS.find(...)` → change to `concepts.find(...)`
- [ ] Line 865: `const total = CONCEPTS.length` → change to `concepts.length`
- [ ] Line 1300: `{SPEAKERS.length}` → `{speakers.length}`

These three were missed in the initial wiring pass. `concepts` and `speakers` are already derived from `useConfigStore` — just the references need updating.

---

### TASK 2 — Load IPA/ortho from `annotationStore` on concept/speaker change
**File:** `src/ParseUI.tsx` — `AnnotateView` component (line ~498)

Currently `ipa` and `ortho` are plain local `useState('')`. They need to pre-populate from the stored annotation when the concept or speaker changes.

- [ ] Import `useAnnotationStore` at the top of the file
- [ ] Inside `AnnotateView`, subscribe to `annotationStore.records[speaker]`
- [ ] On mount and when `concept` or `speaker` changes, find the interval in `tiers.ipa` and `tiers.ortho` whose text matches the current concept (look up by concept name in `tiers.concept` intervals — find the interval whose `text` contains `concept.name`, then get the corresponding IPA/ortho interval at the same time range)
- [ ] Pre-populate `ipa` and `ortho` state with that text (empty string if not found)

**Relevant store shape:**
```typescript
// annotationStore.records[speaker].tiers.ipa.intervals[]
// each interval: { start: number, end: number, text: string }
// annotationStore.records[speaker].tiers.concept.intervals[]
// find concept interval where text includes concept.name, use its start/end to match ipa/ortho
```

---

### TASK 3 — Wire "Save Annotation" button
**File:** `src/ParseUI.tsx` — `AnnotateView`, line ~733

Currently renders with no `onClick`.

- [ ] Import `useAnnotationStore` (if not already done from Task 2)
- [ ] Get `selectedRegion` from `usePlaybackStore` (has `start` and `end` from the active WaveSurfer region)
- [ ] On save: call `annotationStore.setInterval(speaker, 'ipa', { start, end, text: ipa })` and `annotationStore.setInterval(speaker, 'ortho', { start, end, text: ortho })`
- [ ] Also write a `concept` tier interval: `annotationStore.setInterval(speaker, 'concept', { start, end, text: concept.name })`
- [ ] Then call `annotationStore.saveSpeaker(speaker)` to persist

Check `src/stores/annotationStore.ts` for the exact method signatures before implementing.

---

### TASK 4 — Wire "Mark Done" button
**File:** `src/ParseUI.tsx` — `AnnotateView`, line ~736

- [ ] On click: call `tagStore.tagConcept('confirmed', concept.id.toString())`
- [ ] Visually: the concept dot in the sidebar will update automatically since `concepts` is derived from `getTagsForConcept`

---

### TASK 5 — Fix "Missing" badge — make it reactive
**File:** `src/ParseUI.tsx` — `AnnotateView`, line 690–692

Currently hardcoded `Missing` badge always shows.

- [ ] Check `annotationStore.records[speaker]?.tiers.ipa.intervals` — if there is at least one interval whose time range overlaps with a concept tier interval for `concept.name`, consider it annotated
- [ ] If annotated: show a green "Annotated" or "Done" badge instead
- [ ] If not annotated: keep the rose "Missing" badge

---

### TASK 6 — Stale comment cleanup in `AnnotateView`
**File:** `src/ParseUI.tsx`

- [ ] Lines 451–468: delete the entire JSDoc block that says `The waveform below is a styled mock...` — the hook is already wired
- [ ] Lines 592–595: delete the `{/* TODO: Replace mock... */}` comment block — already done
- [ ] Line 127 (inside `AIChat` `useEffect`): change `[messages, minimized]` dependency to `[chatSession.messages, minimized]`

---

## Priority 2 — Compare Mode Real Data

### TASK 7 — Replace `MOCK_FORMS` with real annotation data
**File:** `src/ParseUI.tsx` — Compare mode, line ~1158

`MOCK_FORMS` is a hardcoded array of 5 speaker forms. It needs to be derived from `annotationStore`.

- [ ] Inside `ParseUI`, after stores are set up, build `speakerForms` with `useMemo`:
  - For each speaker in `selectedSpeakers`:
    - Get `annotationStore.records[speaker]`
    - Find IPA interval(s) for the current concept (match via concept tier)
    - Count utterance intervals for that concept
    - Get `arabicSim` and `persianSim` from `enrichmentStore` (check `src/stores/enrichmentStore.ts` for shape)
    - Get cognate group from enrichments (if available, else `'—'`)
    - Get `flagged` from tagStore — is the concept tagged `problematic`?
  - Return `SpeakerForm[]`
- [ ] Replace `MOCK_FORMS.filter(f => selectedSpeakers.includes(f.speaker)).map(...)` at line 1158 with `speakerForms.map(...)`
- [ ] If enrichment data isn't available for a speaker+concept, show `0.00` similarity and `'—'` cognate — do not crash

---

### TASK 8 — Wire Reference forms from `enrichmentStore`
**File:** `src/ParseUI.tsx` — Compare mode, lines 1122–1140

Currently hardcoded Arabic رماد and Persian خاکستر.

- [ ] Check `src/stores/enrichmentStore.ts` for what data is available per concept
- [ ] Get enrichments for the current `concept.name` from the store
- [ ] Replace the hardcoded Arabic script + IPA with real values from enrichments
- [ ] Replace the hardcoded Persian script + IPA with real values from enrichments
- [ ] If enrichments not available for this concept: show a "No reference data" placeholder — do not crash
- [ ] Wire the `Volume2` audio play buttons to play a reference audio file if one exists in enrichments (or leave as no-op with a `title="Reference audio not available"` if not)

---

### TASK 9 — Wire Accept / Flag concept buttons
**File:** `src/ParseUI.tsx` — Compare mode, lines 1113–1118

- [ ] **Flag button** (line 1113): `onClick={() => tagStore.tagConcept('problematic', concept.id.toString())}`
- [ ] **Accept concept button** (line 1116): `onClick={() => tagStore.tagConcept('confirmed', concept.id.toString())}`
- [ ] Make the buttons visually reflect current state — if already confirmed, show filled/active state; same for flagged

---

### TASK 10 — Wire Notes field persistence
**File:** `src/ParseUI.tsx` — Compare mode, line ~1220

Currently `notes` is local `useState`. It needs to persist.

- [ ] On blur (or debounced onChange): write to `annotationStore` — either as a dedicated `notes` tier interval or as metadata on the record
- [ ] On concept/speaker change: load the saved note for that concept (empty string if none)
- [ ] Check whether `annotationStore` has a mechanism for free-form notes — if not, store in `localStorage` keyed by `concept.id` as a minimal interim solution

---

### TASK 11 — Wire per-speaker Flag toggle in Compare table
**File:** `src/ParseUI.tsx` — Compare mode, line ~1176

Currently the flag button renders `f.flagged` from `MOCK_FORMS` with no `onClick`.

- [ ] After TASK 7, `f.flagged` comes from `tagStore`. Wire the button `onClick` to toggle:
  - If flagged: `tagStore.untagConcept('problematic', concept.id.toString())`
  - If not: `tagStore.tagConcept('problematic', concept.id.toString())`

---

### TASK 12 — Wire `reviewed` count
**File:** `src/ParseUI.tsx` — line 864

Currently `const reviewed = 0`.

- [ ] Compute: count how many concepts in the current concept list have at least one confirmed tag (`tagStore.getTagsForConcept(c.id.toString()).some(t => t.id === 'confirmed')`)
- [ ] Use that as `reviewed`

---

## Priority 3 — Actions Menu (Pipeline Triggers)

### TASK 13 — Wire Actions menu items to real API endpoints
**File:** `src/ParseUI.tsx` — lines 966–988

All items currently just call `setActionsMenuOpen(false)`.

Wire each to its real endpoint using `fetch` + poll pattern (same as used in legacy `parse.html`):

| Label | Endpoint | Notes |
|---|---|---|
| Import Speaker Data… | Open onboarding modal or `POST /api/import/upload` | Can be a modal trigger for now |
| Run Audio Normalization | `POST /api/normalize` + poll `GET /api/normalize/status/<jobId>` | Show progress in topbar |
| Run Orthographic STT | `POST /api/stt` with `{ model: 'razhan' }` + poll | Show progress |
| Run IPA Transcription | `POST /api/pipeline/run` with `{ ipa_only: true }` + poll | Show progress |
| Run Full Pipeline | Sequential: normalize → STT → IPA | Client-side orchestration |
| Run Cross-Speaker Match | `POST /api/compute/contact-lexemes` | Uses `useComputeJob` |
| Load Decisions | File input → parse JSON → merge into stores | |
| Save Decisions | `GET /api/export/lingpy` → download TSV | |
| Reset Project | Confirmation modal → clear all stores + localStorage | |

- [ ] Add a `runningAction` local state to show inline progress in the topbar area
- [ ] Each action should: close the dropdown → show progress → complete/error

---

## Priority 4 — Compare Compute

### TASK 14 — Wire Compute panel Run + Refresh buttons
**File:** `src/ParseUI.tsx` — right panel, lines 1351–1357

- [ ] Import `useComputeJob` from `src/hooks/useComputeJob.ts`
- [ ] **Run button**: call `useComputeJob` to `POST /api/compute/contact-lexemes` for current selectedSpeakers + concept
- [ ] **Refresh button**: re-fetch enrichments from store
- [ ] Show a loading spinner or disabled state while job is running

---

### TASK 15 — Wire Cognate decision buttons
**File:** `src/ParseUI.tsx` — lines 1189–1201

Accept / Split / Merge / Cycle — these modify cognate groupings in the compute result.

- [ ] Check what API endpoints exist for cognate decisions (look in `python/server.py` for `/api/decisions` or similar)
- [ ] Wire Accept: save current grouping as a decision
- [ ] Wire Split / Merge / Cycle: mutate cognate groupings locally and persist to decisions JSON
- [ ] If no backend endpoint exists yet: write to `localStorage` keyed by `concept.id` as interim

---

## Priority 5 — Tags Mode

### TASK 16 — Wire concept checkboxes in ManageTagsView
**File:** `src/ParseUI.tsx` — `ManageTagsView` component, line ~433

- [ ] Add local `checkedConcepts: Set<string>` state inside `ManageTagsView`
- [ ] `onChange` on each checkbox: toggle that concept's id in `checkedConcepts`
- [ ] Pre-check concepts that already have `selectedTag` applied: check if `selectedTag.id` is in `tagStore.getTagsForConcept(c.id.toString()).map(t => t.id)`
- [ ] **Apply to selected button** (line 411): for each id in `checkedConcepts`, call `tagConcept(selectedTag.id, conceptId)` — pass `tagConcept` + `untagConcept` as props from `ParseUI`
- [ ] **Clear selection button** (line 408): reset `checkedConcepts` to empty Set

---

## Priority 6 — Spectrogram (post-thesis, low urgency)

### TASK 17 — Port spectrogram worker to TypeScript
**Files:** New: `src/workers/spectrogram-worker.ts`, `src/hooks/useSpectrogram.ts`

The legacy worker lives at `parse/js/shared/spectrogram-worker.js` (273 lines, STFT/FFT pipeline).

- [ ] Copy logic to `src/workers/spectrogram-worker.ts` — add TypeScript types
- [ ] Create `src/hooks/useSpectrogram.ts` — manages the Worker lifecycle, posts PCM data, receives `Uint8ClampedArray` image data
- [ ] In `AnnotateView`: when `spectroOn` is true, get the decoded audio buffer from WaveSurfer (`wsRef.current?.getDecodedData()`), post it to the worker, draw result on a `<canvas>` overlay inside the waveform container
- [ ] Replace the CSS gradient placeholder with the real canvas

---

## Right rail Save buttons (Annotate + Compare)

### TASK 18 — Wire right rail Save buttons
**File:** `src/ParseUI.tsx`

- [ ] **Annotate mode right rail "Save annotations"** (line ~1471): same as TASK 3 — call `annotationStore.saveSpeaker(speaker)`
- [ ] **Compare mode right rail "Save decisions"** (line ~1407): same as TASK 15 — persist decisions JSON
- [ ] **Compare mode right rail "Load decisions"** (line ~1405): same as TASK 13 Load Decisions

---

## Verification checklist after all tasks done

```bash
# In /home/lucas/gh/ardeleanlucas/parse
npm run check          # must be 0 errors
npm run test -- --run  # must be >=102 passing
```

Then open in browser at `http://localhost:5173`:
- [ ] Switch to Annotate mode → select a speaker → waveform loads real audio
- [ ] IPA field pre-populates if annotation exists
- [ ] Type IPA → Save → reload → IPA still there
- [ ] Mark Done → concept dot turns green in sidebar
- [ ] Switch to Compare mode → speaker forms table shows real IPA (not ash/bark placeholder data)
- [ ] Accept concept → confirmed badge updates
- [ ] Tags mode → check a concept → Apply to selected → concept dot updates
- [ ] Actions menu → Run Audio Normalization → progress shows in topbar

---

> **parse-gpt:** Work task by task. Do not batch multiple tasks into one commit.
> Commit message format: `feat(parseui): wire <task name> (#<task number>)`
> Open a PR to `feat/annotate-ui-redesign` — do not merge to `main`.
