# B6 — SpeakerImport

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


> **Historical React-pivot handoff note (2026-04-21):** this file was written as an implementation brief during the Compare-track migration. `src/components/compare/SpeakerImport.tsx` has already landed, and the legacy source file named below was removed in Stage 3 / PR #58. Do **not** treat this as a pending task checklist.
>
> **Read current code first:** `src/components/compare/SpeakerImport.tsx` and `src/components/compare/SpeakerImport.test.tsx`.

**Original model:** gemini-2.5-flash
**Historical source at capture time:** `js/compare/speaker-import.js` (removed in PR #58)
**Original output target:** `src/components/compare/SpeakerImport.tsx` + `SpeakerImport.test.tsx`
**Renders as:** `Modal` from `src/components/shared/` (ParseBuilder's)

---

## What It Is

A wizard for importing a new speaker's annotation JSON into Compare Mode.
Four-step state machine.

---

## State Machine

```
idle → upload → preview → merging → done
                  |
                cancel
                  |
                idle
```

| Step | What happens |
|---|---|
| `idle` | Not visible. Triggered by a button in CompareMode. |
| `upload` | Drag-and-drop or file input. Accepts `{Speaker}.json`. |
| `preview` | Parse the JSON. Show: speaker ID, concept count, annotation count. Confirm or Cancel. |
| `merging` | Call `saveAnnotation(speaker, record)` from `client.ts`. Show spinner. Then call `enrichmentStore.load()`. |
| `done` | Show success message: "Speaker {id} imported." + Close button. |

---

## Rules

- Renders inside `Modal` (from shared). Pass `onClose` to Modal.
- Cancel from preview → returns to `idle` (closes modal).
- File validation: must be valid JSON, must have a `speaker` field and `tiers` object.
  Show inline error text for invalid files — no modal.
- `saveAnnotation` is from `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`) (ParseBuilder's function).
  Do not add your own fetch call.
- After successful merge: call `enrichmentStore.load()` to refresh the compare table.

---

## Required Tests

```typescript
describe('SpeakerImport', () => {
  it('transitions from upload to preview when valid JSON file is selected', () => { ... })
  it('preview shows detected speaker ID and concept count', () => { ... })
  it('shows inline error for invalid JSON file', () => { ... })
  it('confirm calls saveAnnotation with correct speaker and record', () => { ... })
  it('cancel from preview returns to idle', () => { ... })
  it('done step shows success message with speaker ID', () => { ... })
})
```

Run: `npm run test -- SpeakerImport`
Expected: 6 passed, 0 failed.
