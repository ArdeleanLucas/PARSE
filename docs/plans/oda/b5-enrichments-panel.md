# B5 — EnrichmentsPanel

**Model:** gemini-2.5-flash
**Read first:** `js/compare/enrichments.js` (1,557 lines)
**Output:** `src/components/compare/EnrichmentsPanel.tsx` + `EnrichmentsPanel.test.tsx`
**Requires:** `useComputeJob` hook (B8) — implement B8 before wiring the compute button.

---

## What It Is

Shows pre-computed phonetic enrichments for the currently active concept.
Enrichments are pairwise values between all speaker combinations.

---

## Data Shape

From `enrichmentStore.data.enrichments`:

```typescript
interface ConceptEnrichments {
  concept_id: string;
  pairs: Array<{
    speaker_a: string;
    speaker_b: string;
    edit_distance: number;
    pmi: number | null;
    alignment: string | null;   // e.g. "p-a-t-a / p-a-t-e"
    cognate_candidate: boolean;
  }>;
}
```

---

## Behavior

- Reads `uiStore.activeConcept` to know which concept to show.
- If `uiStore.activeConcept` is null → render nothing.
- If enrichments exist for active concept → show pairs table.
- If no enrichments exist for active concept → show `[Run Compute]` button.
- `[Run Compute]` → calls `useComputeJob(activeSpeaker).start()` where `activeSpeaker`
  comes from `uiStore.activeSpeaker` (ParseBuilder's store — read-only).
- While job running → show `ProgressBar` (shared component) with `useComputeJob.state.progress`.
- On job complete → `enrichmentStore.load()` refreshes data automatically
  (handled inside `useComputeJob`).
- On job error → show error message text. No emoji.

---

## Required Tests

```typescript
describe('EnrichmentsPanel', () => {
  it('renders nothing when uiStore.activeConcept is null', () => { ... })
  it('shows pairs table when enrichments exist for active concept', () => { ... })
  it('shows Run Compute button when no enrichments for active concept', () => { ... })
  it('shows ProgressBar when compute job status is running', () => { ... })
  it('shows error text when compute job status is error', () => { ... })
})
```

Run: `npm run test -- EnrichmentsPanel`
Expected: 5 passed, 0 failed.
