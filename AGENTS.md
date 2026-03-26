# AGENTS.md — PARSE Project v5.0

## What This Is

PARSE — **P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer

A browser-based phonetic analysis workstation for linguists. Two work modes:
- **Annotate** — per-speaker segmentation, transcription, and annotation
- **Compare** — cross-speaker cognate analysis and phylogenetic data preparation

Replaces Praat, Audacity, ELAN, and spreadsheet workflows with a single integrated tool.

**Tech stack:** Vanilla JS (ES2020, no build step), wavesurfer.js v7, Web Workers, Python 3.8+ backend, HTML served from a local Python HTTP server.

## Project Structure

```
parse/
├── parse.html                      ← Annotate mode (main app)
├── compare.html                    ← Compare mode
├── start_parse.sh                  ← Linux/Mac launcher
├── Start Review Tool.bat           ← Windows launcher
├── LICENSE, README.md, PROJECT_PLAN.md
│
├── js/
│   ├── shared/                     ← shared across both modes
│   │   ├── annotation-store.js     ← localStorage/disk persistence
│   │   ├── project-config.js       ← project.json loader
│   │   ├── tags.js                 ← tagging/filtering system
│   │   ├── audio-player.js         ← shared audio playback from WAV regions
│   │   ├── ai-client.js            ← JS ↔ Python AI server communication
│   │   └── spectrogram-worker.js   ← Web Worker FFT
│   ├── annotate/                   ← Annotate-specific
│   │   ├── parse.js                ← main entry / router
│   │   ├── annotation-panel.js     ← IPA/ortho/concept fields
│   │   ├── region-manager.js       ← waveform region CRUD
│   │   ├── waveform-controller.js  ← WaveSurfer wrapper
│   │   ├── transcript-panel.js     ← coarse transcript display
│   │   ├── suggestions-panel.js    ← AI suggestion rankings
│   │   ├── fullscreen-mode.js      ← fullscreen overlay
│   │   ├── onboarding.js           ← import wizard
│   │   ├── import-export.js        ← CSV/TextGrid/ELAN
│   │   └── video-sync-panel.js     ← video alignment UI
│   └── compare/                    ← Compare-specific
│       ├── compare.js              ← main entry
│       ├── concept-table.js        ← concept × speaker matrix
│       ├── cognate-controls.js     ← accept/split/merge/cycle
│       ├── borrowing-panel.js      ← similarity bars, adjudication
│       ├── speaker-import.js       ← new speaker import wizard
│       └── enrichments.js          ← enrichments layer read/write
│
├── python/
│   ├── server.py                   ← HTTP server + API endpoints
│   ├── peaks.py                    ← waveform peak generation
│   ├── source_index.py             ← source_index.json builder
│   ├── normalize_audio.py          ← ffmpeg normalization
│   ├── textgrid_io.py              ← Praat TextGrid read/write
│   ├── elan_export.py              ← ELAN XML export
│   ├── csv_export.py               ← CSV export
│   ├── video_sync.py               ← FFT cross-correlation
│   ├── video_clip_extract.py       ← video segment extraction
│   ├── batch_reextract.py          ← batch re-extraction
│   ├── reformat_transcripts.py     ← transcript reformatting
│   ├── coarse_transcripts.py       ← coarse transcript generation
│   ├── ai/                         ← AI abstraction layer
│   │   ├── __init__.py
│   │   ├── provider.py             ← abstract AI interface
│   │   ├── stt_pipeline.py         ← faster-whisper full-file STT
│   │   ├── ipa_transcribe.py       ← ortho → IPA conversion
│   │   ├── model_manager.py        ← model download/cache/path resolution
│   │   └── suggestions.py          ← AI concept suggestions
│   └── compare/                    ← Compare pipeline scripts
│       ├── cognate_compute.py      ← LexStat wrapper + enrichments
│       ├── cross_speaker_match.py  ← STT + repetition detect + matching
│       ├── offset_detect.py        ← auto-offset detection
│       └── phonetic_rules.py       ← configurable phonetic variation
│
├── config/                         ← user-editable configuration
│   ├── ai_config.json              ← model paths, API keys, providers
│   ├── phonetic_rules.json         ← phonetic variation rules
│   └── sil_contact_languages.json  ← contact language definitions
│
├── docs/                           ← development documentation
│   ├── CODING.md, INTERFACES.md, ONBOARDING_PLAN.md
│   ├── SPEAKERS.md, BUILD_SESSION.md
│   └── reviews/                    ← code review reports
│
├── review_tool_dev.html            ← LEGACY (DO NOT TOUCH)
└── tasks/
    └── lessons.md
```

## Before You Write Code

1. **Read `CODING.md`** — build protocol, sub-agent rules, build waves, execution order
2. **Read `INTERFACES.md`** — shared types, events, function signatures, module init pattern
3. **Read `PROJECT_PLAN.md`** — full architecture spec (v5.0), all schemas and design decisions
4. **Check existing code** — if the file you're editing already exists, read it fully first

## File Ownership

Each task prompt tells you which files to create or modify. **Only touch those files.** Do not modify files outside your assignment — other agents may be working on them in parallel.

## Coding Standards

### Python
- Python 3.8+ (must run on Windows with standard Anaconda)
- Type hints on all function signatures
- `argparse` CLI with `--help` for all scripts
- Use `pathlib.Path` for all file paths (Windows compatibility)
- Use `soundfile` (libsndfile) for reading audio — NOT `wave` module
- Logging via `print()` to stderr for errors, stdout for results
- Scripts must be runnable standalone: `python script.py --input X --output Y`
- **Never modify files in `Audio_Original/`** — that directory is read-only

### JavaScript
- Vanilla JS, ES2020 (no TypeScript, no bundler, no npm)
- IIFE module pattern: `(function() { 'use strict'; ... })();`
- All modules attach to `window.PARSE.modules.<name>`
- Events via `document.dispatchEvent(new CustomEvent('parse:event-name', { detail: {...} }))`
- No `var` — use `const` and `let`
- JSDoc comments on public functions
- wavesurfer.js v7 loaded from CDN, accessed via `window.WaveSurfer`

### HTML
- `parse.html` — Annotate mode entry point
- `compare.html` — Compare mode entry point
- All CSS inline in `<style>`, JS modules loaded via `<script src="js/...">`
- No external CSS frameworks

## Audio Format Support

All Python scripts must handle: 16-bit PCM, 24-bit PCM, 32-bit float WAV, RF64/BWF, MP3.
Use `soundfile` for reading. Normalize to float32 internally.

## What NOT To Do

- Do not add npm, webpack, rollup, or any build tooling
- Do not use TypeScript
- Do not add external CSS frameworks
- Do not modify `review_tool_dev.html` (legacy, sacred)
- Do not modify files in `Audio_Original/`
- Do not use Python's `wave` module — use `soundfile`
- Do not use `var` in JavaScript
- Do not hardcode Windows paths in JS — all paths are relative URLs
- Do not fetch entire WAV files in JS — MediaElement + range requests handle streaming
