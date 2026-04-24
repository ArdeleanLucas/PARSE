# API Reference

> Last updated: 2026-04-24
>
> This page consolidates the current PARSE HTTP surface and MCP server mode. HTTP routes were cross-checked against `src/api/client.ts` and `python/server.py`; MCP tools were cross-checked against `python/adapters/mcp_adapter.py`.

## API overview

PARSE has two programmatic surfaces:

1. **HTTP API** — used by the browser frontend and any local automation that talks to `python/server.py`
2. **MCP server mode** — used by external agent clients through the PARSE MCP adapter

### Base URLs

During active development:

- frontend: `http://localhost:5173`
- API backend: `http://localhost:8766`

In practice, the React app usually calls relative `/api/...` paths through the Vite proxy.

## HTTP API

### Response conventions

A few patterns recur across the API:

- job-start endpoints usually return `{ "jobId": "...", "status": "running" }`
- status endpoints typically accept either `jobId` or `job_id`
- binary export/image endpoints return files rather than JSON
- compute endpoints normalize job handling across multiple background workflows
- `/api/config` carries a schema-versioned payload; if the config contract changes incompatibly, update the corresponding version constants in both `python/server.py` and `src/api/client.ts`

## GET endpoints

### Core workspace data

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/config` | Read project configuration | Current config payload is wrapped and includes `schema_version: 1` |
| `GET /api/annotations/{speaker}` | Read one speaker annotation record | Resolves the requested speaker to the normalized annotation payload |
| `GET /api/stt-segments/{speaker}` | Read cached STT segments for a speaker | Returns `segments: []` when cache is missing rather than 404 |
| `GET /api/enrichments` | Read comparative enrichments | Returns `{ enrichments: ... }` |
| `GET /api/tags` | Read tag definitions and assignments | Shared across Annotate and Compare |
| `GET /api/jobs/active` | List active backend jobs | Used to rehydrate progress after reload |
| `GET /api/pipeline/state/{speaker}` | Read coverage-aware pipeline state | Includes `full_coverage` metadata per step |
| `GET /api/chat/session/{sessionId}` | Read one chat session | Returns message history and token metadata |

### Search, analysis, and media

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/lexeme/search` | Rank candidate time ranges for a lexeme/concept | User-facing endpoint behind Search & anchor lexeme |
| `GET /api/spectrogram` | Return or generate a PNG spectrogram for a clip | Cached on disk; returns `image/png` |
| `GET /api/contact-lexemes/coverage` | Inspect CLEF provider coverage | Used by the Compare CLEF workflow |

### Auth, exports, and worker health

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/auth/status` | Read auth provider status | Used by provider-auth UI state |
| `GET /api/export/lingpy` | Download LingPy TSV export | Returns a file/blob, not JSON |
| `GET /api/export/nexus` | Download NEXUS export | Returns a file/blob, not JSON |
| `GET /api/worker/status` | Health-check the persistent compute worker | Returns mode info in every case; returns a real liveness probe when persistent-worker mode is active |

## POST endpoints

### Annotation, onboarding, and speaker data

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /api/annotations/{speaker}` | Save one speaker annotation record | Writes normalized annotation JSON |
| `POST /api/onboard/speaker` | Upload raw audio and optional CSV for one speaker | Multipart upload |
| `POST /api/onboard/speaker/status` | Poll onboarding job status | Background-job status endpoint |
| `POST /api/concepts/import` | Import concepts CSV | Multipart form upload |
| `POST /api/tags/import` | Import tags from CSV | Multipart form upload |
| `POST /api/lexeme-notes` | Write or delete a lexeme note | Writes into `parse-enrichments.json` |
| `POST /api/lexeme-notes/import` | Import lexeme notes/comments from CSV | Multipart form upload |

### Audio, STT, and compute jobs

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /api/normalize` | Start audio normalization | ffmpeg loudnorm pipeline |
| `POST /api/normalize/status` | Poll normalization status | Job polling |
| `POST /api/stt` | Start STT | Accepts `speaker`, `sourceWav` / `source_wav`, optional `language` |
| `POST /api/stt/status` | Poll STT status | Accepts `jobId` or `job_id` |
| `POST /api/compute/{computeType}` | Start a compute job | Main dispatcher for ORTH, IPA, full pipeline, contact lexemes, etc. |
| `POST /api/compute/{computeType}/status` | Poll a typed compute job | Verifies the job matches the compute type |
| `POST /api/compute/status` | Poll a compute job without specifying a type | Generic polling alias |
| `POST /api/{computeType}/status` | Compatibility alias for compute status | Used for compute-style status endpoints other than STT |

### Suggestions, chat, and auth

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /api/suggest` | Request annotation suggestions | Concept-scoped suggestion workflow |
| `POST /api/chat/session` | Create or resume a chat session | Returns normalized `sessionId` / `session_id` |
| `POST /api/chat/run` | Start a chat run | Returns a job ID |
| `POST /api/chat/run/status` | Poll chat run status | Background-job polling |
| `POST /api/auth/key` | Save an API key for a provider | Provider-scoped credential save |
| `POST /api/auth/start` | Start OAuth/device auth flow | Provider auth initiation |
| `POST /api/auth/poll` | Poll OAuth/device auth flow | Normalized status: pending/complete/expired/error |
| `POST /api/auth/logout` | Clear auth credentials | Logout endpoint |

