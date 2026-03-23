# AGENTS.md — Source Explorer Project

## What This Is

A browser-based audio review tool for a Southern Kurdish phonetic thesis. It lets a linguist browse full source recordings (30–200 min each, 500MB–3GB WAVs), view coarse transcripts, get AI-powered suggestions for where target words occur, and select/assign audio regions for re-extraction.

**Tech stack:** Vanilla JS (ES2020, no build step), wavesurfer.js v7, Web Workers, Python 3.8+ scripts, HTML served from a local Python HTTP server on Windows.

## Project Structure

```
source-explorer/
├── AGENTS.md              ← you are here
├── INTERFACES.md          ← shared types, events, function signatures (READ THIS FIRST)
├── PROJECT_PLAN.md        ← architecture, schemas, UI design
├── python/                ← data prep + server scripts (run on Windows)
│   ├── thesis_server.py
│   ├── generate_source_index.py
│   ├── generate_peaks.py
│   ├── reformat_transcripts.py
│   ├── generate_ai_suggestions.py
│   └── batch_reextract.py
├── js/                    ← browser modules (loaded by HTML)
│   ├── source-explorer.js       ← panel orchestrator, singleton
│   ├── waveform-controller.js   ← wavesurfer v7, MediaElement + peaks
│   ├── spectrogram-worker.js    ← Web Worker FFT
│   ├── transcript-panel.js      ← virtualized list, search, click-to-seek
│   ├── suggestions-panel.js     ← AI suggestions, positional prior re-ranking
│   ├── region-manager.js        ← region tracking, assignment, export
│   └── fullscreen-mode.js       ← modal overlay, concept navigation
├── review_tool_dev.html   ← HTML shell (loads all JS modules)
├── Start Review Tool.bat  ← Windows launcher
└── reviews/               ← code review reports (not deployed)
```

## Before You Write Code

1. **Read `INTERFACES.md`** — it defines the event bus, global namespace (`window.SourceExplorer`), DOM contract, data schemas, and module init pattern. All modules communicate via CustomEvents on `document`. Do not invent new patterns.

2. **Read `PROJECT_PLAN.md`** — it has the full architecture, data file schemas, UI mockups, and risk mitigations. Reference it for any design questions.

3. **Check existing code** — if the file you're editing already exists, read it fully before changing it. Understand the patterns already in use.

## File Ownership

Each task prompt tells you which files to create or modify. **Only touch those files.** Do not modify files outside your assignment — other agents may be working on them in parallel.

## Coding Standards

### Python
- Python 3.8+ (must run on Windows with standard Anaconda)
- Type hints on all function signatures
- `argparse` CLI with `--help` for all scripts
- Use `pathlib.Path` for all file paths (Windows compatibility)
- Use `soundfile` (libsndfile) for reading audio — NOT `wave` module. `soundfile` handles 16-bit, 24-bit, 32-bit float, RF64, BWF, and MP3 natively. The `wave` module only reads 16-bit PCM.
- Logging via `print()` to stderr for errors, stdout for results
- Scripts must be runnable standalone: `python script.py --input X --output Y`
- No external dependencies beyond: `soundfile`, `numpy`, `json`, `argparse`, `pathlib`, `os`, `sys`, `struct`, `math`, `re`, `collections`
- **Never modify files in `Audio_Original/`** — that directory is read-only originals

### JavaScript
- Vanilla JS, ES2020 (no TypeScript, no bundler, no npm)
- IIFE module pattern: `(function() { 'use strict'; ... })();`
- All modules attach to `window.SourceExplorer.modules.<name>`
- Events via `document.dispatchEvent(new CustomEvent('se:event-name', { detail: {...} }))`
- Event listeners via `document.addEventListener('se:event-name', handler)`
- No `var` — use `const` and `let`
- JSDoc comments on public functions
- Error handling: `try/catch` around async operations, log to `console.error('[module-name]', ...)`
- Test with `node --check js/filename.js` (syntax validation only — no runtime testing in Node since these are browser modules)
- wavesurfer.js v7 loaded from CDN (`<script>` tag), accessed via `window.WaveSurfer`
- Plugins: `window.WaveSurfer.Regions` (not `.RegionsPlugin`), `window.WaveSurfer.Timeline`

### HTML
- Single-file `review_tool_dev.html` — all CSS inline in `<style>`, JS modules loaded via `<script src="js/...">`
- wavesurfer v7 from CDN: `https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.esm.js` (or UMD variant)
- No external CSS frameworks

## Audio Format Support

**Critical requirement:** All Python scripts must handle these formats gracefully:
- 16-bit PCM WAV (standard)
- 24-bit PCM WAV
- 32-bit float WAV (format tag 3)
- RF64/BWF (extended WAV for files >4GB)
- MP3

Use `soundfile` for reading. It handles all of the above. Normalize samples to float32 internally when computing peaks or doing analysis. The browser's `<audio>` element handles playback of all these formats natively via MediaElement backend — no transcoding needed for playback.

The `Audio_Working/` directory contains pre-normalized copies (16-bit PCM mono, -16 LUFS) for Whisper STT. But peaks generation and browser playback should work directly on `Audio_Original/` files too.

## Data Schemas

All schemas are defined in `INTERFACES.md`. Key files:
- `source_index.json` — speaker→WAV metadata mapping
- `peaks/<Speaker>.json` — wavesurfer PeaksData v2 format
- `coarse_transcripts/<Speaker>.json` — `{speaker, source_wav, duration_sec, segments[]}`
- `ai_suggestions.json` — pre-computed fuzzy matches with base scores + positional anchors
- Decisions stored in `localStorage` under key `se-decisions`

## Environment

- **Python scripts run on Windows** (`C:\Users\Lucas\Thesis\`) — they need access to audio files on that machine
- **Development (this sandbox) runs on Linux** (WSL2) — code is written here, then deployed to Windows
- **ffmpeg/ffprobe** available on Windows via Chocolatey: `/mnt/c/ProgramData/chocolatey/bin/ffmpeg.exe`
- **Browser target:** Chrome 120+ (primary), Firefox as secondary
- **Local server:** `thesis_server.py` on port 8766 with HTTP range request support

## What NOT To Do

- Do not add npm, webpack, rollup, or any build tooling
- Do not use TypeScript
- Do not add external CSS frameworks (Bootstrap, Tailwind, etc.)
- Do not modify `review_tool.html` (production) — only `review_tool_dev.html` (dev)
- Do not modify files in `Audio_Original/` — ever
- Do not use Python's `wave` module for reading audio — use `soundfile`
- Do not use `var` in JavaScript
- Do not create new CustomEvent names without documenting them in INTERFACES.md
- Do not hardcode Windows paths in JS — all paths are relative URLs served by the local server
- Do not fetch entire WAV files in JS — the MediaElement backend + range requests handle streaming
