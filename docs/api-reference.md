# API Reference

> Last updated: 2026-04-29
>
> This page consolidates the current PARSE HTTP surface and MCP server mode. HTTP routes were cross-checked against `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`) and `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`); MCP tools were cross-checked against `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`).

## API overview

PARSE has three programmatic surfaces:

1. **HTTP API** — used by the browser frontend and any local automation that talks to `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)
2. **WebSocket job streaming** — additive realtime job updates from the sidecar in `python/external_api/streaming.py`
3. **MCP server mode** — used by external agent clients through the PARSE MCP adapter

### Base URLs

During active development:

- frontend: `http://localhost:5173`
- API backend: `http://localhost:8766`
- WebSocket sidecar: `ws://localhost:8767` (override with `PARSE_WS_PORT`)

In practice, the React app usually calls relative `/api/...` paths through the Vite proxy.

## HTTP API

### Response conventions

A few patterns recur across the API:

- job-start endpoints usually return `{ "jobId": "...", "status": "running" }`
- status endpoints typically accept either `jobId` or `job_id`
- generic job snapshots expose shared fields such as `type`, `status`, `progress`, `message`, `errorCode`, `logCount`, and `locks`
- heavy-job starters can optionally attach a `callbackUrl` so external automation can receive the final generic job payload on completion or error
- binary export/image endpoints return files rather than JSON
- compute endpoints normalize job handling across multiple background workflows
- `/api/config` carries a schema-versioned payload; if the config contract changes incompatibly, update the corresponding version constants in both `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) and `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`)

## WebSocket job streaming

WebSocket streaming is additive. Clients can continue polling `/api/stt/status`, `/api/compute/{type}/status`, or `/api/jobs/{jobId}` exactly as before.

### Endpoint

- `ws://<host>:<PARSE_WS_PORT or 8767>/ws/jobs/{jobId}`

### Event envelope

```json
{
  "event": "job.progress",
  "jobId": "stt-abc123",
  "type": "stt",
  "ts": "2026-04-24T22:30:00Z",
  "payload": {
    "progress": 42.5,
    "message": "Transcribing (17 segments)",
    "segmentsProcessed": 17,
    "totalSegments": 0
  }
}
```

### Current v1 event types

| Event | Purpose |
|---|---|
| `job.snapshot` | Initial job state sent immediately after subscribe |
| `job.progress` | Current public job payload after a progress/running update |
| `job.log` | One structured log entry from the job ring buffer |
| `stt.segment` | Provisional partial STT segment for in-flight decoding |
| `job.complete` | Terminal success payload |
| `job.error` | Terminal error payload |

### Notes

- `stt.segment` packets are provisional and meant for UX / agent steering.
- The persisted STT cache and final job `result` remain the canonical artifacts.
- Closely emitted events like `job.log` and `job.progress` may arrive in either order unless a stricter ordering contract is documented for that event pair.

## GET endpoints

