# CODING.md — PARSE Build Protocol v4.0

> Read this file before ANY code work on PARSE. Non-negotiable.

## Project Overview

**PARSE** — **P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer

A browser-based phonetic review tool for linguists. Timestamps are the core data model. All annotations are Praat-compatible 4-tier interval structures saved to disk.

- **Plan**: `PROJECT_PLAN.md` (full spec, schemas, UI design, video sync)
- **Interfaces**: `INTERFACES.md` (shared types, events, function signatures)
- **Standards**: `AGENTS.md` (coding standards, format support, what NOT to do)
- **Lessons**: `tasks/lessons.md` (mistakes to not repeat)
- **Repo**: `TarahAssistant/PARSE` — ALL code pushes go here

## Project Directory

```
parse/
├── AGENTS.md              ← coding standards for sub-agents
├── CODING.md              ← you are here (build protocol)
├── INTERFACES.md          ← shared types, events, function signatures
├── PROJECT_PLAN.md        ← full architecture spec (v4.0)
├── python/
│   ├── thesis_server.py           ← HTTP server with range requests + CORS
│   ├── generate_source_index.py   ← ffprobe → source_index.json
│   ├── generate_peaks.py          ← soundfile → peaks JSON (wavesurfer v2)
│   ├── reformat_transcripts.py    ← coarse transcript reformatter
│   ├── generate_ai_suggestions.py ← fuzzy matching pipeline
│   ├── batch_reextract.py         ← ffmpeg segment extraction
│   ├── textgrid_io.py             ← NEW: Praat TextGrid read/write
│   ├── elan_export.py             ← NEW: ELAN XML (.eaf) export
│   ├── csv_export.py              ← NEW: flat CSV export
│   ├── video_sync.py              ← NEW: FFT cross-correlation + drift
│   └── video_clip_extract.py      ← NEW: drift-corrected video clip extraction
├── js/
│   ├── parse.js                   ← panel orchestrator, singleton, state
│   ├── waveform-controller.js     ← wavesurfer v7, MediaElement + peaks
│   ├── spectrogram-worker.js      ← Web Worker FFT (narrow/wide band)
│   ├── transcript-panel.js        ← virtualized list, search, click-to-seek
│   ├── suggestions-panel.js       ← AI suggestions, positional re-ranking
│   ├── region-manager.js          ← region tracking, assignment, export
│   ├── fullscreen-mode.js         ← modal overlay, concept navigation
│   ├── annotation-panel.js        ← NEW: IPA/ortho/concept fields, save/load
│   ├── annotation-store.js        ← NEW: disk persistence, autosave, crash recovery
│   ├── project-config.js          ← NEW: project.json loader + validator
│   ├── video-sync-panel.js        ← NEW: sync UI, dual waveform, fine-tune
│   ├── import-export.js           ← NEW: TextGrid/ELAN/CSV import/export UI
│   └── onboarding.js              ← NEW: project setup wizard
├── review_tool_dev.html           ← HTML shell
├── Start Review Tool.bat          ← Windows launcher
├── start_parse.sh                 ← NEW: macOS/Linux launcher
├── LICENSE                        ← NEW: MIT
├── annotations/                   ← NEW: per-speaker annotation JSON files
├── exports/                       ← NEW: TextGrid, ELAN, CSV, clips output
├── reviews/                       ← code review reports
└── tasks/
    └── lessons.md                 ← mistakes and corrections
```

## Sub-Agent Rules

1. **File ownership is strict** — each sub-agent writes ONLY its assigned files
2. **Read `INTERFACES.md` before writing any JS** — all modules follow the interface contract
3. **Read `AGENTS.md` for coding standards** — `soundfile` not `wave`, vanilla JS, pathlib, etc.
4. **Read `PROJECT_PLAN.md`** for schemas, data models, and constraints
5. **Do NOT modify any file outside your assigned output files**
6. **`git diff --staged` before every commit**

## Architecture: Timestamps Are The Bible

