# B9 — CompareMode Root + Assembly

**Model:** gemini-2.5-flash
**Output:** `src/components/compare/CompareMode.tsx` + `CompareMode.test.tsx`
**Requires:** All of B1–B8 complete and tested.

---

## What It Is

The root component mounted at `/compare` by React Router in `src/App.tsx`.
Assembles all Track B components into the Compare Mode layout.

---

## Layout

```
+--[TopBar: "Annotate" link | "Compare" link | [Import Speaker] button]--+
|                                                                          |
|  [ConceptTable — full-width main grid]                                   |
|                                                                          |
|  +--[Sidebar panel switcher]-----------------------------------------+  |
|  | [Cognate] [Borrowing] [Enrichments] [Tags]  tab buttons           |  |
|  |                                                                    |  |
|  | <CognateControls />  or  <BorrowingPanel />  or                   |  |
|  | <EnrichmentsPanel /> or  <TagManager />                           |  |
|  +--------------------------------------------------------------------+  |
|                                                                          |
|  {SpeakerImport modal — shown when import triggered}                     |
+--------------------------------------------------------------------------+
```

---

## Wiring Rules

- `TopBar` → import from `src/components/shared/TopBar.tsx` (ParseBuilder's).
  Do not reimplement it. Pass nav links and the Import Speaker button as props or children.
- Sidebar tab buttons → call `uiStore.setComparePanel('cognate' | 'borrowing' | 'enrichments' | 'tags')`
- Active panel → read from `uiStore.comparePanel`
- `CognateControls` → only renders when `uiStore.activeConcept` is not null
- `SpeakerImport` → renders as `Modal` overlay, shown when import button clicked
  (local `useState<boolean>` for modal open/close is fine here — it is pure UI state)
- On mount:
  1. `enrichmentStore.load()` if `enrichmentStore.data === null`
  2. `tagStore.hydrate()` once

---

## Required Tests

```typescript
describe('CompareMode', () => {
  it('renders ConceptTable on mount', () => { ... })
  it('calls enrichmentStore.load() on mount when data is null', () => { ... })
  it('calls tagStore.hydrate() on mount', () => { ... })
  it('sidebar switches to BorrowingPanel when Borrowing tab clicked', () => { ... })
  it('CognateControls is not rendered when activeConcept is null', () => { ... })
  it('CognateControls renders when activeConcept is set', () => { ... })
})
```

Run: `npm run test -- CompareMode`
Expected: 6 passed, 0 failed.

---

## Browser Checklist (Lucas verifies personally)

Before declaring Track B done, Lucas must confirm all of these in a real browser
at `http://localhost:5173/compare` with Python server running on :8766:

- [ ] CompareMode renders without errors
- [ ] ConceptTable shows correct concept × speaker grid
- [ ] Click a cell → CognateControls opens for that pair
- [ ] Accept a cognate → cell badge updates immediately
- [ ] Split a cognate set → set ID changes, cell gets new color group
- [ ] Mark a form as borrowed → BorrowingPanel shows it
- [ ] Open TagManager → create a tag → assign 3 concepts → right panel reflects them
- [ ] Reload page → tags persist (localStorage round-trip working)
- [ ] Search in TagManager right panel → filters correctly
- [ ] EnrichmentsPanel → [Run Compute] → progress bar → results load
- [ ] Export LingPy TSV → file downloads, non-empty, correct headers:
      `ID  DOCULECT  CONCEPT  IPA  COGID  TOKENS  NOTE`
- [ ] No `window.PARSE` references in browser console
- [ ] No TypeScript errors in browser console

Track B is not done until every item above has a checkmark from Lucas.
Notify ParseBuilder when ready — he leads the Phase C merge.
