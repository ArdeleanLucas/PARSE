# PARSE React Pivot Bugs (2026-04-08)

## Critical

**Bug: Cannot select speaker or continue in Compare mode**
- Screenshot: [attached]
- Symptoms: Speaker list and table cells are not interactive. No way to select speaker, activate concept, or proceed with cognate/tagging workflow. "Continue" buttons or panel switches do not respond.
- Affected: Compare mode (B1–B6 components), uiStore integration, event handlers on table cells and sidebar.
- Branch: feat/compare-react
- Repro: Load http://localhost:5173, switch to Compare, try selecting any speaker or concept.
- Impact: Blocks all comparative analysis. Blocks thesis workflow with Dr. Kurd.

## Other Known Issues

- Shared component prop mismatches (className on Panel, progress vs value on ProgressBar, Modal 'open' prop, barrel imports for '../shared').
- B1–B3 components (ConceptTable, CognateControls, BorrowingPanel) were deleted as boundary violations from Track A — recreated on feat/compare-react but need verification.
- Enrichment data typing (similarity, cognateSet not in base EnrichmentsPayload).
- No dark mode or menu reorganization yet (per MC-282–286).
- Dev server occasionally killed by SIGTERM during startup.

## Next Steps
- Fix speaker selection and event wiring in ConceptTable + uiStore.
- Add `index.ts` barrel in shared/ or update all imports to individual files.
- Run full `npm run test` and `npx tsc --noEmit` on feat/compare-react.
- Lucas review of live build at :5173.

Update this file as bugs are found/fixed. Prioritize selection workflow for thesis data entry.

**Last updated:** 2026-04-08 by Oda (Track B)
