# PARSE

**P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer  
Browser-based dual-mode workstation for linguistic fieldwork and cross-speaker comparison.  
Repository: [ArdeleanLucas/PARSE](https://github.com/ArdeleanLucas/PARSE)

## What is PARSE

PARSE is a browser-based research tool for linguists working with long field recordings, concept-based wordlists, and multi-speaker datasets. It combines audio navigation, annotation, and comparative analysis in one workspace, so researchers can move from raw recordings to analysis-ready linguistic data without switching between disconnected tools.

PARSE has a dual-mode architecture: **Annotate** for per-speaker segmentation and transcription, and **Compare** for cross-speaker cognate review and borrowing adjudication. Both modes are hosted in a **unified React shell** (`ParseUI.tsx`) alongside the tag system and AI chat dock, with precise time-aligned annotations and a shared tag system across workflows.

The active frontend architecture is **React + Vite** (`index.html` + `src/`), with the preferred development routes at `http://localhost:5173/` (Annotate) and `http://localhost:5173/compare` (Compare). The legacy HTML entrypoints, old review page, and root vanilla-JS tree have been removed. For non-dev/local-server usage, run `npm run build` and the Python backend will serve the built frontend from `http://localhost:8766/` and `http://localhost:8766/compare`. LingPy export verification and full browser regression remain on a deferred to-test list until onboarding/import and end-to-end testing are ready.

The Python backend continues to power AI/API routes for both architectures. PARSE is designed for real fieldwork constraints — large recordings, mixed metadata quality, iterative review — and should be treated as **research software** rather than production software.

---

## Modes

### Annotate mode (React route `/`)

Per-speaker segmentation and transcription workstation.

- Waveform review with WaveSurfer 7 for long recordings
- Four annotation tiers: **IPA**, **orthography**, **concept**, and **speaker**
- AI-assisted STT for locating candidate segments in full recordings
- Draggable timestamp regions for boundary correction
- Fast segment playback and iterative refinement
- AI chat dock for in-session analysis assistance
- Tag and filter concepts for selective annotation

### Compare mode (React route `/compare`)

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

**Providers (10):**

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
- **Python-served built UI:** `http://localhost:8766/` and `http://localhost:8766/compare` after `npm run build`
- **Cleanup status:** legacy vanilla-JS entrypoints have been removed from the repo; broader validation still lives on the deferred testing backlog

---

## AI Provider System

PARSE supports multiple AI backends, routed per task type:

| Task | Supported providers |
|---|---|
| STT (speech-to-text) | faster-whisper (local, GPU), OpenAI Whisper API |
| IPA transcription | wav2vec2 (local), epitran (fallback) |
| LLM / chat | xAI (Grok), OpenAI |

Provider selection is feature-specific — STT, IPA, and LLM tasks can each route to a different backend in the same project. Configuration lives in `config/ai_config.json`, which is gitignored because it contains machine-specific paths (e.g. a local Razhan CT2 model path). Copy `config/ai_config.example.json` to `config/ai_config.json` on a fresh clone and edit for your machine. If the file is missing entirely, the backend falls back to built-in defaults with a `[WARN]` on stderr.

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

Both Annotate and Compare modes include a built-in AI chat dock powered by the configured LLM provider (xAI/Grok or OpenAI). This is not a general-purpose chatbot — it is a domain-specific assistant designed to guide users through the entire PARSE workflow from start to finish.

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

The `scripts/parse-run.sh` launcher (tracked in this repo) starts both servers, pulls the latest code, cleans up stale processes on both WSL and Windows sides, probes the API port before launch, and health-checks the API before printing URLs. A shell alias (`parse-run`) is typically wired to call this script.

```bash
scripts/parse-run.sh    # same as `parse-run` alias; run directly from repo root
```

The alias version lives in `~/.bash_aliases`:

```bash
alias parse-run='/path/to/parse/scripts/parse-run.sh'
alias parse-stop='/path/to/parse/scripts/parse-stop.sh'
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

### Workspace-first bootstrap (recommended on a fresh machine)

For real fieldwork use, keep generated runtime state outside the git checkout. `scripts/parse-init-workspace.sh` scaffolds a standalone workspace for copied source audio, annotations, peaks, chat memory, and config-local runtime files.

```bash
# scaffold once
scripts/parse-init-workspace.sh /path/to/parse-workspace

# then launch PARSE against that workspace
PARSE_WORKSPACE_ROOT="/path/to/parse-workspace" \
  PARSE_CHAT_MEMORY_PATH="/path/to/parse-workspace/parse-memory.md" \
  PARSE_EXTERNAL_READ_ROOTS="/mnt/c/Users/Lucas/Thesis" \
  scripts/parse-run.sh
```

This keeps original WAV/CSV sources untouched. Chat-assisted onboarding copies selected source files into `audio/original/<speaker>/` inside the workspace rather than mutating the source tree.

Environment overrides:

| Variable | Default | Purpose |
|---|---|---|
| `PARSE_PY` | `python3` | Python interpreter. Set to a Windows `python.exe` (e.g. `/mnt/c/Users/Lucas/anaconda3/envs/kurdish_asr/python.exe`) when running from WSL against a Windows conda env. |
| `PARSE_ROOT` | auto-detected | Repo root. |
| `PARSE_WORKSPACE_ROOT` | `PARSE_ROOT` | Workspace/data root used by backend chat tools and runtime files. Point this outside the repo for fieldwork use. |
| `PARSE_CHAT_DOCS_ROOT` | `PARSE_WORKSPACE_ROOT` | Optional docs/text root used by `read_text_preview`. |
| `PARSE_CHAT_MEMORY_PATH` | `PARSE_WORKSPACE_ROOT/parse-memory.md` | Persistent markdown memory file used by the chat assistant. |
| `PARSE_EXTERNAL_READ_ROOTS` | empty | Absolute roots the chat assistant may read outside the workspace for onboarding and file previews. Use OS path separators for multiple roots, or `*` to disable the sandbox entirely. |
| `PARSE_CHAT_READ_ONLY` | empty | Override chat mutability: `1` forces read-only; `0` forces write-enabled. Otherwise PARSE defers to `config/ai_config.json`. |
| `PARSE_API_PORT` | `8766` | API server port. |
| `PARSE_VITE_PORT` | `5173` | Vite dev server port. |
| `PARSE_SKIP_PULL` | `0` | Set to `1` to skip the `git pull` step. |
| `PARSE_PULL_MODE` | `auto` | Git integration strategy: `auto`, `ff`, `rebase`, or `reset`. |

For machine-local overrides without editing tracked files, create a gitignored `.parse-env` file in the repo root. `parse-run.sh` sources it before applying defaults, and the standalone MCP adapter now mirrors that convention when launched directly, so settings like `PARSE_PY`, `PARSE_EXTERNAL_READ_ROOTS`, or `PARSE_CHAT_MEMORY_PATH` can live there permanently. Explicit process environment variables still win over `.parse-env`.

Two companion commands are also available:

```bash
scripts/parse-stop.sh   # kill both servers (WSL + Windows-side zombies)
parse-logs api          # tail Python API stderr
parse-logs vite         # tail Vite dev server output
```

#### WSL + Windows python.exe note

When `PARSE_PY` points at a Windows `python.exe` (a conda env on `C:`), the actual server process runs on the Windows side. WSL's `pkill`/`fuser` cannot signal Windows processes, so `parse-run.sh` detects this case and additionally calls `taskkill.exe` via `/mnt/c/Windows/System32/` to clean up zombie `python.exe` instances holding port 8766. This prevents the "empty reply from server" failure mode where a broken prior process blocks the port.

If `parse-run.sh` reports that it **cannot bind** `127.0.0.1:8766` with `WinError 10013` or `10048`, this is usually a Windows/WSL phantom port reservation. The launcher now detects that case before startup and prints the fix: run `wsl --shutdown` from Windows Command Prompt or PowerShell, then relaunch PARSE. You can also temporarily override the port with `PARSE_API_PORT=<other>`.

#### What `scripts/parse-run.sh` does

1. Integrates latest `origin/main` according to `PARSE_PULL_MODE` (skipped if `PARSE_SKIP_PULL=1`)
2. Kills any stale Python or Vite processes on ports 8766 / 5173
3. Probes whether the API port is actually bindable before launch
4. Starts the **Python API server** (`python/server.py`) on `:8766`
5. Waits for `/api/config` to return 200 (up to 12 s)
6. Starts the **Vite dev server** (`npx vite --host`) on `:5173`
7. Waits for Vite to respond, then prints URLs

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
# One-time per clone: create your local AI config from the template
cp config/ai_config.example.json config/ai_config.json
# then edit config/ai_config.json — especially stt.model_path (local Razhan CT2 path)

# Terminal 1 — Python API backend
cd /path/to/parse
/path/to/anaconda3/envs/kurdish_asr/python.exe python/server.py

# Terminal 2 — Vite frontend
cd /path/to/parse
npm install   # once per clone
npm run dev
```

The backend runs on port `8766`; Vite runs on port `5173`.

### Open in browser

#### React UI (active dev workflow)

- Annotate mode: `http://localhost:5173/`
- Compare mode: `http://localhost:5173/compare`

#### Python-served built UI (after `npm run build`)

- Annotate mode: `http://localhost:8766/`
- Compare mode: `http://localhost:8766/compare`

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
python/
  server.py             -- Backend API server + built-frontend static serving (port 8766)
  adapters/
    mcp_adapter.py      -- MCP server adapter (exposes ParseChatTools over stdio MCP)
  ai/                   -- AI provider layer
    chat_tools.py       -- ParseChatTools — AI assistant tool interface (16 tools)
    chat_orchestrator.py-- Chat session management
    stt_pipeline.py     -- Whisper STT pipeline
    ipa_transcribe.py   -- IPA via wav2vec2 + epitran
    word_finder.py      -- Segment location in full recordings
  compare/              -- Compare pipeline (cognates, offsets, matching)
    providers/          -- CLEF provider registry and provider adapters
  shared/               -- Shared Python utilities
config/
  ai_config.example.json -- Template for AI provider configuration (tracked)
  ai_config.json          -- AI provider configuration (gitignored — copy from example)
annotations/            -- Per-speaker annotation JSON files (runtime, untracked)
parse-enrichments.json  -- Computed comparative overlays (runtime, untracked)
desktop/                -- Electron shell scaffold
docs/                   -- Documentation and plans
dist/                   -- Vite build output (generated, gitignored)
```

---

## AI Chat Tools

The AI chat assistant uses `ParseChatTools` (`python/ai/chat_tools.py`) as its programmatic tool layer. The built-in PARSE chat currently exposes **16 tools** in total. These tools are invoked by the LLM during chat sessions and stay bounded to PARSE-specific workflows.

### Tools (16)

**Read-only / preview**

| Tool | Description |
|---|---|
| `project_context_read` | Full project metadata and speaker status |
| `annotation_read` | Read annotation data for a speaker (with optional tier/concept filtering) |
| `cognate_compute_preview` | Preview cognate computation results |
| `cross_speaker_match_preview` | Preview cross-speaker matching candidates |
| `spectrogram_preview` | Generate spectrogram preview for a segment |
| `read_audio_info` | Read WAV metadata (duration, sample rate, channels, sample width, file size) |
| `read_csv_preview` | Preview a CSV file (e.g. `concepts.csv`) |
| `read_text_preview` | Preview Markdown/text files from the workspace or docs root |
| `parse_memory_read` | Read persistent chat memory from `parse-memory.md` |

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

**Write / merge operations**

| Tool | Description |
|---|---|
| `contact_lexeme_lookup` | Fetch and optionally merge contact-language reference forms via the CLEF provider chain (`dryRun=true` first) |
| `onboard_speaker_import` | Copy external audio/CSV into the workspace, scaffold speaker state, and register it in `source_index.json` (`dryRun=true` first) |
| `parse_memory_upsert_section` | Create or replace a `## Section` block in `parse-memory.md` (`dryRun=true` first) |

The built-in assistant operates with both read and write access to the project, but the write-capable tools are intentionally gated. In particular, onboarding is **one speaker at a time**, and multi-source speakers are flagged as requiring manual / virtual-timeline coordination because PARSE does not yet auto-align multiple WAVs into a shared annotation timeline.

---

## MCP Server Mode

PARSE can run as an **MCP (Model Context Protocol) server**, exposing a **14-tool MCP-safe subset** of its AI chat/tooling surface over the standard MCP protocol. This lets third-party agents — Claude Code, Cursor, Codex, Windsurf, or any MCP-compatible client — call PARSE tools programmatically without going through the browser UI.

```bash
python python/adapters/mcp_adapter.py                          # auto-detect project root
python python/adapters/mcp_adapter.py --project-root /path/to  # explicit root
python python/adapters/mcp_adapter.py --verbose                # debug logging
```

### Client Configuration

Add PARSE as an MCP server in your client config. Example for Claude Desktop (`claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "parse": {
            "command": "python",
            "args": ["/path/to/parse/python/adapters/mcp_adapter.py"],
            "env": {
                "PARSE_PROJECT_ROOT": "/path/to/your/parse/project",
                "PARSE_EXTERNAL_READ_ROOTS": "/mnt/c/Users/Lucas/Thesis",
                "PARSE_CHAT_MEMORY_PATH": "/path/to/parse-memory.md"
            }
        }
    }
}
```

If you launch the adapter without an explicit `env` block, it also reads repo-local overrides from `<project-root>/.parse-env` (same convention as `scripts/parse-run.sh`). Use that for machine-specific `PARSE_EXTERNAL_READ_ROOTS`, `PARSE_CHAT_MEMORY_PATH`, or `PARSE_PROJECT_ROOT`; explicit client-provided env vars still take precedence.

### Exposed Tools

The MCP adapter exposes the subset of `ParseChatTools` that is currently registered in `python/adapters/mcp_adapter.py`:

| Tool | Description |
|---|---|
| `project_context_read` | Project metadata, source index, annotation inventory, enrichments summary |
| `annotation_read` | Read speaker annotation data with optional concept/tier filtering |
| `read_csv_preview` | Preview CSV files (columns, row count, sample rows) |
| `cognate_compute_preview` | Compute cognate/similarity preview from annotations (read-only) |
| `cross_speaker_match_preview` | Cross-speaker match candidates from STT output |
| `spectrogram_preview` | Spectrogram preview for a time-bounded segment |
| `contact_lexeme_lookup` | Fetch reference forms from third-party sources (CLDF, ASJP, Wikidata, etc.); **dryRun required** — pass dryRun=true to preview, dryRun=false to merge into sil_contact_languages.json |
| `stt_start` | Start STT background job on an audio file (proxied to the running PARSE HTTP server on PARSE_API_PORT, default 8766, so job state is shared with the browser UI) |
| `stt_status` | Poll status/progress of an STT job (same HTTP proxy) |
| `import_tag_csv` | Import a CSV file as a custom tag list (dry-run first) |
| `prepare_tag_import` | Create/update a tag with concept IDs (dry-run first) |
| `onboard_speaker_import` | Import one speaker from on-disk audio (and optional CSV) into the workspace; dry-run first; multi-source speakers may require manual virtual-timeline coordination |
| `parse_memory_read` | Read persistent PARSE chat memory from `parse-memory.md` |
| `parse_memory_upsert_section` | Upsert a `## Section` block in `parse-memory.md`; dry-run first |

> **Requires:** `pip install 'mcp[cli]'`

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
- **Tag store** — Zustand `tagStore` persists tag definitions to localStorage, shared across both Annotate and Compare modes under a single project-scoped key

The enrichments layer stores computed structures while preserving manual adjudications. Annotations and enrichments are both excluded from version control as runtime data.

---

## Technology

- React 18 + TypeScript + Vite (current frontend architecture)
- Zustand (state management)
- Tailwind CSS v3 (styling)
- Python 3.10–3.12 backend serving API routes and the built frontend (`dist/`) for non-dev usage (3.13+ is blocked by `cgi.FieldStorage` removal until `python/server.py` migrates off it)
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
