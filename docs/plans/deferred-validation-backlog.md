# PARSE Deferred Validation Backlog

> **Purpose:** keep LingPy export checks and full browser regression on a realistic to-test list without letting them block current implementation work. Right now the broader goal is to remove legacy JS, make the remaining workflows work, and unblock real onboarding/import testing.

## Current policy

- **C5** and **C6** remain important validation tasks, but they are **not hard gates** for current implementation work.
- If Lucas asks Hermes to work on another PR stage, **do that work**.
- Run these checks later, in the order of actual testing, once onboarding/import and end-to-end flows are usable enough to make the results meaningful.
- Destructive cleanup still needs a scoped PR, rollback discipline, and Lucas review/merge — but not a fake C5/C6 signoff ritual before the product can even be tested properly.

---

## Current automated baseline (captured 2026-04-20)

| Gate | Command | Result |
|---|---|---|
| Frontend/unit/integration tests | `npm run test -- --run` | ✅ 25 files, 138 tests passed |
| TypeScript | `./node_modules/.bin/tsc --noEmit` | ✅ clean |
| API regression | `npm run test:api` | ✅ 24 tests passed |

### Non-blocking warnings observed during automated checks

- Vitest prints React Router future-flag warnings in `AnnotateMode.test.tsx`.
- `storePersistence.test.ts` prints `tagStore` `localStorage is not defined` warnings under jsdom, but the suite still passes.
- `npm run test:api` logs benign config/chat warnings while exercising fallback config paths; the API regression suite still passes end-to-end.

---

## Actual testing order

### 1. Real-data onboarding/import prerequisite

Before C5 or C6 mean anything, confirm the product can actually be exercised with real data:

- [ ] Onboard/import flow is usable enough for real testing
- [ ] A real speaker can be loaded into the React workflow
- [ ] Core annotation/compare state is present from real data rather than scaffolding
- [ ] The agent assisting Lucas with onboarding/testing has enough working surface to proceed

This is the real prerequisite now.

---

### 2. Deferred item: LingPy TSV export check (former C5)

Run this only once onboarding/import is far enough along that the export contains meaningful data.

- [ ] Export LingPy TSV from the React Compare route
- [ ] Verify headers: `ID`, `CONCEPT`, `DOCULECT`, `IPA`, `COGID`, `TOKENS`, `BORROWING`
- [ ] Verify row counts against the dataset actually under test
- [ ] Spot-check speaker names, concepts, IPA, cognate IDs, and borrowing values
- [ ] Record anomalies for later cleanup if the export is still incomplete or premature

### Evidence to record later

- exported filename
- row count
- sampled speakers/concepts checked
- anomalies found

---

### 3. Deferred item: Full browser regression (former C6)

Run this after the real-data onboarding/import path is stable enough for meaningful end-to-end testing.

#### Annotate mode
- [ ] Waveform loads for test speakers
- [ ] Play/pause works
- [ ] Region drag/update works
- [ ] IPA edits auto-save correctly
- [ ] STT completes for at least one concept
- [ ] TextGrid import works
- [ ] CSV export works
- [ ] Refresh preserves annotations
- [ ] Onboarding/auth/chat route behaves as intended

#### Compare mode
- [ ] Concept table renders real data
- [ ] Accept / Reject / Split / Merge persist correctly
- [ ] TagManager create/edit/delete works
- [ ] Tag assignments survive reload
- [ ] Enrichments compute/display correctly
- [ ] LingPy export still works from Compare mode once it is meaningful to test

#### Cross-mode
- [ ] Annotate → Compare → Annotate navigation preserves state
- [ ] Backend connection remains stable
- [ ] No blocking browser console errors appear

### Evidence to record later

- browser used
- speakers tested
- export filenames
- console errors
- sticky/inconsistent steps

---

## What this backlog is **not**

- It is **not** a blocker for other implementation stages.
- It is **not** a reason to refuse work on broader JS-removal/unification goals.
- It is **not** proof that cleanup must wait until every validation item is green.

It is simply the ordered list of tests to return to when the product is ready for real testing.
