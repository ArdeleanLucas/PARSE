# BUILD SESSION — PARSE v4.0

**Created:** 2026-03-23 22:23 CET
**Purpose:** Execution plan for the next session. Read this, then build.

---

## Pre-Flight

Before spawning ANY sub-agents:

1. Read `CODING.md` — build waves, sub-agent rules, schemas
2. Read `INTERFACES.md` — events, global namespace (`window.PARSE`), DOM contract
3. Read `AGENTS.md` — coding standards (`soundfile` not `wave`, vanilla JS, etc.)

---

## What Exists (v3.0, already built)

14 files from Waves 1-4 are built and committed. They use the OLD namespace (`window.SourceExplorer`, `se:` events). They will be migrated in Wave 9.

**Python (6 files):** thesis_server.py, generate_source_index.py, generate_peaks.py, reformat_transcripts.py, generate_ai_suggestions.py, batch_reextract.py

**JS (7 files):** parse.js, waveform-controller.js, spectrogram-worker.js, transcript-panel.js, suggestions-panel.js, region-manager.js, fullscreen-mode.js

**HTML + launcher (2 files):** review_tool_dev.html, Start Review Tool.bat

---

## What To Build (v4.0)

### Wave 5 — Core (5 parallel tasks)

| Task | File | What It Does |
|------|------|-------------|
| **E1** | `js/annotation-store.js` | Annotation data model, load/save to disk (`annotations/*.parse.json`), autosave, crash recovery via localStorage backup. Listens to `parse:annotation-save/delete`. Fires `parse:annotations-loaded/changed`. |
| **E2** | `js/annotation-panel.js` | UI: IPA, ortho, concept input fields below the waveform. Save button fires `parse:annotation-save`. Populates from existing annotations on panel open. Depends on E1 interface. |
| **E3** | `js/project-config.js` | Loads + validates `project.json`. Sets `window.PARSE.project`. Fires `parse:project-loaded` or `parse:project-error`. |
| **E4** | `python/generate_peaks.py` | REWRITE: replace `wave` module with `soundfile`. Must handle 16/24/32-bit WAV, RF64, MP3, FLAC. Normalize to float32 internally. Same output format (wavesurfer PeaksData v2). |
| **E5** | `python/normalize_audio.py` | NEW: two-pass ffmpeg `loudnorm`. Reads `audio/original/` → writes `audio/working/`. 16-bit PCM mono, 44.1kHz, -16 LUFS. Never modifies originals. Skips already-normalized files. Cross-platform ffmpeg path. |

**Spawn order:** E1, E3, E4, E5 simultaneously. E2 after E1 starts (needs interface, not implementation).

**Prompt template for each:** Copy the relevant schema from INTERFACES.md + CODING.md into the prompt. Include: purpose, output files, events listened/fired, edge cases, "Do NOT modify files outside your assignment", "Read AGENTS.md for coding standards".

### Wave 6 — Import/Export (4 parallel tasks)

| Task | File | What It Does |
|------|------|-------------|
| **F1** | `python/textgrid_io.py` | Praat TextGrid read AND write. 4 tiers: IPA (top), Ortho, Concept, Speaker. Reads `.TextGrid` (both long and short format). Writes `.TextGrid` (long format). Maps to/from annotation JSON schema. |
| **F2** | `python/elan_export.py` | ELAN XML (.eaf) export. Maps annotation tiers to ELAN tiers with time slots in milliseconds. |
| **F3** | `python/csv_export.py` | Flat CSV export: speaker, concept_id, concept_en, start_sec, end_sec, duration_sec, ipa, ortho, source_file |
| **F4** | `js/import-export.js` | UI: import/export modal. TextGrid import (replace speaker / create new). Export buttons for TextGrid, ELAN, CSV, segment audio. Fires `parse:import-textgrid`, `parse:export-*`. |

**Spawn order:** F1, F2, F3 simultaneously. F4 after F1 is done (needs TextGrid format knowledge).

### Wave 7 — Video Sync (3 parallel tasks)