### Comparative data and workflow correction

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /api/enrichments` | Save enrichments | Accepts either `{ enrichments: ... }` or the raw object |
| `POST /api/config` | Update project configuration | Current server accepts POST as an update path |
| `POST /api/tags/merge` | Merge tag definitions | Shared tag persistence |
| `POST /api/offset/detect` | Detect a constant timestamp offset | Supports STT-based alignment checks |
| `POST /api/offset/detect-from-pair` | Detect a timestamp offset from trusted manual pairs | STT-free correction path |
| `POST /api/offset/apply` | Apply a constant timestamp shift | Mutates the speaker annotation file |

## PUT endpoints

| Endpoint | Purpose | Notes |
|---|---|---|
| `PUT /api/config` | Update project configuration | Same underlying update handler as POST `/api/config` |

## Compute types

The compute dispatcher normalizes several named background workflows.

| Compute type | Accepted aliases | Purpose |
|---|---|---|
| `contact-lexemes` | — | Start a CLEF contact-lexeme fetch/merge job |
| `ipa_only` | `ipa-only`, `ipa` | Run Tier 3 acoustic IPA fill |
| `ortho` | `ortho_only`, `ortho-only` | Run speaker-level ORTH transcription |
| `forced_align` | `forced-align`, `align` | Run Tier 2 forced alignment |
| `full_pipeline` | `full-pipeline`, `pipeline` | Run the step-resilient full annotation pipeline |

## Example requests and responses

### Start STT

```http
POST /api/stt
Content-Type: application/json

{
  "speaker": "Fail02",
  "source_wav": "audio/working/Fail02/Fail02.wav",
  "language": "ku"
}
```

Example response:

```json
{
  "jobId": "stt-abc123",
  "status": "running"
}
```

### Poll STT status

```http
POST /api/stt/status
Content-Type: application/json

{
  "job_id": "stt-abc123"
}
```

Example shape:

```json
{
  "status": "running",
  "progress": 42.0,
  "message": "Transcribing (18 segments)"
}
```

### Read pipeline state

```http
GET /api/pipeline/state/Fail02
```

Example shape:

```json
{
  "speaker": "Fail02",
  "duration_sec": 10432.11,
  "normalize": {
    "done": true,
    "can_run": true,
    "reason": null,
    "path": "audio/working/Fail02/Fail02.wav"
  },
  "stt": {
    "done": true,
    "can_run": true,
    "reason": null,
    "coverage_fraction": 0.98,
    "full_coverage": true,
    "segments": 412
  }
}
```

### Search for lexeme candidates

```http
GET /api/lexeme/search?speaker=Fail02&variants=yek,yak,jek&concept_id=1&tiers=ortho_words,ortho,stt,ipa&limit=10
```

Example shape:

```json
{
  "speaker": "Fail02",
  "concept_id": "1",
  "variants": ["yek", "yak", "jek"],
  "language": "ku",
  "candidates": [
    {
      "start": 312.41,
      "end": 313.87,
      "tier": "ortho_words",
      "matched_text": "yek",
      "matched_variant": "yek",
      "score": 0.92,
      "phonetic_score": 0.88,
      "cross_speaker_score": 0.12,
      "confidence_weight": 0.84,
      "source_label": "ortho_words"
    }
  ],
  "signals_available": {
    "phonemizer": true,
    "cross_speaker_anchors": 6,
    "contact_variants": ["yak"]
  }
}
```

### Start a full pipeline run

```http
POST /api/compute/full_pipeline
Content-Type: application/json

{
  "speaker": "Fail02"
}
```

Example response:

```json
{
  "jobId": "compute-full-pipeline-xyz789",
  "status": "running"
}
```

### Poll a compute job

```http
POST /api/compute/full_pipeline/status
Content-Type: application/json