Every annotation in PARSE is a time-stamped segment with 4 tiers:

```
Tier 1 (top):    IPA          "jek"
Tier 2:          Ortho        "یەک"
Tier 3:          Concept      "1:one"
Tier 4 (bottom): Speaker      "Fail01"
```

All downstream operations derive from timestamps:
- Praat TextGrid export → timestamps become interval boundaries
- ELAN XML export → timestamps become time slots
- CSV export → timestamps become start_sec/end_sec columns
- Video clip extraction → timestamps map through drift correction to video frames
- Segment audio export → timestamps become ffmpeg -ss/-to arguments

**No annotation exists without a timestamp. No timestamp exists without user confirmation.**

## Build Waves (v4.0)

### Wave 5 — Core v4.0 (parallel, high priority)

| Stream | Task | Output Files | Deps |
|--------|------|--------------|------|
| **E1** | Annotation data model + disk persistence | `js/annotation-store.js` | INTERFACES.md |
| **E2** | Annotation panel UI (IPA/ortho/concept fields) | `js/annotation-panel.js` | E1 interface |
| **E3** | Project config loader + validator | `js/project-config.js` | INTERFACES.md |
| **E4** | `generate_peaks.py` rewrite (soundfile) | `python/generate_peaks.py` | Nothing |

E1+E3+E4 are independent. E2 depends on E1's interface (not its implementation — can run parallel if interface is defined first).

### Wave 6 — Import/Export (parallel, high priority)

| Stream | Task | Output Files | Deps |
|--------|------|--------------|------|
| **F1** | Praat TextGrid read/write | `python/textgrid_io.py` | Annotation schema |
| **F2** | ELAN XML export | `python/elan_export.py` | Annotation schema |
| **F3** | CSV export | `python/csv_export.py` | Annotation schema |
| **F4** | Import/Export UI (browser) | `js/import-export.js` | F1, E1 |

F1, F2, F3 are independent Python scripts. F4 depends on F1 for TextGrid format and E1 for annotation model.

### Wave 7 — Video Sync (parallel, medium priority)

| Stream | Task | Output Files | Deps |
|--------|------|--------------|------|
| **G1** | FFT cross-correlation + drift detection | `python/video_sync.py` | Nothing |
| **G2** | Video clip extraction | `python/video_clip_extract.py` | G1 sync data |
| **G3** | Video sync panel UI | `js/video-sync-panel.js` | G1, INTERFACES.md |

G1 is independent. G2 uses G1's output format. G3 wraps G1 in a browser UI.

### Wave 8 — Onboarding + Polish (sequential, after waves 5-7)

| Stream | Task | Output Files | Deps |
|--------|------|--------------|------|
| **H1** | Onboarding wizard | `js/onboarding.js` | E3 (project config) |
| **H2** | HTML shell update | `review_tool_dev.html` | All JS modules |
| **H3** | Cross-platform launcher | `start_parse.sh` | Nothing |
| **H4** | MIT LICENSE | `LICENSE` | Nothing |

### Wave 9 — Integration with existing v3.0 code

| Stream | Task | Files Modified | Notes |
|--------|------|----------------|-------|
| **I1** | Wire annotation-store into region-manager | `js/region-manager.js` | Region assign → annotation save |
| **I2** | Wire annotation-panel into parse.js | `js/parse.js` | Panel open → annotation fields appear |
| **I3** | Wire project-config into all data loaders | `js/parse.js`, `review_tool_dev.html` | Replace hardcoded paths |
| **I4** | Update AI suggestions for provider abstraction | `python/generate_ai_suggestions.py` | Add OpenAI/Ollama support |

## Execution Order

```
Step 0: Update INTERFACES.md with v4.0 events + schemas
Step 1: Spawn Wave 5 (E1-E4) — annotation core + peaks rewrite
Step 2: Spawn Wave 6 (F1-F3) alongside Wave 5 — Python export scripts
Step 3: Wait for E1 → Spawn E2 (annotation panel UI)
Step 4: Wait for E1+F1 → Spawn F4 (import/export UI)
Step 5: Spawn Wave 7 (G1-G3) — can overlap with waves 5-6
Step 6: Wait for all → Wave 8 (onboarding, HTML, launchers)
Step 7: Wave 9 — integration wiring (sequential, careful)
Step 8: Review + test + fix integration bugs
```

