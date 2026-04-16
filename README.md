# PARSE

**P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer  
Browser-based dual-mode workstation for linguistic fieldwork and cross-speaker comparison.  
Repository: [ArdeleanLucas/PARSE](https://github.com/ArdeleanLucas/PARSE)

## What is PARSE

PARSE is a browser-based research tool for linguists working with long field recordings, concept-based wordlists, and multi-speaker datasets. It combines audio navigation, annotation, and comparative analysis in one workspace, so researchers can move from raw recordings to analysis-ready linguistic data without switching between disconnected tools.

Phase 5 of the project introduces a dual-mode architecture: **Annotate** for per-speaker segmentation and transcription, and **Compare** for cross-speaker cognate review and borrowing adjudication. Both modes are hosted in a **unified React shell** (`ParseUI.tsx`) alongside the tag system and AI chat dock, with precise time-aligned annotations and a shared tag system across workflows.

The active frontend architecture is **React + Vite** (`index.html` + `src/`), with the preferred development routes at `http://localhost:5173/` (Annotate) and `http://localhost:5173/compare` (Compare). Legacy `parse.html` and `compare.html` pages still remain on `main` as temporary fallback entrypoints served by the Python backend on port `8766` while C5/C6 validation is completed ahead of C7 cleanup.

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
- **CLEF** (Contact Lexeme Explorer Feature) — multi-source contact-language similarity panel powered by a provider registry (see below)
- Unified tag system (shared with Annotate mode) for scoped filtering
- Export to LingPy-compatible TSV and NEXUS (placeholder) for downstream pipelines (LexStat, BEAST 2)

### CLEF — Contact Lexeme Explorer Feature

CLEF provides contact-language similarity data for borrowing adjudication in Compare mode. It fetches lexical data from multiple third-party and local sources via a **provider registry** (`python/compare/providers/`), then surfaces similarity signals in the `ContactLexemePanel` UI component.

**Providers (11):**

| Provider | Source type |
|---|---|
| `asjp` | ASJP database |
| `cldf` | CLDF datasets |
| `csv_override` | Local CSV overrides |
| `grokipedia` | LLM-assisted lookup (xAI/Grok) |
| `lingpy_wordlist` | LingPy wordlist data |
| `literature` | Published literature references |
| `pycldf_provider` | pycldf library |
| `pylexibank_provider` | pylexibank library |
| `wikidata` | Wikidata lexemes |
| `wiktionary` | Wiktionary entries |

**Endpoints:**
- `POST /api/compute/contact-lexemes` — trigger contact-lexeme fetch job
- `GET /api/contact-lexemes/coverage` — check coverage status across providers

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

The assistant has full access to project state via the `ParseChatTools` interface (`python/ai/chat_tools.py`) and can:

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

### One-command launch (recommended)

The `parse-run` shell alias starts both servers, pulls the latest code, and
health-checks the API before printing URLs. It is defined in `~/.bash_aliases`
and sourced automatically by Bash.

```bash
parse-run          # pull main → start API + Vite → health-check → print URLs
```

On success you will see:

```
[parse-run] ════════════════════════════════════════
[parse-run]   PARSE is running
[parse-run]   React UI:  http://localhost:5173/
[parse-run]   Compare:   http://localhost:5173/compare
[parse-run]   API:       http://localhost:8766/api/config
[parse-run] ════════════════════════════════════════
```

Open **http://localhost:5173/** in your browser for the React UI.

Two companion commands are also available:

```bash
parse-stop         # kill both servers
parse-logs api     # tail Python API stderr
parse-logs vite    # tail Vite dev server output
```

#### What `parse-run` does

1. `git pull origin main --ff-only` — fast-forward to latest main
2. Kills any stale Python or Vite processes on ports 8766 / 5173
3. Starts the **Python API server** (`python/server.py`) on `:8766`
4. Waits for `/api/config` to return 200 (up to 12 s)
5. Starts the **Vite dev server** (`npx vite --host`) on `:5173`
6. Waits for Vite to respond, then prints URLs

Both servers must be running. The Python backend serves the API routes;
the Vite dev server serves the React/TypeScript frontend with Tailwind CSS
and hot module replacement.

#### Requirements

- **WSL / Linux** — the alias uses Bash and `pkill`/`fuser`
- **`kurdish_asr` conda env** — Python interpreter path is hardcoded in the
  alias (`/mnt/c/Users/Lucas/anaconda3/envs/kurdish_asr/python.exe`)
- **Node.js 18+** and `npm install` run once per clone

### Manual launch (alternative)

If you prefer to start each server individually:

```bash
# Terminal 1 — Python API backend
cd /path/to/parse_v2
/path/to/anaconda3/envs/kurdish_asr/python.exe python/server.py

# Terminal 2 — Vite frontend
cd /path/to/parse_v2
npm install   # once per clone
npm run dev
```

The backend runs on port `8766`; Vite runs on port `5173`.

### Open in browser

#### React UI (active)

- Annotate mode: `http://localhost:5173/`
- Compare mode: `http://localhost:5173/compare`

#### Legacy fallback (pre-C7 only)

- Annotate fallback: `http://localhost:8766/parse.html`
- Compare fallback: `http://localhost:8766/compare.html`

---

## Project Structure

```text
index.html              -- React/Vite entry HTML
src/
  App.tsx               -- BrowserRouter shell → <ParseUI />
  ParseUI.tsx           -- Unified UI shell (Annotate + Compare + Tags + AI Chat)
  api/
    client.ts           -- Typed API client (all fetch calls go through here)
    types.ts            -- Shared TypeScript types
  components/
    annotate/           -- Annotate mode components
    compare/            -- Compare mode (CompareMode, ConceptTable, CognateControls,
                           BorrowingPanel, EnrichmentsPanel, ContactLexemePanel,
                           SpeakerImport, TagManager)
    shared/             -- Cross-mode shared components
  hooks/                -- React hooks (useWaveSurfer, useChatSession,
                           useAnnotationSync, useSpectrogram, useActionJob,
                           useComputeJob, useExport, useImportExport, useSuggestions)
  stores/               -- Zustand stores (annotationStore, configStore,
                           enrichmentStore, playbackStore, tagStore, uiStore)
parse.html              -- Legacy Annotate fallback page (pre-C7)
compare.html            -- Legacy Compare fallback page (pre-C7)
js/                     -- Legacy frontend modules retained until C7 cleanup
python/
  server.py             -- Backend API server + legacy static serving (port 8766)
  ai/                   -- AI provider layer
    chat_tools.py       -- ParseChatTools — AI assistant tool interface (10 tools)
    chat_orchestrator.py-- Chat session management
    stt_pipeline.py     -- Whisper STT pipeline
    ipa_transcribe.py   -- IPA via wav2vec2 + epitran
    word_finder.py      -- Segment location in full recordings
  compare/              -- Compare pipeline (cognates, offsets, matching)
    providers/          -- CLEF provider registry (11 providers)
  shared/               -- Shared Python utilities
config/
  ai_config.json        -- AI provider configuration
annotations/            -- Per-speaker annotation JSON files (runtime, untracked)
parse-enrichments.json  -- Computed comparative overlays (runtime, untracked)
desktop/                -- Electron shell scaffold
docs/                   -- Documentation and plans
```

---

## AI Chat Tools

The AI chat assistant uses `ParseChatTools` (`python/ai/chat_tools.py`) as its programmatic tool layer. These tools are invoked by the LLM during chat sessions — they are not exposed as a standalone server.

### Tools (10)

**Read-only**

| Tool | Description |
|---|---|
| `project_context_read` | Full project metadata and speaker status |
| `annotation_read` | Read annotation data for a speaker (with optional tier/concept filtering) |
| `read_csv_preview` | Preview a CSV file (e.g. `concepts.csv`) |
| `cognate_compute_preview` | Preview cognate computation results |
| `cross_speaker_match_preview` | Preview cross-speaker matching candidates |
| `spectrogram_preview` | Generate spectrogram preview for a segment |

**Job-triggering**

| Tool | Description |
|---|---|
| `stt_start` | Start STT pipeline on a recording. Returns job ID |
| `stt_status` | Poll status of a running STT job |

**Tag operations**

| Tool | Description |
|---|---|
| `prepare_tag_import` | Validate and preview a tag CSV before import |
| `import_tag_csv` | Import tags from a prepared CSV file |

---

## HTTP API

The Python backend (`python/server.py`, port `8766`) exposes the following endpoints. The React frontend communicates exclusively through the typed client in `src/api/client.ts`.

### GET

| Endpoint | Description |
|---|---|
| `/api/config` | Project configuration |
| `/api/enrichments` | Computed comparative enrichments |
| `/api/auth/status` | Auth provider status |
| `/api/export/lingpy` | LingPy-compatible TSV export |
| `/api/export/nexus` | NEXUS export *(placeholder — not yet implemented)* |
| `/api/contact-lexemes/coverage` | CLEF provider coverage status |
| `/api/tags` | Tag definitions and assignments |

### POST

| Endpoint | Description |
|---|---|
| `/api/onboard/speaker` | Speaker onboarding (multipart upload, background job) |
| `/api/onboard/speaker/status` | Poll onboarding job status |
| `/api/normalize` | Start audio normalization (ffmpeg loudnorm) |
| `/api/normalize/status` | Poll normalization job status |
| `/api/stt` | Start STT pipeline |
| `/api/stt/status` | Poll STT job status |
| `/api/ipa` | Request IPA transcription for text |
| `/api/suggest` | Request annotation suggestions |
| `/api/chat/session` | Create or resume a chat session |
| `/api/chat/run` | Send a message to the chat assistant |
| `/api/chat/run/status` | Poll chat run status |
| `/api/enrichments` | Save enrichments (POST overwrites) |
| `/api/config` | Update project configuration (partial) |
| `/api/auth/key` | Save API key for a provider |
| `/api/auth/start` | Start OAuth flow |
| `/api/auth/poll` | Poll OAuth status |
| `/api/auth/logout` | Clear auth credentials |
| `/api/tags/merge` | Merge tag definitions |

### PUT

| Endpoint | Description |
|---|---|
| `/api/config` | Full project configuration update |

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
- Zustand (state management)
- Tailwind CSS v3 (styling)
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

## Citation

If you use PARSE in academic work, please cite it as research software. A machine-readable `CITATION.cff` is included in the repository root, so GitHub's **"Cite this repository"** sidebar button will produce APA/BibTeX entries automatically.

Suggested citation:

> Ardelean, L. M. (2026). *PARSE: Phonetic Analysis & Review Source Explorer* [Computer software]. University of Bamberg. https://github.com/ArdeleanLucas/PARSE

BibTeX:

```bibtex
@software{ardelean_parse_2026,
  author  = {Ardelean, Lucas M.},
  title   = {{PARSE}: Phonetic Analysis \& Review Source Explorer},
  year    = {2026},
  url     = {https://github.com/ArdeleanLucas/PARSE},
  note    = {Research software for Southern Kurdish dialect phylogenetics}
}
```

PARSE is research software developed alongside a Southern Kurdish dialect phylogenetics thesis at the University of Bamberg; please also cite the associated thesis if/when it is published.

---

## License

MIT
