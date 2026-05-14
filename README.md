# PARSE — Phonetic Analysis & Review Source Explorer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/ArdeleanLucas/PARSE/actions/workflows/ci.yml/badge.svg)](https://github.com/ArdeleanLucas/PARSE/actions/workflows/ci.yml)
![Python 3.10-3.12](https://img.shields.io/badge/Python-3.10--3.12-blue)
![Node 18%2B](https://img.shields.io/badge/Node-18%2B-339933)

**Browser-based workstation for linguistic fieldwork and comparative analysis.**
Transcribe recordings, keep timestamps trustworthy, compare forms across speakers, track borrowing evidence, and export clean datasets for downstream analysis.

<p align="center">
  <img src="docs/pr-assets/dogfood-fix-153-annotate-stable.png" alt="Annotate mode in the unified PARSE React shell" width="32%" />
  <img src="docs/pr-assets/pr76-compare-table.png" alt="Compare mode concept by speaker matrix" width="32%" />
</p>

> **Status**: Active research software. Thesis-critical features land frequently and file contracts still evolve.

## The Problem
Fieldwork data often ends up split across audio editors, spreadsheets, scripts, and notes. That makes it easy to lose track of where a form came from, which timestamp was reviewed, and which comparison decisions are final. PARSE keeps the audio, annotations, comparison table, notes, borrowing evidence, and exports in one workspace.

## Who It's For
Fieldwork linguists, comparative and historical linguists, and language-documentation teams working with long recordings, wordlists, and multiple speakers or varieties.

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
- **Annotate recordings** — listen to long recordings, review each word or phrase, correct IPA and orthography, and keep the timestamps tied to the audio.
- **Compare speakers** — see the same word or concept across speakers, review variants, and make comparison decisions without rewriting the original data.
- **Find words quickly** — search across recordings when a target word is buried in hours of audio.
- **Track notes and tags** — mark forms as confirmed, uncertain, borrowed, dialect-specific, or anything else useful for analysis.
- **Check borrowing evidence** — bring in contact-language comparison forms with source information and citations.
- **Export clean datasets** — produce LingPy TSV and NEXUS files for downstream comparative and phylogenetic work.
- **Automate repetitive work** — use the local API and MCP server when AI agents or scripts need to import speakers, run jobs, or prepare exports.

## Quick Start
```bash
git clone https://github.com/ArdeleanLucas/PARSE.git
cd PARSE
npm install

python3 -m venv .venv
source .venv/bin/activate
pip install -r python/requirements.txt

./scripts/parse-run.sh
```

Runs on macOS, Linux, and WSL. A GPU is optional; CPU-only works. Open **Annotate** at http://localhost:5173/ and **Compare** at http://localhost:5173/compare.

For environment notes, GPU configuration, workspace layout, and troubleshooting, see [Getting Started](docs/getting-started.md). Adobe Audition marker CSV onboarding is documented in [Audition CSV speaker import](docs/runtime/audition-csv-import.md). For real fieldwork, point PARSE at a workspace root outside the git checkout.

## Annotate
- Review long recordings with a zoomable waveform
- Keep IPA, spelling, meaning, and speaker information together
- Run transcription and alignment help when you need it, then review the result yourself
- Check and correct word boundaries when timing drifts
- Undo mistakes, retime clips, add notes, tag forms, and search for hard-to-find words

Full details in the [User Guide](docs/user-guide.md).

## Compare
- Side-by-side table for comparing the same word or concept across speakers
- Review multiple variants for a speaker and choose the form to use for comparison
- Merge, split, or duplicate concept rows for analysis while preserving the underlying source data
- Survey/source labels and color cues for complex elicitation sets
- Tools for grouping related forms and revising those groups as evidence changes
- Borrowing review with contact-language evidence and citation cards
- Shared tags, speaker flags, and export-ready comparison data
- Export to LingPy-compatible TSV and NEXUS for downstream phylogenetic analysis

Full details in the [User Guide](docs/user-guide.md).

## Use with Claude, Codex, and other AI agents
PARSE can also be driven by scripts and AI agents. That means repetitive tasks — importing speakers, running support jobs, checking annotations, and preparing exports — do not have to happen only through the browser. The in-app assistant uses the same bounded PARSE tool layer.

For setup and the full automation reference, see the [MCP Guide](docs/mcp-guide.md) and [Getting Started with External Agents](docs/getting-started-external-agents.md).

## Research Workflow
1. Import or open a speaker recording.
2. Review the audio, text, IPA, and timestamps in Annotate.
3. Compare the same word or concept across speakers.
4. Check borrowing evidence when contact influence matters.
5. Export LingPy TSV or NEXUS for downstream analysis.

For the long-form walkthrough, see the [User Guide](docs/user-guide.md).

## Documentation
- [Getting Started](docs/getting-started.md) — installation, launch paths, requirements, GPU notes, and troubleshooting.
- [Environment variables](docs/environment-variables.md) — ports, workspace roots, long-file chunking, subprocess timeouts, and device overrides.
- [Getting Started with External Agents](docs/getting-started-external-agents.md) — connecting Claude, Codex, and other agents to PARSE.
- [User Guide](docs/user-guide.md) — detailed Annotate and Compare workflows, CLEF usage, lexical anchoring, and workspace hydration.
- [AI Integration](docs/ai-integration.md) — providers, model configuration, the chat tool surface, and workflow macros.
- [MCP Guide](docs/mcp-guide.md) — automation setup, authentication, tool catalog, and `parse-mcp` usage.
- [MCP Schema](docs/mcp-schema.md) — low-level MCP reference for developers.
- [Agent skill index](docs/agent-skills/parse-mcp-tools/skills/index.md) — categorized per-tool skill docs (annotation, comparison, export, project, advanced) for agents driving PARSE via MCP.
- [API Reference](docs/api-reference.md) — HTTP automation reference and examples.
- [Architecture](docs/architecture.md) — system design, data model, and runtime responsibilities.
- [Audition CSV speaker import](docs/runtime/audition-csv-import.md) — marker-export onboarding contract for Adobe Audition CSV/TSV files.
- [Cross-survey concept linking plan](docs/cross-survey-concept-linking-plan.md) — pre-research spec for linking overlapping KLQ/JBIL survey concepts.
- [Developer Guide](docs/developer-guide.md) — local development flow, extension points, and contributor rules.
- [Research Context](docs/research-context.md) — thesis framing, citation guidance, and research-software context.
- [Models](docs/models/README.md) — model reference notes for speech and transcription support.
- [MC-384 compute release notes](docs/release-notes/mc-384-compute-architecture.md) — long-file chunking, subprocess isolation, and device resolver changes.

## Research & Citation
PARSE was developed for a **Southern Kurdish dialect phylogenetics thesis** at the **University of Bamberg**, but the workstation is general-purpose and applies to any fieldwork-driven comparative linguistics workflow involving long recordings, concept-based wordlists, cognate review, borrowing adjudication, and downstream analysis in **LingPy**, **LexStat**, or **BEAST 2**. If you use PARSE in academic work, cite it as research software via [`CITATION.cff`](CITATION.cff) or GitHub's **Cite this repository** UI.

> Ardelean, L. M. (2026). *PARSE: Phonetic Analysis & Review Source Explorer* [Computer software]. University of Bamberg. https://github.com/ArdeleanLucas/PARSE

See [Research Context](docs/research-context.md) for full citation guidance and research framing.

## License
[MIT License](LICENSE)