### Core workspace data

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/config` | Read project configuration | Current config payload is wrapped and includes `schema_version: 1` |
| `GET /api/annotations/{speaker}` | Read one speaker annotation record | Resolves the requested speaker to the normalized annotation payload |
| `GET /api/stt-segments/{speaker}` | Read cached STT segments for a speaker | Returns `segments: []` when cache is missing rather than 404 |
| `GET /api/enrichments` | Read comparative enrichments | Returns `{ enrichments: ... }` |
| `GET /api/tags` | Read tag definitions and assignments | Shared across Annotate and Compare |
| `GET /api/clef/config` | Read CLEF language configuration | Returns primary contact languages plus saved catalog entries, including per-language `script` hints |
| `GET /api/clef/catalog` | Read bundled CLEF language catalog | Includes the SIL/ISO-backed picker data and ISO 15924 `script` hints for the Configure CLEF modal |
| `GET /api/clef/providers` | Read available CLEF providers | Returns provider keys, labels, and capability metadata for auto-populate setup |
| `GET /api/clef/sources-report` | Read CLEF provenance summary | Returns provider-attribution breakdowns and per-form source data for the Sources Report modal |
| `GET /api/jobs` | List recent backend jobs | Supports status / type / speaker filters and returns generic job snapshots |
| `GET /api/jobs/active` | List active backend jobs | Used to rehydrate progress after reload |
| `GET /api/jobs/{jobId}` | Read one backend job | Includes generic status, progress, `errorCode`, `logCount`, and lock metadata |
| `GET /api/jobs/{jobId}/logs` | Read structured logs for one backend job | Returns per-entry timestamps, levels, events, and crash-log tails when present |
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
| `POST /api/onboard/speaker` | Upload raw audio and optional CSV for one speaker | Multipart upload; Audition marker CSV/TSV fallback can seed `concept` and `ortho_words` intervals from `Name`/`Start` rows |
| `POST /api/onboard/speaker/status` | Poll onboarding job status | Background-job status endpoint |
| `POST /api/concepts/import` | Import concepts CSV | Multipart form upload |
| `POST /api/tags/import` | Import tags from CSV | Multipart form upload |
| `POST /api/lexeme-notes` | Write or delete a lexeme note | Writes into `parse-enrichments.json` |
| `POST /api/lexeme-notes/import` | Import lexeme notes/comments from CSV | Multipart form upload |

Audition marker CSV import details live in [Audition CSV speaker import](runtime/audition-csv-import.md). It preserves CSV row order and cue timestamps, resolves labels to integer PARSE concept ids before allocating new ids, writes concept + `ortho_words` intervals with `import_index` / `audition_prefix` trace metadata, and deliberately leaves `ortho`, `ipa`, and `bnd` for downstream jobs.

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
| `POST /api/clef/config` | Save CLEF language configuration | Used by the guided Configure CLEF modal before optional auto-populate |
| `POST /api/clef/clear` | Clear CLEF reference forms and optional provider caches | Operates only on per-language `config/sil_contact_languages.json[lang].concepts`; supports `dryRun`, language/concept scoping, and `clearCache` |
| `POST /api/clef/form-selections` | Save CLEF form selections | Persists which populated reference forms should contribute to similarity scoring |
| `POST /api/tags/merge` | Merge tag definitions | Shared tag persistence |
| `POST /api/offset/detect` | Detect a constant timestamp offset | Starts an async compute job with progress updates and crash-log capture |
| `POST /api/offset/detect-from-pair` | Detect a timestamp offset from trusted manual pairs | STT-free async correction path |
| `POST /api/offset/apply` | Apply a constant timestamp shift | Mutates the speaker annotation file while preserving manually adjusted / anchored lexemes |


Offset-apply responses include both `shiftedIntervals` (tier-interval count) and `shiftedConcepts` (distinct concept count). UI and external agents should prefer `shiftedConcepts` for human-facing summaries while preserving `shiftedIntervals` for backend/audit totals.

Use `POST /api/clef/clear` with `dryRun=true` first to preview the number of forms, languages, concepts, and cache entries that would be removed. The request body is:

```json
{
  "dryRun": false,
  "languages": ["ar", "fa"],
  "concepts": ["water"],
  "clearCache": false
}
```

`languages` and `concepts` may be `null` or omitted to select all configured languages/concepts. The response is always HTTP 200 for valid requests:

```json
{
  "ok": true,
  "dryRun": false,
  "summary": {
    "languagesAffected": 2,
    "conceptsAffected": 1,
    "formsRemoved": 3,
    "cacheFilesRemoved": 0
  },
  "warnings": []
}
```

A destructive run (`dryRun=false`) backs up `config/sil_contact_languages.json` as `sil_contact_languages.json.<utc-iso>.bak` using basic UTC ISO timestamps such as `sil_contact_languages.json.20260428T205100Z.bak`, even if no forms are removed. The clear only edits selected per-language `concepts` dictionaries; it preserves `_meta`, `name`, `family`, `script`, and other config keys. It does **not** touch `parse-enrichments.json` because CLEF reference forms do not live there. With `clearCache=true`, the backend removes known CLEF provider caches only from `config/cache/`: `wiktionary_*.json`, `wikidata_*.json`, `asjp_*.json`, and `cldf_*` cache directories.

Frontend note: current `src/api/contracts/clef-contact-lexeme.ts` has helpers for CLEF config/catalog/providers/sources/form selections but no `clearClefData()` helper yet. Browser UI work that calls this endpoint must add the helper first rather than using a bare `fetch()`.

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
| `boundaries` | `bnd`, `ortho_words`, `ortho-words` | Run standalone BND boundary refinement and write `tiers.ortho_words` |
| `retranscribe_with_boundaries` | `retranscribe-with-boundaries`, `boundary_constrained_stt`, `boundary-constrained-stt`, `bnd_stt` | Re-run STT using saved BND windows as authoritative segment boundaries |
| `full_pipeline` | `full-pipeline`, `pipeline` | Run the step-resilient full annotation pipeline |


`POST /api/compute/{computeType}` accepts optional scoped-pipeline fields for STT, ORTH, IPA, and full-pipeline workflows:

| Field | Shape | Notes |
|---|---|---|
| `run_mode` | `"full"` \| `"concept-windows"` \| `"edited-only"` | Optional; omitted means `"full"`. Non-full modes process concept-tier windows instead of the whole speaker. |
| `concept_ids` | `string[]` | Optional explicit concept scope for non-full modes. `edited-only` additionally filters to concept intervals with `manuallyAdjusted === true`. |

Non-full responses include `run_mode`, `concept_windows`, and `affected_concepts` (`[{ concept_id, start, end }]`) when concept rows were processed. An `edited-only` run with no matching concepts returns a structured no-op (`no_op: true`, `jobId: null`, `affected_concepts: []`) rather than starting an empty job.

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

To subscribe to realtime updates for the started job, connect to:

```text
ws://localhost:8767/ws/jobs/stt-abc123
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

