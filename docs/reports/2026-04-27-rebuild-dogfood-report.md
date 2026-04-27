# PARSE rebuild dogfood report — 2026-04-27

## Summary

- **Workspace / fixture:** `~/parse-rebuild-workspace/` with preloaded `Fail01`
- **Runtime used:** `parse-rebuild-run` on alt ports (`frontend 5174`, `backend 8866`)
- **Browser target:** `http://localhost:5174/`
- **Dogfood scope:** Annotate, Compare, Compute, Shell/nav, and AI chat maintenance-mode surface
- **Flows tested:** 13
- **Issues filed:** 1
- **Blockers:** 0
- **Major issues:** 1
- **Minor issues:** 0

## Overall verdict

**rebuild needs 1 fixes before thesis use**

Rationale: the core annotate edit/save loop appears to succeed in the UI but did not persist edited IPA/orthography field values after reload, which is too risky for thesis annotation work even though the rest of the exercised UI surfaces rendered and the observed console state stayed free of red JS errors.

## Console capture summary

Across the exercised flows, no red browser console errors were observed.

Observed console noise was limited to repeated React Router future-flag warnings:
- `v7_startTransition`
- `v7_relativeSplatPath`

These are warnings, not the cause of the filed regression.

## Surface-by-surface results

### 1. Annotate workstation

#### Flow A1 — load Fail01 and confirm core annotate surface renders
- **Result:** pass
- Confirmed waveform/transport controls render
- Confirmed transcript lanes render
- Confirmed concept `hair` loaded with active speaker `Fail01`

#### Flow A2 — edit visible IPA + orthography fields, save, reload, confirm persistence
- **Result:** **major issue filed**
- Repro was performed by editing the visible `Enter IPA…` and `Enter orthographic form…` fields, invoking save, and reloading.
- After reload, the fields reverted to their previous values instead of persisting the edit.
- **Issue:** #143

#### Flow A3 — undo / redo / save affordances visible
- **Result:** pass (render-level dogfood)
- Undo / redo / save controls rendered in the annotate workstation.
- No browser-console errors observed while exercising the annotate edit path.

### 2. Compare workstation

#### Flow C1 — switch to compare mode and confirm matrix renders
- **Result:** pass
- Concept × speaker compare surface rendered with the single `Fail01` column as expected for the fixture workspace.

#### Flow C2 — open lexeme detail row for Fail01
- **Result:** pass
- Speaker-row expansion opened and exposed the per-speaker detail controls.

#### Flow C3 — add compare note, save, reload, confirm persistence
- **Result:** pass
- Added a temporary compare note (`dogfood-note`).
- Reload showed the note persisted.

#### Flow C4 — create / assign tag, save, reload, confirm persistence
- **Result:** pass
- Created/assigned temporary tag `dogfood-tag`.
- Reload showed the tag persisted and remained attached.

#### Flow C5 — cognate controls render
- **Result:** pass (render-level dogfood)
- `Accept grouping`, `Split`, `Merge`, and `Cycle` controls rendered.

#### Flow C6 — borrowing classification surface renders
- **Result:** pass (render-level dogfood)
- Borrowing section rendered for the concept and remained usable.

### 3. Compute workstation / modals

#### Flow K1 — CLEF config modal open + save
- **Result:** pass
- Switched compute mode to `Borrowing detection (CLEF)`.
- Opened configure modal and saved successfully.
- Post-save surface returned to compare view with CLEF state present.

#### Flow K2 — CLEF Sources Report affordance
- **Result:** pass
- Sources Report open path was exercised and rendered without red console errors.

#### Flow K3 — transcription run / batch-run UI affordance
- **Result:** pass
- Opened the **Run Full Pipeline** modal from the Actions menu.
- The modal rendered speaker/step preview state correctly, including the blocked-state grid for the current speaker.

### 4. Shell / navigation

#### Flow S1 — top-bar transitions between Annotate and Compare
- **Result:** pass
- Switched between Annotate and Compare successfully.

#### Flow S2 — speaker switcher reflects one-speaker fixture
- **Result:** pass
- Only `Fail01` was listed, matching the fixture workspace.

#### Flow S3 — right-panel control cluster renders after post-#136 split
- **Result:** pass
- Right-panel control sections for Speakers / Compute / Filter / Decisions rendered.
- No blank panel state was observed in the exercised compare and annotate views.

#### Flow S4 — Actions menu render
- **Result:** pass
- Actions menu expanded and exposed import / normalization / STT / ORTH / IPA / full-pipeline entries.

### 5. AI chat (maintenance-mode)

#### Flow H1 — open / send interaction to chat surface
- **Result:** pass with maintenance-mode caveat
- Chat surface remained functional enough to expose the provider-connect state.
- The UI presented `Connect PARSE AI` / `Not connected — choose a provider to begin` rather than crashing.
- No browser-console errors were observed.

## Filed issues

| Issue | Label(s) | Surface | Severity | Summary |
|---|---|---|---|---|
| #143 | `dogfood-2026-04-27` | Annotate | major | annotate save does not persist IPA/orthography field edits |

## Follow-up recommendation

1. Fix #143 before thesis-facing rebuild use.
2. Re-run a focused annotate dogfood check on the exact save path after the fix lands.
3. If #143 is fixed cleanly and no new browser-level regressions appear, the rebuild can be reconsidered for thesis use.
