# AI Integration

> Last updated: 2026-04-24
>
> This document consolidates the AI provider system, model roles, configuration expectations, and the full built-in PARSE chat tool surface currently described in the repository README and code.

PARSE is AI-native, but not in the sense of a generic chatbot pasted onto a UI. Different tasks route to different providers and model families, and the in-app assistant operates through a bounded PARSE-specific tool layer.

## Provider system at a glance

PARSE routes AI work by task type rather than forcing one model/provider to do everything.

| Task | Supported providers |
|---|---|
| STT (speech-to-text) | faster-whisper (local), OpenAI Whisper API |
| IPA transcription | acoustic wav2vec2 via `ipa_only` compute |
| LLM / chat | xAI (Grok), OpenAI |

A single project can therefore mix providers across tasks:

- local STT / ORTH for speech work
- wav2vec2 for alignment and acoustic IPA
- OpenAI or xAI for workflow chat

Configuration lives in `config/ai_config.json`.

## Configuration model

PARSE expects a machine-local config file:

```bash
cp config/ai_config.example.json config/ai_config.json
```

The file is gitignored because it includes machine-specific paths and secrets.

If the file is missing, the backend can still start with built-in defaults, but runtime behavior will not necessarily match a thesis-ready setup.

### Key config sections

#### `stt`

This block controls the main speech-to-text provider.

Current template:

```json
"stt": {
  "provider": "faster-whisper",
  "model_path": "",
  "language": "ku",
  "device": "cuda",
  "compute_type": "float16",
  "beam_size": 5
}
```

Operational notes from the current README and template:

- faster-whisper is the main local STT backend
- word-level timestamps are enabled in the pipeline
- language can be auto-detected from project metadata when available
- the intended workflow is GPU-backed local inference
- the current README notes explicit CUDA-runtime detection, an emergency `PARSE_STT_FORCE_CPU=1` override, and a CPU/int8 fallback if the local CUDA stack is unavailable
- mid-run CUDA failures rebuild the Whisper model on CPU instead of leaving the job wedged

#### `ortho`

This block configures the orthographic transcription path.

Current recommended ORTH block for `ai_config.json`:

```json
"ortho": {
  "provider": "faster-whisper",
  "model_path": "/path/to/razhan-whisper-base-sdh-ct2",
  "language": "sd",
  "device": "cuda",
  "compute_type": "float16",
  "beam_size": 5,
  "vad_filter": true,
  "vad_parameters": {
    "min_silence_duration_ms": 500,
    "threshold": 0.35
  },
  "condition_on_previous_text": false,
  "compression_ratio_threshold": 1.8,
  "initial_prompt": "",
  "refine_lexemes": false
}
```

Key behavior:

- **Razhan** (`razhan/whisper-base-sdh`) is still the canonical Southern Kurdish source model, but `ortho.model_path` must point at a **local CTranslate2 conversion directory**
- HuggingFace repo ids are **rejected** in `ortho.model_path`; convert first with `ct2-transformers-converter --model razhan/whisper-base-sdh --output_dir /path/to/razhan-whisper-base-sdh-ct2`
- ORTH defaults now keep the anti-cascade guard enabled: `vad_filter=true` with tuned Silero params, `condition_on_previous_text=false`, and `compression_ratio_threshold=1.8`
- `initial_prompt` can prime the Whisper decoder for elicitation-style recordings
- `refine_lexemes=true` adds a short-clip lexeme refinement pass after forced alignment

#### `ipa` + `wav2vec2`

The current PARSE architecture makes acoustic IPA a dedicated wav2vec2 stage rather than a text-derived fallback.

```json
"ipa": {
  "engine": "wav2vec2",
  "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
  "model_only": true
},
"wav2vec2": {
  "provider": "wav2vec2-ipa",
  "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
  "device": "cuda",
  "force_cpu": false,
  "chunk_size": 150
}
```

Important design point: the older Epitran / text-to-IPA / LLM IPA paths are gone from the main workflow described in the current README.

#### `llm` and `chat`

These blocks configure the workflow assistant.

```json
"llm": {
  "provider": "openai",
  "model": "gpt-5.4",
  "api_key_env": "OPENAI_API_KEY"
},
"chat": {
  "enabled": true,
  "read_only": false,
  "provider": "openai",
  "model": "gpt-5.4",
  "api_key_env": "OPENAI_API_KEY",
  "temperature": 0.1,
  "max_tool_rounds": 4,
  "max_history_messages": 24,
  "max_output_tokens": 1400
}
```

Supported provider families for chat are currently:

- **OpenAI**
- **xAI / Grok**

## Current model roles

### `razhan/whisper-base-sdh`

| Field | Value |
|---|---|
| Task | ORTH transcription / Southern Kurdish speech recognition |
| Source | Local CTranslate2 directory converted from `razhan/whisper-base-sdh` |
| Role in PARSE | Speaker-level orthographic transcription for Southern Kurdish recordings |

The current README emphasizes that Razhan produces **Kurdish Arabic-script orthographic transcription with word-level timestamps**. It is **not** the IPA engine.

