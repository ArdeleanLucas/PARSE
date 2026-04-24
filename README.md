# PARSE — Phonetic Analysis & Review Source Explorer

**Browser-based dual-mode workstation for linguistic fieldwork.**
Annotate per-speaker recordings with tiered IPA/orthography, then compare across speakers for cognate adjudication, borrowing detection, and export-ready historical-linguistic datasets.

<!-- TODO: Add a hero GIF here showing the unified React shell: Annotate waveform + tiers, Compare concept matrix + CLEF panel, and the AI chat dock. A wide GitHub-friendly GIF or screenshot strip would work well. -->
<!-- TODO: Add 2-3 static screenshots below the hero once the current UI settles: Annotate mode, Compare mode, and Lexeme Search / CLEF panels. -->

> **Status**: Active development. Thesis-critical features are landing frequently, interfaces and file contracts are still evolving, and PARSE should currently be treated as research software rather than beta software.

## ✨ What Makes PARSE Different

- **Dual-mode unified React shell** for annotation and comparison in one workspace
- **Fieldwork-first design** for long recordings, uneven metadata, and iterative review
- **AI-native workflow surface** with a built-in chat assistant powered by **47 PARSE-specific tools**
- **Full MCP server mode** exposing a curated **29-tool** subset for external agents and automation
- **CLEF — Contact Lexeme Explorer Feature** for borrowing adjudication via a 10-provider contact-language lookup stack
- **Lexical Anchor Alignment System** for locating repeated lexical items across long recordings and across speakers
- **Export pipeline** for LingPy TSV and NEXUS outputs used in downstream comparative workflows

## 🚀 Quick Start

```bash
git clone https://github.com/ArdeleanLucas/PARSE.git
cd PARSE
./scripts/parse-run.sh
```

On a fresh clone, you will usually also want to:

- run `npm install` once
- copy `config/ai_config.example.json` to `config/ai_config.json`
- review your local model/provider settings before serious speech work

Open:

- **Annotate**: http://localhost:5173/
- **Compare**: http://localhost:5173/compare

For full requirements, workspace setup, GPU/model configuration, and troubleshooting, see [Getting Started](docs/getting-started.md).

## 🛠️ Core Concepts

### Annotate Mode (`/`)

**Annotate** is the per-speaker segmentation and transcription workstation.

It combines:

- **WaveSurfer 7** waveform review for long recordings
- **Four annotation tiers**: IPA, orthography, concept, and speaker
- **Stacked transcription lanes** for STT, IPA, and ORTH with synchronized horizontal scrolling
- **Audio normalization**, **speaker-level STT**, **ORTH transcription**, and **acoustic IPA fill** jobs
- **Tier 2 forced alignment** with wav2vec2 for tighter word-level boundaries
- **Draggable timestamp correction** and clip-bounded playback for manual review
- **Batch transcription** with preflight checks and rerun-failed support
- **Timestamp-offset detection/apply workflows** for constant CSV↔audio misalignment
- **Search & anchor lexeme** tooling built on the Lexical Anchor Alignment System
- **Shared tags** and the in-session **AI chat dock**

Annotate mode is where PARSE turns long, messy field recordings into time-aligned annotation data without forcing the user into disconnected tools.

### Compare Mode (`/compare`)

**Compare** is the cross-speaker review workspace.

It provides:

- A **concept × speaker matrix** for side-by-side lexical comparison
- Cognate controls for **accept**, **split**, **merge**, and **cycle**
- Per-row editing, speaker flags, and secondary actions for review work
- **Borrowing adjudication** aided by contact-language similarity evidence
- **Enrichment overlays** for computed comparative metadata
- The **CLEF** panel for multi-source contact-language lookup
- The same shared **tag system** used in Annotate mode
- Export to **LingPy-compatible TSV** and **NEXUS** for downstream phylogenetic analysis

Together, Annotate and Compare cover the full movement from speaker-specific audio review to cross-speaker historical analysis.

### AI Workflow Assistant

PARSE includes a built-in **domain-specific chat dock** powered by the configured LLM provider.

This assistant is not a generic chatbot. It operates through `ParseChatTools` and can inspect project state, guide annotation workflows, trigger jobs, help interpret comparative results, and support onboarding, export, and troubleshooting inside the same workstation.

