> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../..).

# PARSE rebuild dogfood addendum — post-fix verification — 2026-04-27

## Verdict

**needs-fixes**

PR #158 landed, but focused real-workspace re-verification against `~/parse-workspace/` shows that two of the previously reported persistence defects still fail in browser-level save → reload testing. The rebuild is therefore **not cutover-ready yet**.

## Scope

- Workspace: `~/parse-workspace/`
- Runtime: `parse-rebuild-run` (`frontend :5174`, `backend :8866`)
- Browser target: `http://127.0.0.1:5174/`
- Verification pass type: focused post-fix regression confirmation, end-to-end thesis flow spot check, and light adjacent-surface sanity pass
- Baseline fix PR under verification: [#158](https://github.com/TarahAssistant/PARSE-rebuild/pull/158)

## A. Regression-confirm results

### #143 — Annotate IPA / orthography persistence
- **Result:** fail
- **Flow:** Annotate → `Fail01` → concept `hair` → edit `Enter IPA…` + `Enter orthographic form…` → `Save Annotation` → reload
- **Observed:** reloaded values reverted to the pre-edit persisted data instead of the new values
- **Evidence:** [post-fix-143-regression-failed.png](../pr-assets/post-fix-143-regression-failed.png)
- **Console:** no red browser-console errors captured for the save attempt

### #153 — Vite frontend stays alive during real-workspace Annotate load
- **Result:** pass
- **Flow:** load Annotate on real workspace and switch speakers sequentially
- **Speakers explicitly exercised:** `Fail02`, `Kalh01`, `Mand01`
- **Observed:** frontend stayed alive; Vite process remained up; no browser JS errors
- **Evidence:** [post-fix-153-stable-after-speaker-switches.png](../pr-assets/post-fix-153-stable-after-speaker-switches.png)
- **Console:** only normal Vite connect logs and React Router future-flag warnings

### #154 — Compare notes persist across reload without blur
- **Result:** fail
- **Flow:** Compare → type note into observations textarea → reload immediately without blur
- **Observed:** note did not persist; after reload the textarea value was empty
- **Evidence:** browser-console inspection after reload confirmed the textarea value as empty string
- **Console:** no red browser-console errors captured during the interaction

## B. End-to-end thesis flow

### Speaker exercised
- `Fail02`

### Flow
1. Open Annotate on real workspace
2. Switch to `Fail02`
3. Edit a real IPA transcription
4. Save
5. Reload
6. Confirm persistence
7. Switch to Compare on the same concept
8. Confirm the edit reflects in the matrix
9. Make/save a cognate decision
10. Reload and confirm

### Result
- **Fail**

### Why it failed
- The flow broke at the save → reload persistence step.
- The edited IPA value did not survive reload, so the verification could not honestly claim the remaining Compare-side thesis flow as passed.

### Console
- No red browser-console errors were observed during this partial run.

## C. Light sanity coverage

| Surface | Result | Notes |
|---|---|---|
| AI chat panel opens/renders | pass | surface rendered; no regression observed |
| Mode / panel navigation | pass | switching surfaces remained functional |
| Tags surface renders | partial | reached tag manager and confirmed controls render, but did not complete create + assign + reload before the run stopped |
| CLEF config modal | not completed | out-of-scope backend issue #155 remains separate |

## D. New findings

- **None distinct from the existing dogfood issues.**
- This pass did **not** isolate a new blocker/major/minor beyond the already known persistence/runtime set.
- The important outcome is that `#143` and `#154` still reproduce under live browser verification on the real workspace despite PR #158 having merged.

## Console / runtime summary

- Backend was healthy on `:8866`
- `parse-rebuild-run` remained pointed at the real thesis workspace
- Browser console stayed free of red JS errors during the confirmed failures
- The previously reported frontend-death issue `#153` did not reproduce in this verification pass

## Updated cutover recommendation

**Hold cutover.**

The rebuild is **not** ready for thesis cutover until the live persistence failures for `#143` and `#154` are actually resolved and re-verified on `~/parse-workspace/`.
