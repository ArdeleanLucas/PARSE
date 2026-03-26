# PARSE

**P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer  
Browser-based dual-mode workstation for linguistic fieldwork and cross-speaker comparison.  
Repository: [TarahAssistant/PARSE](https://github.com/TarahAssistant/PARSE)

## What is PARSE

PARSE is a browser-based research tool for linguists who work with long field recordings, concept-based wordlists, and multi-speaker datasets. It combines audio navigation, annotation, and comparative analysis in one workspace, so researchers can move from raw recordings to analysis-ready linguistic data without jumping between several disconnected tools.

Version 5.0 introduces a dual-mode architecture: **Annotate** for per-speaker segmentation and transcription, and **Compare** for cross-speaker cognate review and borrowing adjudication. Both modes run in the browser, and both are built around precise time-aligned annotations.

No installation of frontend tooling is required for normal use. Run the local Python server, open the interface in a browser, and start working. PARSE is designed for real fieldwork constraints (large recordings, mixed metadata quality, iterative review), and should be treated as **research software** rather than production software.

## Modes

### Annotate mode

Annotate mode is the per-speaker segmentation workstation.

- Waveform review with WaveSurfer 7 for long recordings.
- Four core tiers: **IPA**, **orthography**, **concept**, and **speaker**.
- AI-assisted STT support for locating candidate segments.
- Draggable timestamp regions for boundary correction.
- Fast segment playback and iterative annotation refinement.

### Compare mode

Compare mode is the cross-speaker analysis workspace for cognates and phylogenetic preparation.

- Concept x speaker comparison table for side-by-side lexical review.
- Cognate controls: **accept**, **split**, **merge**, and **cycle**.
- Borrowing adjudication aided by contact-language similarity signals.
- Enrichments layer for computed analysis metadata.
- Tag system for scoped filtering and selective analysis.
- Export to LingPy-compatible TSV for downstream pipelines.

## AI Provider System

PARSE v5.0 supports four AI backends:

- **Local faster-whisper** (GPU-capable local processing)
- **OpenAI Whisper API**
- **xAI / Grok**
- **Ollama**

Provider selection is feature-specific. You can route **STT**, **IPA transcription**, and **LLM tasks** to different providers in the same project. Configuration lives in `config/ai_config.json`.

## Quick Start

From the repository root:

```bash
python3 python/server.py
```

The server runs on port `8766` by default.

Open either mode in your browser:

- Annotate mode: `http://localhost:8766/parse.html`
- Compare mode: `http://localhost:8766/compare.html`

## Project Structure

```text
parse.html          -- Annotate mode
compare.html        -- Compare mode
js/annotate/        -- Annotate JS modules
js/compare/         -- Compare JS modules
js/shared/          -- Shared modules (tags, audio, AI client)
python/ai/          -- AI provider layer
python/compare/     -- Compare pipeline (cognates, matching, offsets)
config/             -- Configuration files
docs/               -- Documentation
```

## Data Architecture

PARSE uses a hybrid data model:

- **Live annotations**: per-speaker JSON annotation files (primary source of truth).
- **Computed enrichments**: `parse-enrichments.json`, generated for comparative analysis overlays.

The enrichments layer stores computed structures such as cognate sets, similarity scores, and borrowing decisions, while preserving manual adjudications.

## Technology

- Vanilla JavaScript (no build step)
- Python 3.8+
- WaveSurfer 7 (CDN)
- No npm/node runtime requirement for normal use

## Context

PARSE was built for a Southern Kurdish dialect phylogenetics thesis at the University of Bamberg. The working dataset includes 11 speakers and an 85-item wordlist, with downstream Bayesian phylogenetic analysis in BEAST 2.

## License

MIT
