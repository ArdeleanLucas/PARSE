# CODING.md — Source Explorer Build Protocol

> Read this file before ANY code work on source-explorer. Non-negotiable.

## Project Overview

Build the Source Explorer review tool using parallel `opencode_task` sub-agents.

- **Plan**: `PROJECT_PLAN.md` (full spec, schemas, edge cases)
- **Interfaces**: `INTERFACES.md` (shared types, events, function signatures — created FIRST)
- **Lessons**: `tasks/lessons.md` (mistakes to not repeat)

## Project Directory

All build output goes to: `/home/lucas/.openclaw/workspace/source-explorer/`

```
source-explorer/
├── CODING.md                  ← you are here
├── INTERFACES.md              ← shared types, function sigs, events (created FIRST)
├── PROJECT_PLAN.md            ← full spec
├── python/                    ← all Python scripts
│   ├── thesis_server.py
│   ├── generate_source_index.py
│   ├── generate_peaks.py
│   ├── reformat_transcripts.py
│   ├── generate_ai_suggestions.py
│   └── batch_reextract.py
├── js/                        ← JS modules (loaded by HTML)
│   ├── source-explorer.js     ← panel orchestrator, singleton, state persistence
│   ├── waveform-controller.js ← wavesurfer init, MediaElement + peaks, nav controls
│   ├── transcript-panel.js    ← virtualized list, search, click-to-seek, highlight
│   ├── suggestions-panel.js   ← AI suggestions, positional prior selector, re-ranking
│   ├── spectrogram-worker.js  ← Web Worker for FFT (narrow-band + wide-band)
│   ├── region-manager.js      ← region selection, assignment, export, decisions JSON
│   └── fullscreen-mode.js     ← modal overlay, prev/next missing concept
├── review_tool_dev.html       ← HTML shell (loads all JS modules)
├── Start Review Tool.bat      ← updated batch file
├── reviews/                   ← review output data
└── tasks/
    └── lessons.md             ← mistakes and corrections
```

## Sub-Agent Rules

1. **File ownership is strict** — each sub-agent writes ONLY its assigned files. No conflicts.
2. **Read `INTERFACES.md` before writing any JS** — all modules follow the interface contract.
3. **Read `PROJECT_PLAN.md`** for schemas, edge cases, and constraints relevant to your module.
4. **Do NOT modify any file outside your assigned output files.**
5. **`git diff --staged` before every commit.**

## Parallel Streams

### Wave 1 — Foundation (parallel, no deps)

| Stream | Task | Output Files | Notes |
|--------|------|--------------|-------|
| **A1** | Python: HTTP server | `python/thesis_server.py` | Range requests, CORS, Windows paths |
| **A2** | Python: source_index generator | `python/generate_source_index.py` | Reads ffprobe output, writes JSON |
| **A3** | Python: peaks generator | `python/generate_peaks.py` | Reads WAV via `wave` module, outputs peaks JSON |
| **A4** | Python: transcript reformatter | `python/reformat_transcripts.py` | Simplifies coarse JSON schema |
| **A5** | Python: AI suggestions generator | `python/generate_ai_suggestions.py` | Fuzzy matching, base scores only |
| **A6** | Python: batch re-extractor | `python/batch_reextract.py` | Reads export JSON, runs ffmpeg |

All 6 Python scripts are independent. Spawn all at once.

Each task prompt MUST include:
- The relevant schema from `PROJECT_PLAN.md` (copy the JSON examples in)
- Input/output file paths
- Edge cases from the plan (bit depth, script mixing, Levenshtein thresholds, etc.)

### Wave 2 — JS Core (parallel, depends on INTERFACES.md)

| Stream | Task | Output Files | Notes |
|--------|------|--------------|-------|
| **B1** | JS: panel orchestrator | `js/source-explorer.js` | Singleton logic, open/close, localStorage |
| **B2** | JS: waveform controller | `js/waveform-controller.js` | wavesurfer v7, MediaElement, peaks, AbortController |
| **B3** | JS: spectrogram worker | `js/spectrogram-worker.js` | Web Worker, FFT, ≤30s cap, greyscale |

