# PARSE — Phonetic Analysis & Review Source Explorer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/ArdeleanLucas/PARSE/actions/workflows/ci.yml/badge.svg)](https://github.com/ArdeleanLucas/PARSE/actions/workflows/ci.yml)
![Python 3.10-3.12](https://img.shields.io/badge/Python-3.10--3.12-blue)
![Node 18%2B](https://img.shields.io/badge/Node-18%2B-339933)

**Browser-based workstation for linguistic fieldwork and comparative analysis.**
Annotate recordings with tiered IPA and orthography, then compare across speakers to adjudicate cognates, flag borrowings, and export datasets for downstream phylogenetic work.

<p align="center">
  <img src="docs/pr-assets/dogfood-fix-153-annotate-stable.png" alt="Annotate mode in the unified PARSE React shell" width="32%" />
  <img src="docs/pr-assets/pr76-compare-table.png" alt="Compare mode concept by speaker matrix" width="32%" />
</p>

> **Status**: Active research software. Thesis-critical features land frequently and file contracts still evolve.

## The Problem
Linguistic fieldwork, cognate adjudication, and phylogenetic export usually sprawl across disconnected tools. That fragmentation breaks timestamp fidelity, duplicates cleanup work, and makes audit trails brittle. PARSE keeps transcription, comparison, borrowing evidence, and export in one workspace.

## Who It's For
Fieldwork linguists, comparative and historical linguists, and language-documentation teams working with long elicitation recordings, concept-based wordlists, and multiple speakers of closely related varieties.

## Table of Contents
- [What PARSE Does](#what-parse-does)
- [Quick Start](#quick-start)
- [Annotate](#annotate)
- [Compare](#compare)
- [Use with Claude, Codex, and other AI agents](#use-with-claude-codex-and-other-ai-agents)
- [Documentation](#documentation)
- [Research & Citation](#research--citation)
- [License](#license)

## What PARSE Does
- **Annotate** — review long recordings clip by clip with tiered IPA, orthography, concept, and speaker layers. Run STT, forced alignment, and acoustic IPA fill on whole speakers or scoped to specific concepts.
- **Compare** — line up every speaker's realization of a concept side by side, accept/split/merge cognate sets, and review A/B/C variants per speaker.
- **CLEF (Contact Lexeme Explorer)** — pull borrowing evidence from a 10-provider contact-language lookup stack with citations, provenance, and source reports.
- **Word finder** — lexical anchor search across speakers and concepts to locate forms quickly inside large corpora.
- **Advanced tagging** — shared tag vocabulary across speakers and concepts for analytical slicing (loanwords, uncertain forms, dialect features, anything you want to track).
- **Phonetic similarity & cognate review** — similarity columns against the primary language and contact languages drive cognate adjudication directly in the matrix.
- **Export for BEAST 2** — produce LingPy-compatible TSV and NEXUS files that feed LexStat and BEAST 2 phylogenetic pipelines without leaving the workstation.
- **AI assistant + MCP** — an in-app chat assistant and a full MCP server let Claude Code, Codex, Cursor, Cline, Hermes, and Windsurf drive PARSE directly.

## Quick Start
```bash
git clone https://github.com/ArdeleanLucas/PARSE.git
cd PARSE
npm install

# Python 3.10-3.12 required (python/server.py still imports cgi, removed in 3.13).
# Pick one:
python3 -m venv .venv && source .venv/bin/activate && pip install -r python/requirements.txt
# OR on PEP 668 distros (Debian/Ubuntu) without a venv:
# pip install --user --break-system-packages -r python/requirements.txt

./scripts/parse-run.sh
```

Runs on macOS / Linux / WSL. CUDA 12.x optional for faster STT and forced alignment; CPU-only also works. Open **Annotate** at http://localhost:5173/ and **Compare** at http://localhost:5173/compare.

For environment notes, GPU configuration, workspace layout, and troubleshooting, see [Getting Started](docs/getting-started.md). Adobe Audition marker CSV onboarding is documented in [Audition CSV speaker import](docs/runtime/audition-csv-import.md). For real fieldwork, point PARSE at a workspace root outside the git checkout.

## Annotate
- Clip-bounded WaveSurfer review for long recordings
- Four annotation tiers: IPA, orthography, concept, and speaker
- Whole-speaker or concept-scoped pipeline reruns for STT, ORTH, IPA, and forced alignment
- Boundary refinement with Tier 1 / Tier 2 overlays for spotting drift
- Per-speaker undo/redo, draggable timestamp correction, waveform quick retime
- Per-lexeme notes, lexical anchor search, and shared tags inside the workstation

Full details in the [User Guide](docs/user-guide.md).

## Compare
- Concept × speaker matrix for side-by-side lexical comparison
- A/B/C realization review with canonical per-speaker picks
- Manual concept merge/unmerge overrides for comparative review
- Cognate controls for accept, split, merge, and cycle
- Borrowing adjudication with contact-language similarity evidence
- CLEF panel with provenance-aware source reporting and citation cards
- Shared tags, speaker flags, and enrichment overlays
- Export to LingPy-compatible TSV and NEXUS for downstream phylogenetic analysis

Full details in the [User Guide](docs/user-guide.md).

## Use with Claude, Codex, and other AI agents
PARSE ships with an MCP server so external AI agents can drive the workstation — onboarding speakers, running pipelines, querying annotations, and triggering exports without going through the browser. There's also an in-app chat assistant powered by `ParseChatTools` for the same surface inside PARSE itself.

Four entry points are available:
- **HTTP API** at `http://localhost:8766` (OpenAPI at `/docs`, `/redoc`, `/openapi.json`)
- **WebSocket job stream** at `ws://localhost:8767/ws/jobs/{jobId}`
- **HTTP MCP bridge** on the same server
- **stdio MCP adapter** at `python/adapters/mcp_adapter.py`

Setup, authentication, and the full tool catalog live in the [MCP Guide](docs/mcp-guide.md) and [Getting Started with External Agents](docs/getting-started-external-agents.md).

## Research Workflow
1. Annotate one speaker — normalize audio, run STT/ORTH/IPA support jobs, and confirm timestamps after PARSE reloads the speaker annotation from disk.
2. Compare concepts across speakers in matrix view and resolve cognates.
3. Run CLEF when borrowing analysis needs contact-language evidence or reference-form population.
4. Export LingPy TSV or NEXUS for downstream comparative and phylogenetic analysis.

For the long-form walkthrough, see the [User Guide](docs/user-guide.md).

## Documentation
- [Getting Started](docs/getting-started.md) — installation, launch paths, requirements, environment variables, GPU notes, and troubleshooting.
- [Getting Started with External Agents](docs/getting-started-external-agents.md) — MCP stdio setup, HTTP bridge entry points, environment conventions, and agent-facing examples.
- [User Guide](docs/user-guide.md) — detailed Annotate and Compare workflows, CLEF usage, lexical anchoring, and workspace hydration.
- [AI Integration](docs/ai-integration.md) — providers, model configuration, the chat tool surface, and workflow macros.
- [MCP Guide](docs/mcp-guide.md) — the four external surfaces, authentication model, tool catalog, and `parse-mcp` usage.
- [MCP Schema](docs/mcp-schema.md) — raw schema/auth reference for the MCP surface.
- [API Reference](docs/api-reference.md) — HTTP endpoints, job observability, OpenAPI docs, and examples.
- [Architecture](docs/architecture.md) — system design, data model, and runtime responsibilities.
- [Audition CSV speaker import](docs/runtime/audition-csv-import.md) — marker-export onboarding contract for Adobe Audition CSV/TSV files.
- [Developer Guide](docs/developer-guide.md) — local development flow, extension points, and contributor rules.
- [Research Context](docs/research-context.md) — thesis framing, citation guidance, and research-software context.

## Research & Citation
PARSE was developed for a **Southern Kurdish dialect phylogenetics thesis** at the **University of Bamberg**, but the workstation is general-purpose and applies to any fieldwork-driven comparative linguistics workflow involving long recordings, concept-based wordlists, cognate review, borrowing adjudication, and downstream analysis in **LingPy**, **LexStat**, or **BEAST 2**. If you use PARSE in academic work, cite it as research software via [`CITATION.cff`](CITATION.cff) or GitHub's **Cite this repository** UI.

> Ardelean, L. M. (2026). *PARSE: Phonetic Analysis & Review Source Explorer* [Computer software]. University of Bamberg. https://github.com/ArdeleanLucas/PARSE

See [Research Context](docs/research-context.md) for full citation guidance and research framing.

## License
[MIT License](LICENSE)
