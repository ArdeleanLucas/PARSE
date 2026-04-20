# PARSE Phase 4 — C5/C6 Signoff Checklist

> **Purpose:** provide the manual signoff gate that must be cleared before any C7 / Stage 3 legacy-entrypoint deletion. Hermes can automate supporting checks, but **Lucas must personally sign off C5 and C6**.

## Stage-3 readiness snapshot

- `AGENTS.md` still blocks **C7 cleanup / legacy deletion** until **C5 + C6 are explicitly cleared**.
- The open docs-audit lane (**PR #53**) correctly treats vanilla-JS removal as a later destructive stage, not work that can start pre-signoff.
- This checklist is the missing operator document that `parsebuilder-todo.md` and `parseui-current-state-plan.md` already reference.
- **This file does not imply signoff.** It only defines the evidence Lucas must gather and record.

---

## Current automated baseline (captured 2026-04-20)

### Automated gates

| Gate | Command | Result |
|---|---|---|
| Frontend/unit/integration tests | `npm run test -- --run` | ✅ 25 files, 138 tests passed |
| TypeScript | `./node_modules/.bin/tsc --noEmit` | ✅ clean |
| API regression | `npm run test:api` | ✅ 24 tests passed |

### Non-blocking warnings observed during automated checks

- Vitest prints React Router future-flag warnings in `AnnotateMode.test.tsx`.
- `storePersistence.test.ts` prints `tagStore` `localStorage is not defined` warnings under jsdom, but the suite still passes.
- `npm run test:api` logs benign config/chat warnings while exercising fallback config paths; the API regression suite still passes end-to-end.

These are **not** currently treated as gate failures, but they should be kept in mind if output is tightened later.

---

## Test environment for manual signoff

Start both services from the canonical repo:

```bash
# Terminal 1
python3 python/server.py

# Terminal 2
npm run dev
```

Primary URLs:

- Annotate: `http://localhost:5173/`
- Compare: `http://localhost:5173/compare`

Legacy fallback pages on `:8766` are **not** the signoff target for C5/C6.
If the Python server banner prints `parse.html` / `compare.html` URLs, ignore those for this phase and stay on the React/Vite routes above.

---

## C5 — LingPy TSV export signoff

**Goal:** verify the thesis-critical export from the React workflow, not the legacy HTML pages.

### Steps

1. Open `http://localhost:5173/compare`
2. Click the **Export LingPy TSV** button
3. Open the downloaded file in a spreadsheet editor or text editor
4. Verify all of the following:
   - [ ] file downloads successfully
   - [ ] file is non-empty
   - [ ] headers include: `ID`, `CONCEPT`, `DOCULECT`, `IPA`, `COGID`, `TOKENS`, `BORROWING`
   - [ ] row count matches expected concept × speaker coverage for the current dataset
   - [ ] `DOCULECT` values match the expected speaker names
   - [ ] `CONCEPT` values are correct for sampled rows
   - [ ] `IPA` values match known annotations for at least one trusted speaker (for example `Fail01`)
   - [ ] `COGID` values are populated in a way that matches current compare decisions
   - [ ] `BORROWING` values match current borrowing adjudication state
   - [ ] no obvious TSV corruption (misaligned columns, broken quoting, blank body)

### Evidence to record

- date/time of signoff
- exported filename
- row count
- sampled speaker(s) / concept(s) checked
- any anomalies found

### Status

- [ ] **Lucas C5 signoff complete**

---

## C6 — browser regression signoff

**Goal:** validate the current React/Vite PARSE workflow end-to-end in the browser.

### Annotate mode

- [ ] Waveform loads for each T1 speaker: `Fail01`, `Fail02`, `Kalh01`, `Mand01`, `Qasr01`, `Saha01`
- [ ] Play/pause works without audio glitch
- [ ] Dragging a region updates annotation context correctly
- [ ] Editing an IPA field auto-saves within ~1 second
- [ ] STT pipeline runs to completion for at least one concept
- [ ] Import TextGrid populates tiers correctly
- [ ] Export CSV produces a valid file
- [ ] Hard refresh preserves existing annotations
- [ ] Onboarding flow reaches the AI assistant panel as intended (auth choices visible if no provider is signed in)

### Compare mode

- [ ] ConceptTable renders for all T1 speakers
- [ ] Accept / Reject / Split / Merge actions persist to enrichments
- [ ] TagManager creates, edits, and deletes tags correctly
- [ ] Tag assignment survives page reload
- [ ] EnrichmentsPanel shows computed values after compute flow
- [ ] LingPy TSV export still works from Compare mode and matches C5 expectations

### Cross-mode

- [ ] Navigate Annotate → Compare → Annotate with no state loss
- [ ] Python backend on port `8766` remains connected throughout the session
- [ ] No blocking browser console errors appear during the workflow

### Watchpoints during C6

These are items to pay special attention to during browser signoff:

- historical Compare interactivity bug noted in `docs/bugs.md`
- onboarding-to-chat routing in Annotate mode
- export behavior from the React Compare route, not the legacy fallback page
- any place where docs or launchers still nudge the user toward `:8766/parse.html` or `:8766/compare.html`

### Evidence to record

- browser used
- speakers tested
- export filename(s)
- any console errors
- any steps that still feel sticky or inconsistent

### Status

- [ ] **Lucas C6 signoff complete**

---

## Exit rule before C7 / Stage 3 deletion

Do **not** begin legacy removal (`parse.html`, `compare.html`, `js/`, Python static fallback cutover, launcher deletion) until both are checked:

- [ ] C5 complete
- [ ] C6 complete

Once both are signed off, Hermes can prepare the destructive Stage 3 / C7 unification PR.