**Practical:** Waves 5+6+7 can run mostly in parallel (up to 10 tasks). Wave 8 is sequential. Wave 9 is surgical edits to existing files.

## Key Schemas (for sub-agent prompts)

### Annotation File (`annotations/<Speaker>.parse.json`)

```json
{
  "version": 1,
  "project_id": "sk-thesis-2026",
  "speaker": "Fail01",
  "source_audio": "audio/working/Fail01/Faili_M_1984.wav",
  "source_audio_duration_sec": 7200.0,
  "tiers": {
    "ipa": {
      "type": "interval",
      "display_order": 1,
      "intervals": [
        { "start": 506.2, "end": 506.9, "text": "jek" }
      ]
    },
    "ortho": {
      "type": "interval",
      "display_order": 2,
      "intervals": [
        { "start": 506.2, "end": 506.9, "text": "یەک" }
      ]
    },
    "concept": {
      "type": "interval",
      "display_order": 3,
      "intervals": [
        { "start": 506.2, "end": 506.9, "text": "1:one" }
      ]
    },
    "speaker": {
      "type": "interval",
      "display_order": 4,
      "intervals": [
        { "start": 0, "end": 7200.0, "text": "Fail01" }
      ]
    }
  },
  "metadata": {
    "language_code": "sdh",
    "created": "2026-03-23T21:00:00Z",
    "modified": "2026-03-23T22:00:00Z"
  }
}
```

### Video Sync Data

```json
{
  "video_file": "Khan01_session.mp4",
  "audio_file": "audio/working/Khan01/REC00002.wav",
  "fps": 60,
  "sync": {
    "status": "synced",
    "offset_sec": 14.3,
    "drift_rate": 0.00667,
    "method": "fft_auto",
    "ai_verified": true,
    "manual_adjustment_sec": 0.0
  }
}
```

### Timestamp → Video Mapping

```
video_time = (wav_time × (1 + drift_rate/60)) + offset_sec + manual_adjustment_sec
video_frame = round(video_time × fps)
```

## Sub-Agent Prompt Template

Each `opencode_task` prompt MUST include:

1. Module purpose (one paragraph)
2. Exact output file path(s)
3. Interface contract (relevant events + shared data from INTERFACES.md)
4. Relevant schema (copied from this file or PROJECT_PLAN.md)
5. Specific edge cases and constraints
6. **"Do NOT modify any file outside your assigned output files"**
7. **"Read AGENTS.md for coding standards before writing code"**

## What Runs Where

- **Python scripts** — written in sandbox, **executed on user's machine** (needs audio file access)
- **JS modules + HTML** — written in sandbox, **deployed to project directory** for dev server
- **opencode_task sandbox** — `/home/lucas/.openclaw/workspace/parse/`

## Pre-Build Checklist

Before spawning any Wave 5+ sub-agents:

- [ ] INTERFACES.md updated with v4.0 events (annotation events, import/export events, video sync events)
- [ ] `generate_peaks.py` soundfile rewrite (can run as E4 in wave 5)
- [ ] WAV normalization done (Lucas, on Windows) — or at least one speaker for testing

## Post-Build Checklist

After all waves complete:

1. `python3 -m py_compile python/*.py` — all Python scripts compile
2. `node --check js/*.js` — all JS modules pass syntax check
3. Review each file for interface compliance
4. Test: annotations save to disk and survive page reload
5. Test: TextGrid export opens in Praat without errors
6. Test: waveform loads, transcript renders, suggestions appear
7. Test: video sync produces correct offset (if video files available)
8. `git diff --staged` before committing
9. Push to `TarahAssistant/PARSE`
