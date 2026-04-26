# Annotate parity evidence — 2026-04-26

**Date:** 2026-04-26  
**Oracle repo:** `ArdeleanLucas/PARSE`  
**Oracle SHA:** `0951287a812609068933ba22711a8ecd97765f38`  
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`  
**Rebuild SHA:** `f9aa3db1aad1d77078c9105cd8b5e5254c066338`  
**Fixture:** `Saha01` single-speaker parity workspace derived from `/home/lucas/parse-workspace`

---

## Method

- Created fresh detached `origin/main` worktrees for oracle and rebuild.
- Injected the same Saha01 fixture artifacts into each temp worktree.
- Built both frontends locally.
- Launched the backend from each temp worktree cwd.
- Browsed the UI through Vite on `:5173` for parity testing rather than the raw backend root.

Temp worktrees used:
- oracle: `/tmp/parse-oracle-parity`
- rebuild: `/tmp/parse-rebuild-parity`

---

## Status legend

- **PASS** — oracle and rebuild produced the same intended behavior for the flow
- **DEVIATION** — behavior differed, but the difference is currently accepted and documented
- **FAIL** — parity diverged or the oracle baseline blocked the flow before it could be exercised end-to-end

---

## Evidence matrix

| Flow | Oracle result | Rebuild result | Status | Evidence |
|---|---|---|---|---|
| Speaker load / enter Annotate | Crashed in `TranscriptionLanes` hook-order error | Loaded Saha01 annotate view cleanly | **FAIL** | `.hermes/reports/parity/annotate/01-speaker-load.txt` |
| Save annotation | Blocked by oracle crash | Save control visible; cross-repo exercise blocked | **FAIL** | `.hermes/reports/parity/annotate/02-save-annotation.txt` |
| Mark concept done | Blocked by oracle crash | Mark Done control visible; cross-repo exercise blocked | **FAIL** | `.hermes/reports/parity/annotate/03-mark-concept-done.txt` |
| STT request | Blocked by oracle crash | STT lane visible; request parity not runnable | **FAIL** | `.hermes/reports/parity/annotate/04-stt-request.txt` |
| Region capture / anchor offset | Blocked by oracle crash | Anchor/offset controls visible; parity not runnable | **FAIL** | `.hermes/reports/parity/annotate/05-region-capture.txt` |
| Undo / redo | Blocked by oracle crash | Undo/Redo controls present; parity not runnable | **FAIL** | `.hermes/reports/parity/annotate/06-undo-redo.txt` |
| Hotkey / playback routing | Blocked by oracle crash | Play/segment controls present; parity not runnable | **FAIL** | `.hermes/reports/parity/annotate/07-hotkey-routing.txt` |

---

## Key observation

The first parity flow already diverged materially:

- **Oracle current-main** fell into an ErrorBoundary with `Rendered more hooks than during the previous render` inside `TranscriptionLanes.tsx` while entering Annotate on the Saha01 fixture.
- **Rebuild current-main** loaded the Saha01 annotate workstation successfully and exposed the expected editing/playback/timestamp controls.

That means the parity loop is now blocked as much by **oracle instability** as by rebuild drift. The correct next step is **not** to silently mark later flows as passing; it is to treat the oracle hook-order crash as a tracked parity blocker for the Annotate surface.

---

## Attached artifacts

- `.hermes/reports/parity/annotate/oracle-annotate-hook-order-crash.txt`
- `.hermes/reports/parity/annotate/oracle-annotate-hook-order-crash.png`
- `.hermes/reports/parity/annotate/rebuild-saha01-annotate-loaded.txt`
- `.hermes/reports/parity/annotate/rebuild-saha01-annotate-loaded.png`

---

## Owner recommendation

- **Primary follow-up owner:** parse-builder / annotate parity lane
- **Reason:** the observed divergence is a React annotate-entry failure rooted in `TranscriptionLanes` / `AnnotateView`, not a backend-only contract mismatch