### Wave 3 — JS Features (parallel, depends on Wave 2 interfaces)

| Stream | Task | Output Files | Notes |
|--------|------|--------------|-------|
| **C1** | JS: transcript panel | `js/transcript-panel.js` | Virtualized list, search, highlight |
| **C2** | JS: suggestions panel | `js/suggestions-panel.js` | AI suggestions, positional prior selector, re-ranking |
| **C3** | JS: region manager | `js/region-manager.js` | Region selection, assignment, export |
| **C4** | JS: fullscreen mode | `js/fullscreen-mode.js` | Modal overlay, prev/next navigation |

### Wave 4 — Integration (sequential, after all waves)

| Stream | Task | Output Files | Notes |
|--------|------|--------------|-------|
| **D1** | HTML shell + assembly | `review_tool_dev.html`, `Start Review Tool.bat` | Loads all JS, defines panel HTML structure |

## Execution Order

```
Step 0: Create INTERFACES.md (defines all shared types, events, function signatures)
Step 1: Spawn Wave 1 (A1–A6) — all 6 Python scripts in parallel
Step 2: Spawn Wave 2 (B1–B3) — can run alongside Wave 1
Step 3: Wait for Wave 2 to finish → Spawn Wave 3 (C1–C4) in parallel
Step 4: Wait for all waves → Spawn Wave 4 (D1) for integration
Step 5: Manual review + fix any integration issues
```

**In practice:** Waves 1 and 2 launch simultaneously (9 parallel tasks). Wave 3 launches once Wave 2 interfaces are stable (4 more tasks). Wave 4 is the final assembly.

## Interface Contract (INTERFACES.md)

Before spawning ANY sub-agent, write `INTERFACES.md` with:

1. **Global namespace:** `window.SourceExplorer` — all modules attach here
2. **Events (CustomEvent on document):**
   - `se:panel-open` — `{speaker, conceptId, sourceWav}`
   - `se:panel-close` — `{speaker}`
   - `se:seek` — `{timeSec}` — any module can request a seek
   - `se:region-created` — `{startSec, endSec}`
   - `se:region-assigned` — `{speaker, conceptId, startSec, endSec, sourceWav}`
   - `se:suggestion-click` — `{suggestionIndex, segmentStartSec}`
   - `se:transcript-click` — `{segmentIndex, startSec}`
   - `se:priors-changed` — `{selectedSpeakers: string[]}`
   - `se:fullscreen-toggle` — `{}`
3. **Shared data access:**
   - `window.SourceExplorer.sourceIndex` — loaded source_index.json
   - `window.SourceExplorer.transcripts` — loaded coarse transcripts (keyed by speaker)
   - `window.SourceExplorer.suggestions` — loaded ai_suggestions.json
   - `window.SourceExplorer.decisions` — current decisions state (read/write)
4. **Module init pattern:** Each module exports an `init(container)` function called by the HTML shell
5. **DOM contract:** Each module receives a specific container div ID (defined in HTML shell)

## Sub-Agent Prompt Template

Each `opencode_task` prompt includes:
1. The module's purpose (one paragraph)
2. The exact output file path(s)
3. The interface contract (relevant events + shared data)
4. The relevant schema sections (copied from PROJECT_PLAN.md)
5. Specific edge cases and constraints
6. **"Do NOT modify any file outside your assigned output files"**

## What Runs Where

- **Python scripts** — written in sandbox, **executed on Lucas's Windows machine** (they need access to `C:\Users\Lucas\Thesis\`)
- **JS modules + HTML** — written in sandbox, **deployed to `C:\Users\Lucas\Thesis\`** for dev server
- **opencode_task sandbox** — `/home/lucas/.openclaw/workspace/source-explorer/`

## Post-Build Checklist

After all waves complete:
1. Review each file for interface compliance
2. Test HTML shell loads all modules without console errors
3. Copy entire `source-explorer/` to Lucas's Windows machine
4. Run `thesis_server.py` + open `review_tool_dev.html` in Chrome
5. Verify: waveform loads, transcript renders, suggestions appear, regions work
