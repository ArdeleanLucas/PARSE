# PARSE

**P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer

PARSE is a browser-based tool for linguists who need to review, annotate, and verify phonetic field recordings. It was developed in the context of Southern Kurdish dialect phylogenetics research, but the workflow is general-purpose: if you have long-form WAV recordings plus timestamp or cue data, PARSE gives you a lightweight environment for segment-level review without requiring a heavy desktop annotation stack.

Repository: [`TarahAssistant/PARSE`](https://github.com/TarahAssistant/PARSE)

## What PARSE is for

Field linguistics workflows often involve moving back and forth between audio editors, spreadsheets, transcripts, and annotation software. PARSE is designed to bring that review loop into a single browser-based workspace so a researcher can:

- inspect long recordings visually,
- jump to candidate segments quickly,
- correct timestamp boundaries by hand,
- annotate each segment with phonetic and orthographic forms, and
- preserve review progress locally while building a cleaner dataset for downstream analysis.

The initial target use case is a Southern Kurdish dialect comparison thesis, but the tool is suitable for any linguist working with:

- WAV recordings,
- cue or timestamp files,
- segment-level transcription or gloss data, and
- multi-speaker comparison workflows.

## Core features

- **Waveform viewer powered by WaveSurfer.js** for browsing long recordings in the browser
- **Segment-level annotation** with both **IPA** and **orthographic/script** fields
- **Draggable timestamp regions** for adjusting segment start and end boundaries
- **Auto-play segment review** for fast verification of clipped regions
- **Import wizard** for bringing in recordings plus **CSV/TextGrid** cue data
- **Multi-speaker support** for comparative review across speakers or dialects
- **localStorage persistence** so browser-side annotation progress survives page reloads
- **Lightweight deployment**: a single self-contained HTML app, no build step, no frontend framework

## Technology overview

PARSE is intentionally simple to run and inspect:

- **Frontend:** a single self-contained `parse.html` file
- **Language:** vanilla JavaScript, HTML, and CSS
- **Waveform library:** WaveSurfer.js loaded from CDN
- **Build tooling:** none
- **Serving model:** any HTTP server with **Range request** support for long-audio playback
- **Persistence:** browser-local storage for review state
- **Supporting pipeline:** Python utilities in `python/` and `scripts/` for preparing datasets

This makes the project easy to clone, serve locally, and adapt for specific research datasets.

## Quickstart

### Requirements

- Python 3
- A modern browser
- An HTTP server that supports **Range requests**

> Do **not** open `parse.html` directly with `file://`. Long-form audio playback works best when the app is served over HTTP.

From the project root:

```bash
python3 serve.py 8766
```

Then open:

```text
http://localhost:8766/parse.html
```

If your local checkout is still using the current helper scripts in this repository, the existing equivalents are `python3 python/thesis_server.py` or `./start_parse.sh`.

## Typical workflow

1. Start the local HTTP server.
2. Open `parse.html` in the browser.
3. Import one or more WAV recordings.
4. Import a cue file or timestamp file (for example CSV or TextGrid).
5. Review proposed segments in the waveform view.
6. Adjust region boundaries by dragging timestamps.
7. Enter or correct IPA and orthographic annotations.
8. Repeat across speakers while retaining progress locally in the browser.

## Data pipeline

In addition to the browser app, the repository includes Python-based data preparation utilities for building the review dataset:

- **Audio normalization** for consistent working copies
- **Waveform peak generation** for fast browser rendering
- **Coarse transcript generation** for navigable text-aligned review
- **AI suggestion generation** for candidate segment discovery
- **Auxiliary scripts** for orthographic/transcription processing

Relevant directories:

- `python/` — normalization, transcript prep, peaks generation, AI suggestions, import/export helpers
- `scripts/` — auxiliary processing scripts used during dataset preparation

## Project structure

```text
PARSE/
├── parse.html              # Main self-contained browser app
├── python/                 # Data prep and server-side helper scripts
│   ├── normalize_audio.py
│   ├── build_coarse_transcripts.py
│   ├── generate_peaks.py
│   ├── generate_ai_suggestions.py
│   └── ...
├── scripts/                # Auxiliary processing scripts
├── js/                     # Modular/dev JavaScript components
├── ONBOARDING_PLAN.md      # Import and onboarding design notes
├── PROJECT_PLAN.md         # Project architecture and roadmap
├── CODING.md               # Build and implementation protocol
├── review_tool_dev.html    # Alternate/dev shell
└── LICENSE
```

## Research context

PARSE was built for **Southern Kurdish dialect phylogenetics** work, where the practical problem is not just transcription, but reliable recovery of comparable lexical items from long field recordings across many speakers.

That said, the design is intentionally broader than a single thesis. Any researcher with:

- field recordings,
- segment timestamps,
- cue exports from tools like Praat or Adobe Audition, or
- speaker-by-speaker review needs

can adapt PARSE as a lightweight annotation and verification environment.

## Status

PARSE is an active research software project. The current repository contains both the main single-file browser application and supporting scripts for a broader annotation, import/export, and AI-assisted review pipeline.

## License

MIT
