# MC-301 — ParseUI actions menu import speaker modal wiring

## Objective
Complete the next ParseUI wiring slice by turning the top-bar Actions > Import Speaker Data entry into a real modal-backed flow that reuses the existing `SpeakerImport` component inside the unified shell.

## Scope
1. Work on the canonical code branch path for ParseUI: `feat/parseui-unified-shell` -> `main`.
2. Add a failing ParseUI regression test that proves the action opens the import modal.
3. Wire the action menu item to open a shared modal and render `SpeakerImport`.
4. Close the dropdown after invocation and allow the modal to close cleanly.
5. Run `npm run check`, targeted ParseUI tests, then the full Vitest suite.
6. Open/update the PR and request review from `TrueNorth49`.

## Academic / product considerations
- This is operational infrastructure for fieldwork onboarding, so the UI must expose a recoverable import path without breaking Annotate/Compare state.
- The shell should reuse existing PARSE primitives rather than create a second import implementation.
- No emoji in any UI labels.

## Files in scope
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `docs/plans/MC-301-parseui-actions-import.md`

## Test strategy
- RED: add a ParseUI test that clicks `Actions` -> `Import Speaker Data…` and expects the import modal content to appear.
- GREEN: implement the minimal modal state and rendering needed to satisfy the test.
- REFACTOR: keep the modal wiring local and avoid premature endpoint orchestration until the import trigger is stable.

## Completion criteria
- Actions menu import item opens a real modal containing `SpeakerImport`.
- The menu closes after the click.
- Typecheck passes.
- Targeted ParseUI tests pass.
- Full test suite passes.
- A PR to `main` is opened from `feat/parseui-unified-shell` with reviewer request to `TrueNorth49`.
