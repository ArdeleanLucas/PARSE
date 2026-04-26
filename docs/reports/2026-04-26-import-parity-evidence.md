# PARSE-rebuild Import/onboarding parity evidence — 2026-04-26

**Date:** 2026-04-26  
**Oracle repo:** `ArdeleanLucas/PARSE`  
**Oracle SHA:** `c2fb743fbb30119bfcd18ce9d802f3125449acdf`  
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`  
**Rebuild SHA:** `768a155b78148039472f1c47bbf322430af9c1e8`

---

## TL;DR

**Import/onboarding parity is aligned across oracle and rebuild on all 7 audited flow outcomes, with 1 shared deviation and 6 passing flows.**

- **Shared deviation:** the regular `/api/onboard/speaker` route still writes Windows-style backslashes into its result payload and `source_index.json` on **both** oracle and rebuild.
- **Confirmed fixed on both sides:** the path-separator bug targeted by oracle sync PR #233 is now closed for the two `import_processed_speaker` flows. Both processed-import write paths persisted forward-slash project-relative paths.
- **Reload survival:** both UIs reloaded with `3 speakers`, `3 concepts`, and visible tag `Import Parity Tag (2)`.

---

## Runtime harness

### Oracle runtime
- Frontend: `http://127.0.0.1:15173/`
- Backend: `http://172.27.0.1:18766/`

### Rebuild runtime
- Frontend: `http://127.0.0.1:15174/`
- Backend: `http://172.27.0.1:18776/`

### Harness note
The parity run used **fresh detached current-main worktrees** plus local-only harness patches in those temp worktrees only:
- `python/server.py` port constants moved off `8766/8767` to avoid an occupied Windows listener
- `vite.config.ts` was given a temporary `PARSE_API_HOST` override so Vite in WSL could proxy to the Windows-side backend listener

These harness changes were **not** repo changes and are not proposed for merge.

### Workspace + fixtures
Both sides ran against the same synthetic parity workspace + shared fixture set rooted at:
- workspaces: `/tmp/parse-oracle-import-workspace`, `/tmp/parse-rebuild-import-workspace`
- fixtures: `/tmp/parse-import-fixtures`

---

## Flow matrix

| # | Flow | Oracle | Rebuild | Grounded evidence |
|---|---|---|---|---|
| 01 | Onboard speaker import | DEVIATION | DEVIATION | Both onboarded `Imp01` and loaded 2 concepts, but both wrote backslash paths like `audio\original\Imp01\Imp01.wav` into `source_index.json` and the job result payload |
| 02 | Processed speaker import (write path) | PASS | PASS | `import_processed_speaker` wrote POSIX `audio/working/ProcWrite01/speaker.wav` on both sides |
| 03 | Processed speaker import (preserve-existing merge) | PASS | PASS | Both preserved `audio/original/ProcMerge01/speaker.wav`, appended `audio/working/ProcMerge01/speaker.wav`, made the working WAV primary, and cleared stale `peaks_file` / `legacy_transcript_csv` |
| 04 | Pure CSV concept import (current shipped CSV helper) | PASS | PASS | Both merged the same `concepts-import.csv` with `matched=2`, `added=1`, `total=3` |
| 05 | Tag CSV import | PASS | PASS | Both created `Import Parity Tag` (`#10b981`) with concept IDs `1` and `3` |
| 06 | Empty/error states | PASS | PASS | Both returned the same 400s for missing audio, blank speaker ID, all-miss tag CSV, and malformed concepts CSV |
| 07 | Persistence after reload | PASS | PASS | Both UIs reloaded with `3 concepts`, `3 speakers`, and visible `Import Parity Tag 2` |

---

## Critical path-separator comparison (flows 2 + 3)

### Flow 02 — processed import write path
Both sides now write the same POSIX path under `source_index.json`:
- oracle: `audio/working/ProcWrite01/speaker.wav`
- rebuild: `audio/working/ProcWrite01/speaker.wav`

### Flow 03 — preserve-existing merge
Both sides now retain the same ordered source set:
1. `audio/original/ProcMerge01/speaker.wav`
2. `audio/working/ProcMerge01/speaker.wav`

And on both sides:
- primary source becomes only `audio/working/ProcMerge01/speaker.wav`
- stale `peaks_file` is removed
- stale `legacy_transcript_csv` is removed

**Conclusion:** the oracle sync fix from `ArdeleanLucas/PARSE#233` is confirmed for the processed-speaker import family on both oracle and rebuild.

---

## Shared deviation — onboard route still emits backslashes

The regular onboard job still writes Windows-style separators on both sides:
- oracle `source_index.json`: `audio\original\Imp01\Imp01.wav`
- rebuild `source_index.json`: `audio\original\Imp01\Imp01.wav`

The job result payloads also use backslashes for:
- `wavPath`
- `csvPath`
- `annotationPath`

This is **not rebuild drift**. It is a shared import-route deviation tracked as [ArdeleanLucas/PARSE#236](https://github.com/ArdeleanLucas/PARSE/issues/236), and it remains outside the processed-speaker fix validated above.

---

## Supplemental shipped import surface — CommentsImport

Current main also ships an Audition-comments CSV import surface (`CommentsImport.tsx` / `POST /api/lexeme-notes/import`). I exercised it as supplemental evidence because it belongs to the same import family even though PR #118's 7-row matrix focused primarily on onboarding + processed import + CSV helpers.

Result:
- oracle: PASS
- rebuild: PASS

Both sides imported 2 notes for `ProcWrite01` and matched them to existing lexeme intervals:
- concept `1` → `imported note`
- concept `2` → `second note`

---

## Screenshots

- [Oracle final import parity state](docs/pr-assets/pr-import-parity-oracle-final.png)
- [Rebuild final import parity state](docs/pr-assets/pr-import-parity-rebuild-final.png)

### Screenshot hash note

- Oracle final screenshot SHA256: `f35ed92706232b6661bd65ece68f2985305b581b34d79f1254726076b9acf3a4`
- Rebuild final screenshot SHA256: `f35ed92706232b6661bd65ece68f2985305b581b34d79f1254726076b9acf3a4`

The final screenshots are byte-identical. As in the Tags pass, that is consistent with exact visible parity, but it makes distinct-hash sanity checks non-informative. The primary grounding remains the API/file evidence plus the browser-visible reload state.

---

## Interpretation

This pass moves the import/onboarding surface out of §12 priority position 1.

What it proves:
- rebuild and oracle are aligned on the current shipped import helpers
- the processed-speaker path-separator fix is live on both sides
- the ordinary onboard route still has a shared path-format deviation that should be tracked separately if Lucas wants POSIX paths there too

What it does **not** prove:
- a richer wizard-style Audition concept importer beyond the currently shipped CSV helpers
- any parity judgment about the still-open chat_tools / TranscriptionLanes / BatchReportModal agent PRs, which are orthogonal to this surface
