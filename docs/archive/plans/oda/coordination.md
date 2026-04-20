# Coordination Protocol and Completion Gate

> Reference this when you are blocked, need something from ParseBuilder,
> or are ready to hand off.

---

## Coordination Protocol

| Situation | Action |
|---|---|
| Phase 0 scaffold not ready | Wait. Run gate check. Tell ParseBuilder what is failing. |
| Need a shared component (Button, Modal, etc.) | Request from ParseBuilder with exact props interface. Do not implement yourself. |
| Need a new `client.ts` function | Request from ParseBuilder with exact TypeScript signature. Do not add fetch calls. |
| Need a new `src/api/types.ts` type | Request from ParseBuilder with exact interface. |
| `/api/export/lingpy` returns 404 | STOP. Report to ParseBuilder and Lucas immediately. Block on this. |
| `/api/export/nexus` returns 404 | Stop and report. Same rule. |
| Any Python endpoint returns unexpected shape | Report to ParseBuilder. Do not work around it. |
| Store shape needs amendment | Write the proposed change. File it with Lucas for approval. Do not touch code first. |
| A component needs `uiStore` state that doesn't exist yet | Request from ParseBuilder with exact field name and type. |
| Track B automated tests pass | Run full checklist below, then notify ParseBuilder to begin Phase C. |

---

## Legacy File Reference

Read these before implementing each component. They are the behavioral source of truth.

| Component / Store | Read This First |
|---|---|
| ConceptTable | `js/compare/concept-table.js` (873 lines) + `js/compare/compare.js` lines 1–500 |
| CognateControls | `js/compare/cognate-controls.js` (854 lines) |
| BorrowingPanel | `js/compare/borrowing-panel.js` (1,678 lines) |
| TagManager | `js/shared/tags.js` (845 lines) + `js/compare/compare.js` (search 'tag') |
| EnrichmentsPanel | `js/compare/enrichments.js` (1,557 lines) |
| SpeakerImport | `js/compare/speaker-import.js` (2,147 lines) |
| tagStore | `js/shared/tags.js` |
| enrichmentStore | `js/shared/annotation-store.js` (enrichments section) |

Full dual-agent plan: `docs/plans/react-vite-pivot.md`

---

## Track B Completion Gate

**Automated (run before contacting ParseBuilder):**

```bash
npm run test
# Expected: all tests pass, zero failures

npx tsc --noEmit
# Expected: zero errors
```

Confirm every test file exists:
- `src/components/compare/ConceptTable.test.tsx`
- `src/components/compare/CognateControls.test.tsx`
- `src/components/compare/BorrowingPanel.test.tsx`
- `src/components/compare/TagManager.test.tsx`
- `src/components/compare/EnrichmentsPanel.test.tsx`
- `src/components/compare/SpeakerImport.test.tsx`
- `src/components/compare/CompareMode.test.tsx`
- `src/hooks/useExport.test.ts`
- `src/hooks/useComputeJob.test.ts`

**Browser checklist (Lucas verifies personally at `http://localhost:5173/compare`):**

- [ ] CompareMode renders without console errors
- [ ] ConceptTable shows correct concept × speaker grid
- [ ] Click a cell → CognateControls opens for that pair
- [ ] Accept a cognate → cell badge updates immediately
- [ ] Split a cognate set → set ID changes, cell gets new color group
- [ ] Mark a form as borrowed → BorrowingPanel shows it
- [ ] Open TagManager → create a tag → assign 3 concepts → right panel reflects them
- [ ] Reload page → tags persist (localStorage round-trip)
- [ ] Search in TagManager right panel → filters correctly
- [ ] EnrichmentsPanel → [Run Compute] → progress bar appears → results load on complete
- [ ] Export LingPy TSV → file downloads, non-empty, headers: `ID DOCULECT CONCEPT IPA COGID TOKENS NOTE`
- [ ] No `window.PARSE` in browser console
- [ ] No TypeScript errors in browser console

Track B is not done until every browser item has a checkmark from Lucas.
When all items are confirmed, notify ParseBuilder to begin Phase C merge.

---

## Track B Audit (2026-04-08)

Oda's original B1-B6 submission was audited and found non-functional:

- **Wrong branch:** Work was committed to `feat/annotate-react` instead of `feat/compare-react`.
- **3/6 files missing:** ConceptTable, BorrowingPanel, and EnrichmentsPanel were never created.
- **3/6 were stubs:** CognateControls, TagManager, and SpeakerImport existed but contained placeholder logic with no real functionality.
- **0 tests:** None of the six components had any test files.

**Salvaged:** `tagStore.ts` was a solid implementation (full CRUD, v1→v2 migration, persist). It was moved to `feat/compare-react`.

**Rebuilt by ParseBuilder:** All six B1-B6 components were implemented from scratch on `feat/compare-react` (commit 44ee8de), with 32 tests passing and full TypeScript compliance.

**Current state:** B1-B6 are done on `feat/compare-react`. Oda's remaining scope:
- **B7** — `useExport.ts` + `useComputeJob.ts` hooks
- **B8** — `CompareMode.tsx` root component (assembly + routing)
- **B9** — Browser integration test (Lucas verifies personally)