| Task | File | What It Does |
|------|------|-------------|
| **G1** | `python/video_sync.py` | FFT cross-correlation for offset detection. Multi-point drift measurement. Accepts video file + audio file + fps. Outputs offset_sec + drift_rate. Uses scipy `fftconvolve`. |
| **G2** | `python/video_clip_extract.py` | Reads annotation timestamps + sync data. Applies drift-corrected mapping. Extracts video clips via ffmpeg `-ss`/`-to`. |
| **G3** | `js/video-sync-panel.js` | UI: video file selector, FPS dropdown, auto-sync button, dual waveform display, offset fine-tune slider, lock button. Status indicator (🔴🟡🟢). Fires `parse:video-sync-*` events. |

**Spawn order:** G1, G2, G3 can all be parallel (G2 reads G1's output format but doesn't need the code).

### Wave 8 — Onboarding + Polish (sequential)

| Task | File | What It Does |
|------|------|-------------|
| **H1** | `js/onboarding.js` | Project setup wizard: name, SIL language picker, contact languages, audio file selection, speaker setup, concept CSV import, AI config. Writes `project.json`. |
| **H2** | `review_tool_dev.html` | UPDATE: add new DOM containers (`parse-annotation`, `parse-video-sync`, `parse-io-modal`, `parse-onboarding`), load new JS modules, update script tags. |
| **H3** | `start_parse.sh` | NEW: macOS/Linux launcher (equivalent to Start Review Tool.bat). |
| **H4** | `LICENSE` | MIT license file. |

**Spawn order:** H1 first (depends on E3). H2 after ALL waves 5-7 complete. H3+H4 trivial, do manually.

### Wave 9 — Integration (SEQUENTIAL, careful)

| Task | Files Modified | What Changes |
|------|----------------|-------------|
| **I1** | All existing JS files | Migrate `window.SourceExplorer` → `window.PARSE`, `se:` → `parse:`, DOM IDs `se-` → `parse-` |
| **I2** | `js/region-manager.js` | Wire "Assign" button into `parse:annotation-save` flow |
| **I3** | `js/parse.js` | Wire annotation-panel into panel open/close lifecycle |
| **I4** | `python/generate_ai_suggestions.py` | Add AI provider abstraction (OpenAI/Ollama alongside Sonnet) |

**Spawn order:** I1 first (namespace migration). I2-I4 after I1 completes. These are SURGICAL edits to existing files — review carefully before committing.

---

## Execution Plan

```
Batch 1 (8 slots): E1 + E2 + E3 + E4 + E5 + F1 + F2 + F3
  → Wave 5 (all 5) + Wave 6 Python scripts (3) = 8 parallel

Batch 2 (after some Batch 1 slots free): F4 + G1 + G2 + G3
  → F4 needs F1 done. G1-G3 are independent.

Batch 3 (sequential): H1 → H2
  → H1 needs E3. H2 needs everything.

Manual: H3 (shell launcher) + H4 (LICENSE)

Batch 4 (sequential, careful): I1 → I2 + I3 + I4
  → Namespace migration first, then wiring.

Final: Full review + test + commit + push
```

**Maximum parallel tasks at once:** 8 (hard limit on concurrent sub-agents)
**Estimated total:** 12-16 opencode_task dispatches

---

## After Build Completes

1. `python3 -m py_compile python/*.py` — all Python compiles
2. `node --check js/*.js` — all JS passes syntax check
3. Verify annotation save/load round-trips
4. Verify TextGrid export opens in Praat
5. `git diff --staged` → review → commit → push to `TarahAssistant/PARSE`
6. Update `tasks/lessons.md` with anything learned
7. Update daily memory file

---

## Key Reminders

- **opencode_task works** (tested this session, ~50s for simple tasks)
- **projectName: "parse"** for all opencode_task calls
- **Sub-agents see AGENTS.md** in the project dir (coding standards, format support)
- **New modules use `window.PARSE` and `parse:` events** from the start
- **Old modules stay on `window.SourceExplorer`** until Wave 9 migration
- **Never use Python `wave` module** — use `soundfile`
- **Never modify `audio/original/`** — working copies only

---

## 🟢 Progress Log — 2026-03-23 Session

**Updated:** 23:10 CET

### Batch 1 Status (Waves 5 + 6 Python)

