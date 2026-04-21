# B1 — ConceptTable

> **Archived Oda Track B task brief (2026-04-21):** this file is historical implementation scaffolding from the Compare-track React pivot. Do **not** execute it as a live task. Current PARSE work branches from `origin/main`, and the landed Compare code lives in `src/components/compare/`, `src/hooks/`, and `AGENTS.md`.

**Model:** gemini-2.5-pro (complex grid render + state logic)
**Read first:** `js/compare/concept-table.js` (873 lines), `js/compare/compare.js` lines 1–500
**Output:** `src/components/compare/ConceptTable.tsx` + `ConceptTable.test.tsx`
**Blocks:** B2 cannot start until B1 tests pass.

---

## What It Is

The central grid of Compare Mode. Rows = concepts, columns = speakers.
Each cell shows the IPA form for that (concept, speaker) pair plus a status badge.

---

## Data Shape

Comes from `enrichmentStore.data.table` (type defined in `src/api/types.ts`):

```typescript
interface ConceptRow {
  concept_id: string;
  concept_label: string;   // display label e.g. "water"
}

interface CellData {
  ipa: string;
  ortho: string;
  cognate_set: string | null;  // e.g. "SET-1" — null = unassigned
  status: 'accepted' | 'rejected' | 'pending' | 'borrowed';
}

interface TableData {
  concepts: ConceptRow[];
  speakers: string[];   // ordered
  cells: {
    [concept_id: string]: {
      [speaker_id: string]: CellData
    }
  }
}
```

---

## Rendering Rules

- `enrichmentStore.data` is null → show loading skeleton
- `enrichmentStore.loading` is true → show progress indicator
- Status badge CSS classes (no emoji, no inline color):
  - `pending` → class `badge--pending` (grey)
  - `accepted` → class `badge--accepted` (green tint)
  - `rejected` → class `badge--rejected` (red tint)
  - `borrowed` → class `badge--borrowed` (orange tint)
- Clicking a cell → `uiStore.setActiveConcept(concept_id)`
- Cognate set label shown inside cell as small text. Cells sharing the same
  `cognate_set` value share a color group class. Derive class name deterministically
  from the set ID string (e.g. hash → one of 12 CSS classes). No hardcoded palette.
- Grid must handle 800 concept rows × 10 speaker columns without layout breakage.
  Use CSS grid. Add windowed list (e.g. react-virtual) only if scroll performance
  degrades measurably — do not add it speculatively.

---

## Required Tests

```typescript
describe('ConceptTable', () => {
  it('renders one row per concept in enrichmentStore', () => { ... })
  it('renders one column header per speaker', () => { ... })
  it('shows loading skeleton when enrichmentStore.loading = true', () => { ... })
  it('clicking a cell calls uiStore.setActiveConcept with correct concept_id', () => { ... })
  it('cells with the same cognate_set share a CSS color-group class', () => { ... })
  it('status badge has correct class for each of the four status values', () => { ... })
})
```

Run: `npm run test -- ConceptTable`
Expected: 6 passed, 0 failed.