### Start a pipeline run (full or scoped)

```http
POST /api/compute/full_pipeline
Content-Type: application/json

{
  "speaker": "Fail02",
  "run_mode": "concept-windows",
  "concept_ids": ["1", "2"]
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

For scoped runs, `result` also includes `run_mode`, `concept_windows`, and `affected_concepts`; full-speaker runs preserve the legacy response shape.

### Download exports

```http
GET /api/export/lingpy
GET /api/export/nexus
```

Both endpoints return downloadable file content rather than JSON.

## OpenAPI 3.1 and interactive API docs

PARSE now serves a machine-readable OpenAPI 3.1 document directly from `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`).

| Endpoint | Purpose |
|---|---|
| `GET /openapi.json` | Full OpenAPI 3.1 spec for the HTTP API + HTTP MCP bridge |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc |

The OpenAPI document intentionally describes the HTTP workstation API and the HTTP MCP bridge. The stdio MCP adapter remains documented separately below because it is a process transport, not an HTTP route.

## HTTP MCP bridge

Task 5 adds a discovery/execution bridge so external Python tooling can use the PARSE MCP schema without spawning the stdio adapter.

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/mcp/exposure` | Read active MCP exposure configuration | Supports `mode=active|default|all` |
| `GET /api/mcp/tools` | List MCP-visible tool schemas | Returns `parameters`, `annotations`, and `meta.x-parse` |
| `GET /api/mcp/tools/{toolName}` | Read one MCP tool schema | 404 if hidden in the selected mode |
| `POST /api/mcp/tools/{toolName}` | Execute one MCP-visible tool over HTTP | Uses the same validation + execution layer as the PARSE tool runtime |

### Exposure modes

`mode` query parameter accepts:
- `active` — obey `config/mcp_config.json` (or fallback root `mcp_config.json`)
- `default` — force the shipped default 59-tool surface
- `all` — force the full tool surface (currently also 59 tools unless a future explicit all-only surface diverges)

### Tool schema payload

Each tool entry returned by the bridge includes:
- `name`
- `family`
  - `adapter`
  - `chat`
  - `workflow`
- `description`
- `parameters`
- `annotations`
- `meta.x-parse`

`meta.x-parse` remains the key safety payload for agents. It includes:
- `mutability`
- `supports_dry_run`
- `dry_run_parameter`
- `preconditions`
- `postconditions`

## MCP server mode

PARSE can also run as a stdio MCP server by exposing the shipped **55-tool** `ParseChatTools` default plus the **3** workflow macros through `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`). Read-only `mcp_get_exposure_mode` is added by the adapter itself, so the default published MCP surface is **59 tools** total and the `expose_all_tools=true` surface is also **59**. Explicit `config/mcp_config.json` → `{ "expose_all_tools": false }` keeps the legacy curated 36-tool subset, which still becomes **40** adapter tools once the 3 workflow macros and adapter helper are included.

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

## Legacy curated MCP task surface (36 `ParseChatTools` + 3 workflow macros; 40 adapter tools including `mcp_get_exposure_mode`)

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
| `compute_boundaries_start` | Start standalone BND refinement and write `tiers.ortho_words` from cached Tier 1 word timestamps |
| `compute_boundaries_status` | Poll standalone BND refinement status |
| `retranscribe_with_boundaries_start` | Start boundary-constrained STT from saved BND windows |
| `retranscribe_with_boundaries_status` | Poll boundary-constrained STT status |
| `ipa_transcribe_acoustic_start` | Start Tier 3 acoustic IPA |
| `ipa_transcribe_acoustic_status` | Poll Tier 3 acoustic IPA status |
| `pipeline_run` | Start a one-speaker full pipeline or step-subset run |
| `compute_status` | Poll any compute job |

