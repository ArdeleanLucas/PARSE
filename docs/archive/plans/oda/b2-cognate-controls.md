# B2 — CognateControls

> **Archived Oda Track B task brief (2026-04-21):** this file is historical implementation scaffolding from the Compare-track React pivot. Do **not** execute it as a live task. Current PARSE work branches from `origin/main`, and the landed Compare code lives in `src/components/compare/`, `src/hooks/`, and `AGENTS.md`.

**Model:** gemini-2.5-flash
**Read first:** `js/compare/cognate-controls.js` (854 lines)
**Output:** `src/components/compare/CognateControls.tsx` + `CognateControls.test.tsx`
**Requires:** B1 tests passing. `enrichmentStore` implemented.

---

## What It Is

A panel showing adjudication controls for the active (concept, speaker) cell.
Appears when `uiStore.activeConcept` is set. Driven entirely by `enrichmentStore`.

---

## Props

```typescript
interface CognateControlsProps {
  conceptId: string
  speakerId: string
  onClose: () => void
}
```

---

## Controls

| Button | Mutation |
|---|---|
| Accept | `cells[concept][speaker].status = 'accepted'` — assigns cognate set if unset |
| Reject | `cells[concept][speaker].status = 'rejected'` |
| Split | Creates new unique cognate_set ID for this cell only, breaks from current set |
| Merge | Opens target-set picker; merges this cell into chosen set |
| Cycle | Rotates cell through available cognate_set IDs |
| Mark Borrowed | `status = 'borrowed'`; reveals donor language text input |

All mutations: `enrichmentStore.save(updatedData)`.
No local state for cell data — read from `enrichmentStore.data.table.cells`.

---

## Required Tests

```typescript
describe('CognateControls', () => {
  it('Accept sets status to accepted and calls enrichmentStore.save', () => { ... })
  it('Reject sets status to rejected', () => { ... })
  it('Split generates a new cognate_set ID distinct from the current one', () => { ... })
  it('Mark Borrowed sets status to borrowed and reveals donor language input', () => { ... })
  it('renders nothing when conceptId is null', () => { ... })
})
```

Run: `npm run test -- CognateControls`
Expected: 5 passed, 0 failed.
