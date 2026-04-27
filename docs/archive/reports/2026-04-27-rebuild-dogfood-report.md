> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../..).

# PARSE rebuild dogfood report — 2026-04-27

## Summary

- **Workspace / fixture:** `~/parse-workspace/` real thesis workspace
- **Runtime used:** `parse-rebuild-run` on alt ports (`frontend 5174`, `backend 8866`)
- **Browser target:** `http://127.0.0.1:5174/`
- **Dogfood scope:** Annotate, Compare, Compute, shell/nav, and AI chat connect state
- **Flows tested:** 9
- **Issues filed:** 4
- **Blockers:** 2
- **Major issues:** 2
- **Minor issues:** 0

## Overall verdict

**rebuild blocked by 2 issues before thesis use**

Rationale: the rebuild successfully loaded the real 10-speaker / 521-concept workspace and exercised real annotation, compare, and compute paths, but two blocker-class failures emerged during the live dogfood run:

1. the frontend dev server was killed during real-workspace Annotate load (#153)
2. Annotate save did not persist edited IPA values after reload (#143)

Additional major regressions remain in Compare notes persistence (#154) and CLEF populate behavior (#155).

## Runtime / evidence summary

### Real workspace load

The rebuild loaded the real workspace surface rather than the old one-speaker fixture:
- `10 speakers`
- `521 concepts`
- speaker list included `Fail01, Fail02, Kalh01, Khan01, Khan02, Khan03, Khan04, Mand01, Qasr01, Saha01`

### Browser console

No red browser-console errors were captured for the save/persistence failures. The browser console stayed effectively clean during the confirmed regressions.

### Backend / process evidence

The backend stayed alive through the run and continued serving real annotation/STT/audio requests. The most important process-level evidence was:
- frontend process emitted `[frontend] Killed` during real Annotate load
- backend stayed healthy on `:8866`
- CLEF job completed but logged `total_filled=0`

## Surface-by-surface results

### 1. Annotate workstation

#### Flow A1 — load real Annotate surface from thesis workspace
- **Result:** pass with blocker discovered during runtime
- Real workspace Annotate data loaded, including waveform / transport / transcript lanes.
- Speaker-specific annotation data was observed for all 10 speakers.
- During the real-workspace Annotate load, `parse-rebuild-run` logged `[frontend] Killed` and the dev server stopped answering.
- **Issue:** #153

#### Flow A2 — switch across all real speakers and confirm annotation payloads load
- **Result:** pass
- Confirmed visible Annotate data loads for all 10 real speakers.
- Examples observed during the run:
  - `Fail01` → `ndʒɚ`
  - `Fail02` → `ɡis`
  - `Kalh01` → `ɪŋtwɛnti`
  - `Khan02` → `qaʒ`
  - `Mand01` → `ʁiʒ`
  - `Qasr01` → `ʁez`
  - `Saha01` → `muːsɛr`

#### Flow A3 — edit IPA field, save annotation, reload, confirm persistence
- **Result:** blocker
- Edited the visible `Enter IPA…` field on `Fail01` / `hair`, invoked save, and reloaded.
- The annotation file on disk did not change, and reload restored the original value.
- **Issue:** #143

### 2. Compare workstation

#### Flow C1 — load the full compare matrix on the real workspace
- **Result:** pass
- Compare rendered against the real workspace and was re-expanded back to `10 / 10` selected speakers.
- The matrix displayed all 10 speaker rows for concept `hair`.

#### Flow C2 — compare notes persistence across reload
- **Result:** major issue filed
- Entered a temporary note into `Add observations, etymological notes, or questions for review…`.
- Reload cleared the field instead of restoring the note.
- **Issue:** #154

#### Flow C3 — cognate / borrowing controls render on the real matrix
- **Result:** pass (render-level dogfood)
- `Accept grouping`, `Split`, `Merge`, and `Cycle` rendered.
- Borrowing section rendered and remained navigable.

### 3. Compute workstation

#### Flow K1 — switch compute mode to Borrowing detection (CLEF) and run job
- **Result:** major issue filed
- The header progress chip reached `Populating CLEF reference data… 100%`.
- The backend completed the job but logged zero fetched forms:
  - `fetch_and_merge done: total_filled=0 per_lang={'ar': 0, 'fa': 0}`
- **Issue:** #155

### 4. Shell / navigation

#### Flow S1 — top-bar transitions between Compare and Annotate
- **Result:** pass with instability caveat
- Mode switching itself worked.
- However, the real Annotate path exposed the frontend-killed blocker (#153).

#### Flow S2 — Actions / right-panel shell surfaces render on the real workspace
- **Result:** pass
- Actions menu and right-panel control sections rendered.
- Real workspace speaker controls reflected the 10-speaker dataset.

### 5. AI chat surface

#### Flow H1 — open chat surface and verify disconnected-state behavior
- **Result:** pass with connect-state caveat
- The chat surface did not crash.
- It presented the provider-connect state (`Not connected — choose a provider to begin`).
- No red browser-console errors were observed.

## Filed issues

| Issue | Label(s) | Surface | Severity | Summary |
|---|---|---|---|---|
| #143 | `dogfood-2026-04-27` | Annotate | blocker | annotate save does not persist IPA/orthography field edits |
| #153 | `dogfood-2026-04-27` | Shell / Annotate runtime | blocker | frontend dev server is killed during real-workspace Annotate load |
| #154 | `dogfood-2026-04-27` | Compare | major | compare notes are not persisted across reload |
| #155 | `dogfood-2026-04-27` | Compute / CLEF | major | CLEF populate can complete with zero fetched reference forms |

## Follow-up recommendation

1. Fix #153 and #143 before any thesis-facing rebuild cutover claim.
2. Re-run a focused real-workspace Annotate dogfood pass after those fixes land.
3. Then recheck Compare notes persistence (#154).
4. Finally, rerun CLEF populate with the intended provider/config setup and confirm that the UI communicates zero-result failure states cleanly (#155).