{
  "job_id": "compute-full-pipeline-xyz789"
}
```

Example shape:

```json
{
  "status": "complete",
  "progress": 100,
  "message": "Pipeline finished",
  "result": {
    "speaker": "Fail02",
    "steps_run": ["normalize", "stt", "ortho", "ipa"],
    "summary": {
      "ok": 4,
      "skipped": 0,
      "error": 0
    }
  }
}
```

### Download exports

```http
GET /api/export/lingpy
GET /api/export/nexus
```

Both endpoints return downloadable file content rather than JSON.

## MCP server mode

PARSE can run as an MCP server by exposing a curated subset of `ParseChatTools` through `python/adapters/mcp_adapter.py`.

### Start the adapter

```bash
python python/adapters/mcp_adapter.py
python python/adapters/mcp_adapter.py --project-root /path/to/project
python python/adapters/mcp_adapter.py --verbose
```

### Requirement

```bash
pip install 'mcp[cli]'
```

### Example client configuration

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

If no explicit environment block is passed, the adapter also reads repo-local overrides from `.parse-env`.

## Full MCP tool surface (32 tools)

### Inspection / preview / preflight

| Tool | Description |
|---|---|
| `project_context_read` | Project metadata, source index summary, annotation inventory, enrichments summary |
| `annotation_read` | Read speaker annotation data with optional concept/tier filtering |
| `read_csv_preview` | Preview CSV files and sample rows |
| `cognate_compute_preview` | Compute a read-only cognate/similarity preview |
| `cross_speaker_match_preview` | Read cross-speaker match candidates from STT output |
| `spectrogram_preview` | Generate a time-bounded spectrogram preview |
| `parse_memory_read` | Read persistent PARSE chat memory |
| `speakers_list` | Enumerate speakers for batch/preflight workflows |
| `pipeline_state_read` | Read one speaker's coverage-aware pipeline state |
| `pipeline_state_batch` | Read preflight state for multiple speakers |

### Job control

| Tool | Description |
|---|---|
| `stt_start` | Start STT on a project audio file |
| `stt_status` | Poll STT job status |
| `stt_word_level_start` | Start Tier 1 word-level STT |
| `stt_word_level_status` | Poll Tier 1 word-level STT status |
| `forced_align_start` | Start Tier 2 forced alignment |
| `forced_align_status` | Poll forced-alignment status |
| `ipa_transcribe_acoustic_start` | Start Tier 3 acoustic IPA |
| `ipa_transcribe_acoustic_status` | Poll Tier 3 acoustic IPA status |
| `pipeline_run` | Start a one-speaker full pipeline or step-subset run |
| `compute_status` | Poll any compute job |

### Alignment / correction

| Tool | Description |
|---|---|
| `detect_timestamp_offset` | Detect a constant timestamp offset from annotation↔audio/STT evidence |
| `detect_timestamp_offset_from_pair` | Detect an offset from trusted manual anchor pairs |
| `apply_timestamp_offset` | Apply a constant shift to speaker timestamps |

### Write / import / curation

| Tool | Description |
|---|---|
| `contact_lexeme_lookup` | Fetch contact-language reference forms; dry-run first |
| `import_tag_csv` | Import a CSV as a PARSE tag list |
| `prepare_tag_import` | Preview and validate a tag import |
| `onboard_speaker_import` | Import one speaker from on-disk audio/CSV into the workspace |
| `import_processed_speaker` | Import one speaker from existing processed artifacts |
| `parse_memory_upsert_section` | Upsert a `## Section` block in `parse-memory.md` |

### Workflow macros

| Tool | Description |
|---|---|
| `run_full_annotation_pipeline` | Run STT → forced alignment → acoustic IPA for one speaker in one call |
| `prepare_compare_mode` | Resolve a concept slice across speakers and return a compare-ready preview bundle |
| `export_complete_lingpy_dataset` | Export LingPy TSV + NEXUS, optionally refreshing contact lexeme references first |

## MCP usage notes

The MCP surface is a curated subset of the low-level chat tools plus 3 high-level workflow macros.

A few operational rules remain important:

- use `dryRun=true` first for gated mutating tools such as `contact_lexeme_lookup`, `onboard_speaker_import`, and timestamp/application workflows
- prefer `full_coverage` rather than bare `done` when making automation decisions about whether a tier really covers the full recording
- onboarding remains **one speaker at a time**

## Related docs

- Provider and model overview: [AI Integration](./ai-integration.md)
- User-facing workflow context: [User Guide](./user-guide.md)
- Data model and system design: [Architecture](./architecture.md)