Supported LLM backends currently include **xAI (Grok)** and **OpenAI**. Local speech and alignment work is handled separately through faster-whisper, Razhan, Silero VAD, and wav2vec2.

### MCP Server Mode

PARSE can also run as an **MCP (Model Context Protocol) server**.

That means external agent clients such as Claude Code, Cursor, Cline, Hermes, Windsurf, Codex, or other MCP-capable tools can call a curated subset of PARSE functions programmatically, without going through the browser UI.

The MCP adapter currently exposes **29 tools** drawn from the broader in-app PARSE tool surface.

## 📚 Documentation

- [Getting Started](docs/getting-started.md) — installation, launch paths, requirements, environment variables, `ai_config.json`, GPU notes, and troubleshooting
- [User Guide](docs/user-guide.md) — detailed Annotate/Compare workflows, CLEF usage, Lexical Anchor Alignment, and workspace hydration
- [AI Integration](docs/ai-integration.md) — provider routing, model roles, configuration, external dependencies, and the full 47-tool chat surface
- [API Reference](docs/api-reference.md) — HTTP endpoints, compute routes, examples, and the full 29-tool MCP surface
- [Architecture](docs/architecture.md) — unified shell, backend/data design, Lexical Anchor Alignment scoring, and CLEF provider registry
- [Developer Guide](docs/developer-guide.md) — project structure, tech stack, local development flow, and extension points for chat tools, MCP tools, and endpoints
- [Research Context](docs/research-context.md) — thesis background, citation guidance, and research-software framing

If you are new to PARSE, start with **[Getting Started](docs/getting-started.md)** and then move to the **[User Guide](docs/user-guide.md)**.

## Research Workflow in One Pass

PARSE is designed around a real fieldwork sequence rather than a toy demo sequence:

1. **Load or import one speaker** into the active workspace
2. **Normalize audio** and inspect the waveform
3. **Run STT / ORTH / IPA support jobs** to seed time-aligned review
4. **Correct timestamps and confirm segments** in Annotate mode
5. **Search and anchor difficult lexemes** across long recordings
6. **Compare the concept set across speakers** in the matrix view
7. **Use CLEF evidence** when a borrowing analysis needs external lexical context
8. **Export LingPy TSV or NEXUS** for downstream comparative and phylogenetic analysis

The guiding principle is simple: timestamps are central, human review stays explicit, and automation should make linguistic judgment faster rather than opaque.

## Core Runtime Notes

A few practical details matter up front:

- The active frontend is **React + Vite** in `src/`
- The Python backend in `python/server.py` powers AI routes and can also serve the built frontend
- The preferred development URLs are:
  - `http://localhost:5173/`
  - `http://localhost:5173/compare`
- After `npm run build`, the Python server can serve the built UI at:
  - `http://localhost:8766/`
  - `http://localhost:8766/compare`
- `config/ai_config.json` is machine-local and gitignored; start from `config/ai_config.example.json`
- For real fieldwork usage, PARSE is intended to run against a **workspace root outside the git checkout**
- PARSE is still in active development; the repository has explicitly treated full browser regression and export verification as ongoing validation work rather than fully settled release guarantees

Those details are expanded in [Getting Started](docs/getting-started.md) and [Developer Guide](docs/developer-guide.md).

## 🔬 Research & Citation

PARSE was developed for a **Southern Kurdish dialect phylogenetics thesis** at the **University of Bamberg**.

The working dataset and workflow are oriented toward:

- long elicitation recordings
- concept-based wordlists
- multiple speakers of closely related varieties
- cognate review and borrowing adjudication
- downstream comparative analysis in **LingPy**, **LexStat**, and **BEAST 2**

If you use PARSE in academic work, please cite it as **research software** and use the repository's [`CITATION.cff`](CITATION.cff) file or GitHub's **Cite this repository** UI.

Suggested citation:

> Ardelean, L. M. (2026). *PARSE: Phonetic Analysis & Review Source Explorer* [Computer software]. University of Bamberg. https://github.com/ArdeleanLucas/PARSE

See [Research Context](docs/research-context.md) for full citation guidance and research framing.

## License

MIT License
