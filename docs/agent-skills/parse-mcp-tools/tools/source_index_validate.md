---
name: parse-mcp-tool-source-index-validate
description: "Use PARSE MCP tool `source_index_validate`: Validate a speaker manifest entry or full manifest against the SourceIndex schema. Two modes:\n  speaker — validate + transform one speaker entry; returns errors and transformed shape\n  full    — validate + build the complete source_index.json; optionally write to outputPath inside the project"
version: 1.0.0
source: PARSE MCP catalog
source_generated_at: 2026-05-10T17:37:02Z
license: MIT
tags:
  - parse
  - mcp
  - tool
  - chat
---

# PARSE MCP Tool Skill — `source_index_validate`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `source_index_validate` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `source_index_validate`
- **Skill name:** `parse-mcp-tool-source-index-validate`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** None
- **`additionalProperties`:** `False`
- **Catalog description:** Validate a speaker manifest entry or full manifest against the SourceIndex schema. Two modes:
  speaker — validate + transform one speaker entry; returns errors and transformed shape
  full    — validate + build the complete source_index.json; optionally write to outputPath inside the project

### Parameters

- `mode` (type=string; enum=`speaker`, `full`) — Validation scope (default: speaker).
- `speakerId` (type=string; minLength=1; maxLength=200) — Speaker ID (required for mode=speaker).
- `speakerData` (type=object) — Speaker manifest entry to validate (required for mode=speaker).
- `manifest` (type=object) — Full manifest with top-level 'speakers' key (required for mode=full).
- `outputPath` (type=string; minLength=1; maxLength=512) — Write built source_index.json here (mode=full only, project-relative or absolute inside project).
- `dryRun` (type=boolean) — If true, never writes outputPath even when provided; returns the validated/constructed payload only.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)

### Postconditions advertised by catalog

- When the tool is not in preview mode, it writes or updates a project artifact. (`filesystem_write`, `required`)

## Portable setup

Use placeholders instead of machine-specific paths:

```bash
cd <PARSE_REPO>
export PARSE_PROJECT_ROOT=<PROJECT_ROOT>
# Optional when input files live outside the PARSE project root:
export PARSE_EXTERNAL_READ_ROOTS=<ABSOLUTE_READ_ROOT_1>[:<ABSOLUTE_READ_ROOT_2>]
PYTHONPATH=python python3 -m adapters.mcp_adapter --project-root "$PARSE_PROJECT_ROOT"
```

For the HTTP MCP bridge, discover the live schema before calling:

```bash
curl "$PARSE_BASE_URL/api/mcp/tools/source_index_validate?mode=active"
```

## Workflow

1. **Discover** – Confirm `source_index_validate` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Worked example

A `speakerData` object must carry a non-empty `wav_files` list plus speaker-level fields such as `has_csv`:

```json
{
  "mode": "speaker",
  "speakerId": "Speaker01",
  "speakerData": {
    "wav_files": [
      {
        "path": "audio/original/Speaker01/source.wav",
        "duration_sec": 12.34,
        "file_size_bytes": 123456,
        "bit_depth": 16,
        "sample_rate": 16000,
        "channels": 1,
        "is_primary": true,
        "lexicon_start_sec": 0.0
      }
    ],
    "has_csv": true,
    "notes": "Optional source-index note"
  }
}
```

For `mode: "full"`, wrap the same speaker entries under top-level `manifest.speakers`; use `dryRun: true` when you only want the constructed payload and not an `outputPath` write:

```json
{
  "mode": "full",
  "manifest": {
    "speakers": {
      "Speaker01": {
        "wav_files": [
          {
            "path": "audio/original/Speaker01/source.wav",
            "duration_sec": 12.34,
            "file_size_bytes": 123456,
            "bit_depth": 16,
            "sample_rate": 16000,
            "channels": 1,
            "is_primary": true,
            "lexicon_start_sec": 0.0
          }
        ],
        "has_csv": true
      }
    }
  },
  "outputPath": "source_index.json",
  "dryRun": true
}
```

Typical speaker-mode validation response:

```json
{
  "tool": "source_index_validate",
  "ok": true,
  "result": {
    "readOnly": true,
    "mode": "speaker",
    "speakerId": "Speaker01",
    "valid": true,
    "errors": [],
    "transformed": {
      "source_wavs": [
        {
          "filename": "audio/original/Speaker01/source.wav",
          "duration_sec": 12.34,
          "file_size_bytes": 123456,
          "bit_depth": 16,
          "sample_rate": 16000,
          "channels": 1,
          "lexicon_start_sec": 0.0,
          "is_primary": true
        }
      ],
      "peaks_file": "peaks/Speaker01.json",
      "transcript_file": "coarse_transcripts/Speaker01.json",
      "has_csv": true,
      "notes": "Optional source-index note"
    },
    "previewOnly": true
  }
}
```

## Quality checklist

- [ ] Live catalog confirms `source_index_validate` is currently exposed.
- [ ] The current live schema was inspected before constructing arguments.
- [ ] Required arguments were provided and optional result limits were bounded.
- [ ] Dry-run/preview was used first when advertised by the catalog.
- [ ] Any returned `jobId` was polled to terminal state.
- [ ] Any file mutation was independently audited after apply.
- [ ] Evidence recorded the exact argument shape, result summary, and verification path.

## Anti-patterns

- Calling internal helper functions and presenting that as MCP validation.
- Running `python/adapters/mcp_adapter.py` by file path; use `PYTHONPATH=python python3 -m adapters.mcp_adapter`.
- Copying local workstation paths into reusable docs, scripts, or handoffs.
- Treating `ok: true`, preview counts, or dry-run output as proof of durable file mutation.
- Auditing legacy `annotations/<Speaker>.json` when active `.parse.json` annotations exist.
- Reporting before a started job reaches terminal state.
