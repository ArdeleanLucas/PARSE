# PARSE

**P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer  
Browser-based dual-mode workstation for linguistic fieldwork and cross-speaker comparison.  
Repository: [ArdeleanLucas/PARSE](https://github.com/ArdeleanLucas/PARSE)

## What is PARSE

PARSE is a browser-based research tool for linguists working with long field recordings, concept-based wordlists, and multi-speaker datasets. It combines audio navigation, annotation, and comparative analysis in one workspace, so researchers can move from raw recordings to analysis-ready linguistic data without switching between disconnected tools.

Phase 5 of the project introduces a dual-mode architecture: **Annotate** for per-speaker segmentation and transcription, and **Compare** for cross-speaker cognate review and borrowing adjudication. Both modes are built around precise time-aligned annotations with a unified tag system shared across workflows.

PARSE is currently in a **hybrid transition**. The active frontend architecture is **React + Vite** (`index.html` + `src/`), with the preferred development routes at `http://localhost:5173/` (Annotate) and `http://localhost:5173/compare` (Compare). Legacy `parse.html` and `compare.html` pages still remain on `main` as temporary fallback entrypoints served by the Python backend on port `8766` while C5/C6 validation is completed ahead of C7 cleanup.

The Python backend continues to power AI/API routes for both architectures. PARSE is designed for real fieldwork constraints — large recordings, mixed metadata quality, iterative review — and should be treated as **research software** rather than production software.

---

## Modes

### Annotate mode (React route `/`, legacy fallback `parse.html`)

Per-speaker segmentation and transcription workstation.

- Waveform review with WaveSurfer 7 for long recordings
- Four annotation tiers: **IPA**, **orthography**, **concept**, and **speaker**
- AI-assisted STT for locating candidate segments in full recordings
- Draggable timestamp regions for boundary correction
- Fast segment playback and iterative refinement
- AI chat dock for in-session analysis assistance
- Tag and filter concepts for selective annotation

### Compare mode (React route `/compare`, legacy fallback `compare.html`)

Cross-speaker analysis workspace for cognates and phylogenetic data preparation.

- Concept × speaker matrix for side-by-side lexical review
- Cognate controls: **accept**, **split**, **merge**, and **cycle**
- Borrowing adjudication aided by contact-language similarity signals
- Enrichments overlay for computed analysis metadata
- Unified tag system (shared with Annotate mode) for scoped filtering
- Export to LingPy-compatible TSV for downstream pipelines (LexStat, BEAST 2)

### Current entrypoint status

- **Preferred development UI:** `http://localhost:5173/` and `http://localhost:5173/compare`
- **Legacy fallback UI:** `http://localhost:8766/parse.html` and `http://localhost:8766/compare.html`
- **Cleanup gate:** legacy fallback pages remain only until C5/C6 are manually cleared and C7 removes them

---

## AI Provider System

PARSE (Phase 5) supports multiple AI backends, routed per task type:

| Task | Supported providers |
|---|---|
| STT (speech-to-text) | faster-whisper (local, GPU), OpenAI Whisper API |
| IPA transcription | wav2vec2 (local), epitran (fallback) |
| LLM / chat | xAI (Grok), OpenAI, Ollama |

Provider selection is feature-specific — STT, IPA, and LLM tasks can each route to a different backend in the same project. Configuration lives in `config/ai_config.json`.

**GPU requirement:** PARSE is designed for CUDA inference. The recommended local STT setup is faster-whisper with `device=cuda, compute_type=float16`. CPU inference is not supported for production use.

### Models

| Model | Task | Source |
|---|---|---|
| [`razhan/whisper-base-sdh`](https://huggingface.co/razhan/whisper-base-sdh) | STT — Southern Kurdish speech recognition | HuggingFace (local CT2) |
| [`facebook/wav2vec2-xlsr-53-espeak-cv-ft`](https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft) | IPA transcription — multilingual phoneme recognition | HuggingFace (local) |
| Silero VAD | Voice activity detection — segment boundary detection in long recordings | bundled with faster-whisper |
| epitran | IPA transliteration — rule-based fallback for Arabic-script Southern Kurdish | Python library |

**Razhan** is the key model for the Southern Kurdish thesis project. It is a Whisper variant fine-tuned directly on Southern Kurdish (`sdh`) speech data, converted to CTranslate2 format for GPU-accelerated inference (`device=cuda, compute_type=float16`). It produces **Kurdish Arabic-script orthographic transcriptions with word-level timestamps** — not IPA. IPA is a separate stage handled by wav2vec2.

Silero VAD segments each full-length recording before Razhan processes it. VAD parameters are tuned specifically for the elicitation recording format: activation threshold 0.35 (lower than default, to catch soft-spoken consultants at variable microphone distances) and minimum silence of 300 ms between segments (to prevent interviewer-prompt and speaker-response pairs from being collapsed into single units).

The wav2vec2 model (`facebook/wav2vec2-xlsr-53-espeak-cv-ft`) handles IPA transcription of annotated segments via CTC phoneme-to-word alignment. Both models are stored locally — no internet connection is required at inference time.

### Lexical Anchor Alignment System

The core unique feature of PARSE. Long elicitation recordings (2.5–5 hours each) contain target lexical items embedded in conversational frames, metalinguistic commentary, and ambient noise. Manually scanning recordings to locate each concept across eleven speakers is prohibitively slow and inconsistent. PARSE solves this through a two-signal candidate scoring pipeline (thesis §4.4).

**Signal A — Within-speaker repetition detection.** Each elicited item is typically produced two to four times in succession. Clusters of phonetically similar forms within a 30-second window are strong candidates for a repeated target item. Phonetic similarity is measured by normalised Levenshtein distance on IPA strings.

**Signal B — Cross-speaker concept matching.** Unassigned segments are compared against verified annotations from other speakers for the same concept using a four-strategy cascade: exact orthographic → fuzzy orthographic → phonetic rule-based → positional prior. Phonetic variation rules encode documented Southern Kurdish alternations — onset voicing (k/g, t/d, p/b), nucleus variation (e/a), coda deletion — so that legitimate dialectal variants are not rejected as mismatches.

**Confidence formula:**

```
confidence = 0.50 × phonetic + 0.25 × repetition + 0.15 × positional + 0.10 × cluster
```

The positional component applies a 45-second tolerance window (linear decay) around the expected timestamp derived from the cross-speaker median for each concept.

The system presents ranked candidates. The annotator verifies, adjusts boundaries, and confirms. Nothing is saved without an explicit action. Candidate quality improves as the dataset grows — each verified annotation adds to the reference pool that cross-speaker matching draws on, making later speakers progressively faster to annotate than the first.

---

## AI Workflow Assistant

Both Annotate and Compare modes include a built-in AI chat dock powered by the configured LLM provider (xAI/Grok, OpenAI, or Ollama). This is not a general-purpose chatbot — it is a domain-specific assistant designed to guide users through the entire PARSE workflow from start to finish.

The assistant has full access to project state via the MCP tool interface and can:

**Audio setup and file management**
- Help locate and load `.wav` source files into the workspace
- Check audio health (LUFS, format, sample rate, duration)
- Guide the normalization pipeline for new speakers

**Annotation workflow**
- Walk through the segment annotation process tier by tier (IPA, orthography, concept, speaker)
- Run the STT pipeline on a full recording to locate candidate segments
- Assist with boundary correction and iterative refinement

**Cross-speaker analysis**
- Prepare and guide a Compare mode session
- Explain cognate controls and borrowing adjudication decisions
- Help interpret enrichment overlays and similarity scores

**Export and downstream pipeline**
- Guide LingPy-compatible TSV export
- Explain column structure for LexStat and BEAST 2 input

**Troubleshooting**
- Diagnose pipeline failures (STT, IPA, normalization)
- Identify missing files, mismatched metadata, or annotation gaps
- Explain error messages from the server log

The assistant operates with read and write access to the project. It can stage files, update metadata, trigger jobs, and report back — without requiring the user to leave the interface.

---

## Quick Start

### 1) Start the Python backend

#### Windows

PARSE requires the `kurdish_asr` conda environment which has all Python dependencies pre-installed (faster-whisper, torch, torchaudio, soundfile, ctranslate2).

For the current React/Vite UI, start the backend directly:

```bash
/path/to/anaconda3/envs/kurdish_asr/python.exe python/server.py --project-root C:/path/to/parse_v2
```

Optional legacy launcher:

```bat
Start Review Tool.bat
```

> **Important:** `Start Review Tool.bat` is still a legacy launcher that opens `review_tool_dev.html` and depends on the old thesis/review server script. For the current React/Vite UI, start `python/server.py`, then run the Vite dev server as shown below and open `http://localhost:5173/`.

#### macOS / Linux

```bash
python3 python/server.py
```

> **Note:** `bash start_parse.sh` still opens the legacy `review_tool_dev.html` flow. Prefer the React/Vite workflow below unless you intentionally need legacy fallback tooling.

The backend runs on port `8766` by default and serves the API routes used by both the React/Vite frontend and the temporary legacy fallback pages.

### 2) Start the active React/Vite frontend

Run this once per clone:

```bash
npm install
```

Then start the frontend dev server:

```bash
npm run dev
```

### 3) Open in browser

#### Preferred React/Vite routes

- Annotate mode: `http://localhost:5173/`
- Compare mode: `http://localhost:5173/compare`

#### Legacy fallback routes (pre-C7 only)

Use these only if you intentionally need the legacy HTML pages while cleanup is still in progress:

- Annotate fallback: `http://localhost:8766/parse.html`
- Compare fallback: `http://localhost:8766/compare.html`

---

## Project Structure

```text
index.html              -- React/Vite entry HTML
src/                    -- Current React frontend (Annotate + Compare)
parse.html              -- Legacy Annotate fallback page (pre-C7)
compare.html            -- Legacy Compare fallback page (pre-C7)
js/                     -- Legacy frontend modules retained until C7 cleanup
python/
  server.py             -- Backend API server + legacy static serving (port 8766)
  ai/                   -- AI provider layer
    provider.py         -- STT / IPA / LLM provider factory
    chat_orchestrator.py-- Chat session management
    stt_pipeline.py     -- Whisper STT pipeline
    ipa_transcribe.py   -- IPA via wav2vec2 + epitran
    word_finder.py      -- Segment location in full recordings
  compare/              -- Compare pipeline (cognates, offsets, matching)
config/
  ai_config.json        -- AI provider configuration
annotations/            -- Per-speaker annotation JSON files (runtime, untracked)
parse-enrichments.json  -- Computed comparative overlays (runtime, untracked)
desktop/                -- Electron shell scaffold
docs/                   -- Documentation
```

---

## MCP Tool Interface

PARSE exposes a full **Model Context Protocol (MCP)** interface for external agents and AI coding assistants to interact with the project programmatically. The MCP server runs as a subprocess and communicates via standard input/output (stdio), making it compatible with any MCP-capable client.

```bash
python python/adapters/mcp_adapter.py
```

### Tools (14 total)

**Read-only (6)**

| Tool | Description |
|---|---|
| `parse_project_context_read` | Full project metadata and speaker status |
| `parse_find_workspace_files` | List files by category (speakers, audio, all) |
| `parse_read_csv_preview` | Preview a CSV file (e.g. `concepts.csv`) |
| `parse_annotation_read` | Read annotation data for a speaker |
| `parse_check_file` | Check file existence and return metadata |
| `parse_lufs_check` | Audio health check — format, duration, LUFS |

**Mutating (5)**

| Tool | Description |
|---|---|
| `parse_copy_to_workspace` | Copy a file into the project workspace (conflict signaling) |
| `parse_update_source_index` | Update `source_index.json` — speaker key collision detection |
| `parse_update_project_json` | Update `project.json` — protected key guard |
| `parse_import_audition_csv` | Import Adobe Audition marker CSV for speaker onboarding |
| `parse_onboard_speaker` | Full speaker onboarding (stages audio, registers metadata) |

**Job-based (3) — require HTTP server running**

| Tool | Description |
|---|---|
| `parse_normalize_audio` | Start audio normalization job. Returns `jobId` + `statusUrl` |
| `parse_trigger_pipeline` | Start STT / IPA / matching pipeline. Returns `jobId` |
| `parse_job_status` | Poll status of any running job by ID |

### Built-in Prompts (4)

| Prompt | Description |
|---|---|
| `import-speaker` | Guided speaker import workflow |
| `run-audio-health-check` | Full audio health report for a speaker |
| `review-speaker-status` | Review annotation completeness and gaps |
| `prepare-compare-session` | Prepare a cross-speaker compare session |

### HTTP mirrors

Several MCP tools are also available as HTTP endpoints on port `8766` for direct server-side calls without the MCP transport layer:

- `POST /api/onboard/speaker` — mirrors `parse_onboard_speaker`
- `GET /api/project/status` — mirrors `parse_project_context_read`

### Conflict contract

Mutating tools use an explicit conflict signaling contract:
- `force=False` (default) — returns a conflict signal if the target key or file already exists
- `force=True` — overwrites without confirmation

Read tools never modify state.

---

## Data Architecture

PARSE uses a hybrid data model:

- **Live annotations** — per-speaker JSON files in `annotations/<Speaker>.json` (primary source of truth; timestamps are never modified by AI)
- **Computed enrichments** — `parse-enrichments.json`, generated by the compare pipeline for cognate sets, similarity scores, and borrowing decisions
- **Tag store** — `js/shared/tags.js` persists tag definitions to localStorage, shared across both Annotate and Compare modes under a single project-scoped key

The enrichments layer stores computed structures while preserving manual adjudications. Annotations and enrichments are both excluded from version control as runtime data.

---

## Technology

- React 18 + TypeScript + Vite (current frontend architecture)
- Legacy vanilla JavaScript + HTML entrypoints (temporary pre-C7 fallback)
- Python 3.10+ with conda environment
- WaveSurfer 7
- faster-whisper + CTranslate2 (local STT)
- wav2vec2 via HuggingFace transformers (local IPA)
- CUDA 12/13 + PyTorch (GPU inference)

---

## Context

PARSE was built for a Southern Kurdish dialect phylogenetics thesis at the University of Bamberg. The working dataset covers multiple speakers of Southern Kurdish varieties with an 85-item Oxford Iranian wordlist, targeting downstream Bayesian phylogenetic analysis in BEAST 2.

---

## License

MIT