| Task | File | Status | Notes |
|------|------|--------|-------|
| E1 | `js/annotation-store.js` | ⏳ Running (iter 4/5) | Retry after AbortError failures |
| E2 | `js/annotation-panel.js` | ✅ Done | IPA/ortho/concept UI, RTL ortho field |
| E3 | `js/project-config.js` | ✅ Done | project.json loader, validation, video-sync-locked save |
| E4 | `python/generate_peaks.py` | ✅ Done | Full soundfile rewrite, stereo→mono, chunked, MP3 fallback |
| E5 | `python/normalize_audio.py` | ✅ Done | Two-pass loudnorm, mtime skip, all formats, ffmpeg path resolution |
| F1 | `python/textgrid_io.py` | ✅ Done | Long+short read, long write, bidirectional roundtrip tested |
| F2 | `python/elan_export.py` | ✅ Done | ELAN XML, deduped time slots, UTF-8 XML escaping |
| F3 | `python/csv_export.py` | ✅ Done | Single/all-speakers, UTF-8 BOM, overlap join |

### Batch 2 Status (Wave 6 JS + Wave 7)

| Task | File | Status | Notes |
|------|------|--------|-------|
| F4 | `js/import-export.js` | ✅ Done | TextGrid import UI, per-speaker + all-speaker exports, io-complete toast |
| G1 | `python/video_sync.py` | ⏳ Finalizing | FFT cross-correlation, drift detection, scipy/numpy fallback |
| G2 | `python/video_clip_extract.py` | ✅ Done | Drift-corrected mapping, dry-run mode, ffprobe bounds check |
| G3 | `js/video-sync-panel.js` | ✅ Done | 🔴🟡🟢 status indicator, polling flow, lock event |

### Remaining (Next Session)

| Wave | Task | File | Notes |
|------|------|------|-------|
| 8 | H1 | `js/onboarding.js` | Project setup wizard (depends on E3 project-config) |
| 8 | H2 | `review_tool_dev.html` | Add DOM containers for all new v4.0 modules, load new script tags |
| 8 | H3 | `start_parse.sh` | macOS/Linux launcher (trivial, can do manually) |
| 8 | H4 | `LICENSE` | MIT (trivial, can do manually) |
| 9 | I1 | All existing JS | Migrate `window.SourceExplorer` → `window.PARSE`, `se:` → `parse:`, `se-` → `parse-` IDs |
| 9 | I2 | `js/region-manager.js` | Wire "Assign" button into `parse:annotation-save` flow |
| 9 | I3 | `js/parse.js` | Wire annotation-panel into panel open/close lifecycle |
| 9 | I4 | `python/generate_ai_suggestions.py` | Add OpenAI/Ollama provider abstraction |

### Post-Build Checklist (Next Session)

- [ ] `python3 -m py_compile python/*.py`
- [ ] `node --check js/*.js`
- [ ] Annotation save/load round-trip test
- [ ] TextGrid export opens in Praat
- [ ] `git diff --staged` → review → commit → push to `TarahAssistant/PARSE`
- [ ] Update `tasks/lessons.md`
- [ ] Update `memory/2026-03-23.md`

### Session Summary (2026-03-23)

**Built tonight:** 13 new files across Waves 5, 6, and 7
- `js/annotation-store.js` — annotation data model, persistence, TextGrid/ELAN/CSV/segments export
- `js/annotation-panel.js` — IPA/ortho/concept UI fields, save/delete, RTL ortho
- `js/project-config.js` — project.json loader, schema validation, video sync save-back
- `js/import-export.js` — TextGrid import modal, per-speaker + all-speaker export buttons
- `js/video-sync-panel.js` — video sync UI, polling flow, 🔴🟡🟢 status, lock
- `python/generate_peaks.py` — full soundfile rewrite (was wave module)
- `python/normalize_audio.py` — two-pass ffmpeg loudnorm, mtime skip, all formats
- `python/textgrid_io.py` — bidirectional Praat TextGrid I/O, long+short read
- `python/elan_export.py` — ELAN XML .eaf export, deduped time slots
- `python/csv_export.py` — flat CSV, UTF-8 BOM, overlap join
- `python/video_sync.py` — FFT cross-correlation, drift detection *(finalizing)*
- `python/video_clip_extract.py` — drift-corrected clip extraction via ffmpeg

**Blocked pattern:** `opencode_task` hits AbortError in iter 1-2 consistently; workaround = spawn via `sessions_spawn` with `gpt54` model when opencode fails repeatedly.
