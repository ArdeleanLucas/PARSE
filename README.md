# PARSE

**P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer

A browser-based audio review tool for computational historical linguistics. PARSE bridges the gap between raw fieldwork recordings and structured phylogenetic datasets.

## What it does

- Loads full-length fieldwork audio recordings (30–200+ minutes, up to 3GB WAVs)
- Displays coarse transcripts with click-to-seek navigation
- Provides AI-powered suggestions for where target lexical items occur in recordings
- Lets the researcher review, assign, and export audio regions
- Outputs structured data for BEAST 2 phylogenetic analysis

## Architecture

- **Python scripts** — data preparation (source indexing, peaks generation, transcript reformatting, AI suggestion generation, batch re-extraction)
- **JavaScript modules** — browser-based UI (waveform controller, transcript panel, suggestions panel, region manager, spectrogram worker, fullscreen mode)
- **HTML shell** — loads all JS modules, provides panel structure
- **Local HTTP server** — serves audio with range requests for streaming playback

## Getting started

1. Run `python/thesis_server.py` to start the local audio server
2. Open `review_tool_dev.html` in Chrome
3. See `CODING.md` for the full build protocol and `INTERFACES.md` for module contracts

## Project structure

See `CODING.md` for the full directory layout and development protocol.

## License

Private — thesis research tool.