### Job observability

| Tool | Description |
|---|---|
| `jobs_list` | List active or recent jobs with optional status / type / speaker filters |
| `job_status` | Read one generic job snapshot, including `errorCode`, progress, `logCount`, and lock metadata |
| `job_logs` | Read structured per-job logs and surfaced crash-log tails |

### Alignment / correction

| Tool | Description |
|---|---|
| `detect_timestamp_offset` | Detect a constant timestamp offset from annotation↔audio/STT evidence |
| `detect_timestamp_offset_from_pair` | Detect an offset from trusted manual anchor pairs |
| `apply_timestamp_offset` | Apply a constant shift to speaker timestamps |

`bnd_stt` is worth calling out here because PR notes often name it explicitly: it is a compute-type alias for the HTTP/background job path above, not a separately registered MCP tool name. External agents should call `retranscribe_with_boundaries_start` over MCP and use `bnd_stt` only when driving `/api/compute/{type}` or worker aliases directly.

### Write / import / curation

| Tool | Description |
|---|---|
| `contact_lexeme_lookup` | Fetch contact-language reference forms; dry-run first |
| `clef_clear_data` | MCP wrapper for `POST /api/clef/clear`; clears per-language `concepts` entries in `config/sil_contact_languages.json`, preserves `_meta`, and optionally removes known provider caches |
| `import_tag_csv` | Import a CSV as a PARSE tag list |
| `prepare_tag_import` | Preview and validate a tag import |
| `onboard_speaker_import` | Import one speaker from on-disk audio/CSV into the workspace |
| `import_processed_speaker` | Import one speaker from existing processed artifacts |
| `parse_memory_upsert_section` | Upsert a `## Section` block in `parse-memory.md` |

### Workflow macros

| Tool | Description |
|---|---|
| `run_full_annotation_pipeline` | Run the annotation pipeline for one speaker; supports `run_mode` (`full`, `concept-windows`, `edited-only`) and optional `concept_ids` |
| `prepare_compare_mode` | Resolve a concept slice across speakers and return a compare-ready preview bundle |
| `export_complete_lingpy_dataset` | Export LingPy TSV + NEXUS, optionally refreshing contact lexeme references first |

`jobs_list_active` remains an in-app assistant helper, but the MCP/default external surface now uses the generic `jobs_list` / `job_status` / `job_logs` trio so agents can inspect both active and recent work consistently.

## `parse-mcp` Python package

Task 5 adds the official package scaffold under:

- `python/packages/parse_mcp/`
- package name: **`parse-mcp`**

It provides:
- `ParseMcpClient` for discovery + execution against the HTTP MCP bridge
- `build_langchain_tools(...)`
- `build_llamaindex_tools(...)`
- `build_crewai_tools(...)`

## Authentication model

### HTTP transport auth
PARSE's local HTTP surface is not bearer-protected today. It is intended for a local workstation deployment on `localhost` / `127.0.0.1`.

### Provider credentials
Provider credentials are managed locally through:
- `GET /api/auth/status`
- `POST /api/auth/key`
- `POST /api/auth/start`
- `POST /api/auth/poll`
- `POST /api/auth/logout`

Credentials are stored in local `config/auth_tokens.json`.

### MCP process auth
The stdio MCP adapter does not add a separate network auth layer. Access is governed by the local process launch context and environment variables such as:
- `PARSE_PROJECT_ROOT`
- `PARSE_EXTERNAL_READ_ROOTS`
- `PARSE_CHAT_MEMORY_PATH`
- `PARSE_API_PORT`
- `PARSE_PORT`

## MCP usage notes

The shipped MCP default exposes the full safe 55-tool PARSE task surface plus 3 high-level workflow macros and `mcp_get_exposure_mode`; `expose_all_tools=false` is the legacy curated opt-out.

Operational rules that remain important:
- use `dryRun=true` first for gated mutating tools such as `contact_lexeme_lookup`, `clef_clear_data`, `onboard_speaker_import`, and timestamp/application workflows
- prefer `full_coverage` rather than bare `done` when making automation decisions about whether a tier really covers the full recording
- onboarding remains **one speaker at a time**

## Related docs

- External agent onboarding: [Getting Started with External Agents](./getting-started-external-agents.md)
- Provider and model overview: [AI Integration](./ai-integration.md)
- User-facing workflow context: [User Guide](./user-guide.md)
- Data model and system design: [Architecture](./architecture.md)
- Schema/auth details: [MCP Schema](./mcp-schema.md)
