# B3 — BorrowingPanel

> **Archived Oda Track B task brief (2026-04-21):** this file is historical implementation scaffolding from the Compare-track React pivot. Do **not** execute it as a live task. Current PARSE work branches from `origin/main`, and the landed Compare code lives in `src/components/compare/`, `src/hooks/`, and `AGENTS.md`.

**Model:** gemini-2.5-flash
**Read first:** `js/compare/borrowing-panel.js` (1,678 lines)
**Output:** `src/components/compare/BorrowingPanel.tsx` + `BorrowingPanel.test.tsx`
**Requires:** `enrichmentStore` implemented.

---

## What It Is

Shows all cells currently marked `status === 'borrowed'` across all speakers and concepts.
For each entry:

- Concept label + speaker ID
- IPA form
- Donor language field (editable text input)
- Confidence score (0.0–1.0) shown as a `ProgressBar` (from shared components)
- Confirm Borrow button — no-op if already confirmed, marks it reviewed
- Revert to Pending button — sets `status = 'pending'`

Data source: filter `enrichmentStore.data.table.cells` for `status === 'borrowed'`.
All mutations via `enrichmentStore.save()`.
Empty state: text "No borrowings marked." — no emoji.

---

## Required Tests

```typescript
describe('BorrowingPanel', () => {
  it('lists only cells with status borrowed', () => { ... })
  it('shows empty state text when no borrowed cells exist', () => { ... })
  it('editing donor language input calls enrichmentStore.save with updated value', () => { ... })
  it('Revert button sets cell status to pending', () => { ... })
})
```

Run: `npm run test -- BorrowingPanel`
Expected: 4 passed, 0 failed.