### `facebook/wav2vec2-xlsr-53-espeak-cv-ft`

| Field | Value |
|---|---|
| Task | Tier 2 forced alignment + Tier 3 acoustic IPA |
| Source | HuggingFace (local) |
| Role in PARSE | Tightens word boundaries and generates phoneme output from audio slices |

Current behavior described in the README:

- Tier 2 forced alignment refines Tier 1 word windows
- Tier 3 IPA prefers the word-level STT cache when available
- If no STT word cache exists, PARSE falls back to coarse ORTH-interval slices
- On WSL, the aligner now resolves to **CPU by default** for long wav2vec2 CTC workloads
- `config/ai_config.json` exposes `wav2vec2.force_cpu` and `wav2vec2.chunk_size` so long runs can be tuned without code changes
- recent fixes also cache `EspeakBackend` instances per language and report progress during Tier 2 forced alignment, which matters most on slower CPU-heavy WSL runs

### Silero VAD

| Field | Value |
|---|---|
| Task | Voice activity detection |
| Source | Bundled with faster-whisper |
| Role in PARSE | Segment boundary detection for long recordings in Whisper-style decoding |

The current README notes that Silero VAD parameters are tuned for elicitation recordings with soft-spoken consultants and variable microphone distance.

### faster-whisper + CTranslate2

| Component | Role |
|---|---|
| `faster-whisper` | Local STT / ORTH inference backend |
| `CTranslate2` | Optimized runtime for Whisper-family models |

These components underpin local inference for the speech-heavy parts of PARSE.

## External dependency links worth citing

The current README includes a citation-oriented table for core external models and repositories directly referenced by PARSE.

| Component | Type | Used in PARSE for | Link |
|---|---|---|---|
| `razhan/whisper-base-sdh` | Model | ORTH transcription of Southern Kurdish speech | https://huggingface.co/razhan/whisper-base-sdh |
| `facebook/wav2vec2-xlsr-53-espeak-cv-ft` | Model | Acoustic IPA transcription + forced alignment | https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft |
| Silero VAD | Model / repo | Voice activity detection during Whisper-style decoding | https://github.com/snakers4/silero-vad |
| faster-whisper | Repository / library | Local STT + ORTH inference backend | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | Repository / library | Optimized local inference runtime for Whisper-family models | https://github.com/OpenNMT/CTranslate2 |
| WaveSurfer.js | Repository / library | Long-recording waveform UI | https://github.com/katspaugh/wavesurfer.js |
| React | Repository / library | Frontend application framework | https://github.com/facebook/react |
| Vite | Repository / library | Frontend dev/build toolchain | https://github.com/vitejs/vite |
| Tailwind CSS | Repository / library | Frontend styling system | https://github.com/tailwindlabs/tailwindcss |
| Lucide | Repository / library | UI icon set | https://github.com/lucide-icons/lucide |

## The AI workflow assistant

Both Annotate and Compare modes include a built-in assistant powered by the configured LLM provider.

The current README describes it as a **domain-specific assistant**, not a general-purpose chatbot. It operates through `ParseChatTools` in `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) and can currently support:

- audio setup and file management
- annotation workflow guidance
- cross-speaker analysis support
- export and downstream-pipeline assistance
- troubleshooting across the PARSE workflow

## Full built-in chat tool surface (50 tools)

The in-app assistant currently exposes **50 PARSE-specific tools**.

### Read-only / preview tools (15)

| Tool | Description |
|---|---|
| `project_context_read` | Full project metadata and speaker status |
| `speakers_list` | Enumerate annotated speakers for batch/preflight workflows |
| `annotation_read` | Read annotation data for a speaker, with optional tier/concept filtering |
| `pipeline_state_read` | Preflight one speaker's pipeline state with per-step `done` / `can_run`, coverage fields, counts, and reasons |
| `pipeline_state_batch` | Preflight multiple speakers and summarize blocked / partial-coverage speakers before a batch run |
| `cognate_compute_preview` | Preview cognate computation results |
| `cross_speaker_match_preview` | Preview cross-speaker matching candidates |
| `spectrogram_preview` | Generate a spectrogram preview for a segment |
| `read_audio_info` | Read WAV metadata such as duration, sample rate, channels, sample width, and file size |
| `read_csv_preview` | Preview a CSV file such as `concepts.csv` |
| `read_text_preview` | Preview Markdown/text files from the workspace or docs root |
| `parse_memory_read` | Read persistent chat memory from `parse-memory.md` |
| `enrichments_read` | Read computed enrichments with optional top-level filtering |
| `lexeme_notes_read` | Read stored lexeme notes with optional speaker/concept filtering |
| `phonetic_rules_apply` | Apply or inspect phonetic-rule normalization / equivalence logic |

### Job observability tools (4)

| Tool | Description |
|---|---|
| `jobs_list_active` | List active backend jobs so the in-app assistant can recover progress after reloads |
| `jobs_list` | List active or recent jobs with status / type / speaker filters |
| `job_status` | Read one generic job snapshot, including `errorCode`, progress, lock metadata, and log counts |
| `job_logs` | Read structured per-job logs and surfaced crash-log tails |

### Job-triggering tools (12)

| Tool | Description |
|---|---|
| `stt_start` | Start STT pipeline on a recording and return a job ID |
| `stt_status` | Poll the status of a running STT job |
| `compute_status` | Generic poller for compute jobs, including full-pipeline runs and step-level results |
| `audio_normalize_start` | Start audio normalization for one speaker |
| `audio_normalize_status` | Poll the status of a normalization job |
| `stt_word_level_start` | Start Tier 1 word-level STT with nested `segments[].words[]` spans |
| `stt_word_level_status` | Poll status/result of a Tier 1 word-level STT job |
| `forced_align_start` | Start Tier 2 acoustic forced alignment for one speaker |
| `forced_align_status` | Poll status/result of a Tier 2 forced-alignment job |
| `pipeline_run` | Start a one-speaker pipeline or ORTH-only run with explicit steps and overwrites |
| `ipa_transcribe_acoustic_start` | Start Tier 3 acoustic IPA transcription for one speaker |
| `ipa_transcribe_acoustic_status` | Poll status/result of a Tier 3 acoustic IPA job |

### Alignment / correction tools (3)

| Tool | Description |
|---|---|
| `detect_timestamp_offset` | Detect a constant timestamp offset between annotation data and audio/STT evidence |
| `detect_timestamp_offset_from_pair` | Compute an offset from one or more manually trusted CSV↔audio anchor pairs |
| `apply_timestamp_offset` | Apply a constant offset to lexeme timestamps for one speaker (`dryRun=true` first) |

### Tag operations (2)

| Tool | Description |
|---|---|
| `prepare_tag_import` | Validate and preview a tag CSV before import |
| `import_tag_csv` | Import tags from a prepared CSV file |

### Write / export / merge tools (14)

| Tool | Description |
|---|---|
| `contact_lexeme_lookup` | Fetch and optionally merge contact-language reference forms via the CLEF provider chain (`dryRun=true` first) |
| `onboard_speaker_import` | Copy external audio/CSV into the workspace, scaffold speaker state, and register it in `source_index.json` (`dryRun=true` first) |
| `import_processed_speaker` | Hydrate one speaker from existing processed artifacts into the active workspace (`dryRun=true` first) |
| `parse_memory_upsert_section` | Create or replace a `## Section` block in `parse-memory.md` (`dryRun=true` first) |
| `enrichments_write` | Shallow-merge or replace computed enrichments |
| `lexeme_notes_write` | Write or delete lexeme notes for a speaker/concept pair |
| `export_annotations_csv` | Export annotations as CSV (`speaker="all"` supported) |
| `export_lingpy_tsv` | Export a LingPy-compatible TSV wordlist |
| `export_nexus` | Export a NEXUS matrix for downstream phylogenetics |
| `export_annotations_elan` | Export annotations as ELAN XML |
| `export_annotations_textgrid` | Export annotations as Praat TextGrid |
| `transcript_reformat` | Reformat transcript files into PARSE-friendly structure |
| `peaks_generate` | Generate waveform peaks for one speaker/audio source |
| `source_index_validate` | Validate or build `source_index.json` entries / manifests |

## Tool-surface design constraints

The current README calls out two important operational boundaries:

- write-capable tools are intentionally gated
- onboarding is **one speaker at a time**

Multi-source speakers may still require manual or virtual-timeline coordination because PARSE does not yet auto-align multiple WAVs into a single shared annotation timeline.

### MCP workflow macros (3)

| Tool | Description |
|---|---|
| `run_full_annotation_pipeline` | Run STT → forced alignment → acoustic IPA for one speaker in one call |
| `prepare_compare_mode` | Build a compare-ready concept × speaker bundle with fresh preview data |
| `export_complete_lingpy_dataset` | Export LingPy TSV + NEXUS, optionally refreshing contact lexeme references first |

## MCP subset versus in-app tool surface

Not every in-app chat tool is exported over MCP, and MCP also exposes 3 workflow-only macros plus read-only `mcp_get_exposure_mode` outside the built-in 50-tool chat surface.

- **Built-in chat tools**: 50
- **Default MCP task tools**: 32
- **Default MCP adapter surface including workflow macros + `mcp_get_exposure_mode`**: 36
- **Full MCP adapter surface with `expose_all_tools=true`**: 54

Task 5 adds an HTTP MCP bridge on top of that same schema surface:
- `GET /api/mcp/exposure`
- `GET /api/mcp/tools`
- `GET /api/mcp/tools/{toolName}`
- `POST /api/mcp/tools/{toolName}`

That bridge reuses `ChatToolSpec` metadata (`parameters`, MCP annotations, and `meta.x-parse`) so external Python wrappers can discover the same tool contracts without spawning the stdio adapter.

For the exact MCP subset, startup instructions, and usage examples, see [API Reference](./api-reference.md).
