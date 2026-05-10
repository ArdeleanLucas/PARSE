---
name: parse-mcp-tool-onboard-speaker-import
description: "Use PARSE MCP tool `onboard_speaker_import`: Import a speaker's audio source from on-disk paths (and optional transcription CSV). Copies files into audio/original/<speaker>/, scaffolds an annotation record on the first import, and appends the source to source_index.json. sourceWav/sourceCsv may be absolute paths under PARSE_EXTERNAL_READ_ROOTS (set to '*' for no sandbox) or paths under the project audio/ directory. Multi-source speakers: call this tool once per audio source. The first import defaults to is_primary=true; subsequent imports default to is_primary=false. When a speaker already has registered sources, the response flags `virtualTimelineRequired=true` — PARSE does not yet auto-align multiple WAVs across a shared virtual timeline, so annotation spanning them must be coordinated manually or deferred. Gated by dryRun: call dryRun=true first to preview planned copies/registrations, then dryRun=false after the user confirms."
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

# PARSE MCP Tool Skill — `onboard_speaker_import`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `onboard_speaker_import` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `onboard_speaker_import`
- **Skill name:** `parse-mcp-tool-onboard-speaker-import`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `speaker`, `sourceWav`, `dryRun`
- **`additionalProperties`:** `False`
- **Catalog description:** Import a speaker's audio source from on-disk paths (and optional transcription CSV). Copies files into audio/original/<speaker>/, scaffolds an annotation record on the first import, and appends the source to source_index.json. sourceWav/sourceCsv may be absolute paths under PARSE_EXTERNAL_READ_ROOTS (set to '*' for no sandbox) or paths under the project audio/ directory. Multi-source speakers: call this tool once per audio source. The first import defaults to is_primary=true; subsequent imports default to is_primary=false. When a speaker already has registered sources, the response flags `virtualTimelineRequired=true` — PARSE does not yet auto-align multiple WAVs across a shared virtual timeline, so annotation spanning them must be coordinated manually or deferred. Gated by dryRun: call dryRun=true first to preview planned copies/registrations, then dryRun=false after the user confirms.

### Parameters

- `speaker` (type=string; minLength=1; maxLength=200) — Speaker ID to create or extend in the current project.
- `sourceWav` (type=string; minLength=1; maxLength=1024) — Absolute or project-relative path to the source audio file to copy into the workspace.
- `sourceCsv` (type=string; maxLength=1024) — Optional transcript CSV to store alongside the imported source WAV.
- `isPrimary` (type=boolean) — Flag this WAV as the speaker's primary source. Defaults to true when the speaker has no existing sources.
- `dryRun` (type=boolean) — If true, preview only — no file copies or source_index.json writes.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- The sourceWav path must resolve to a readable audio file within the allowed import roots. (`file_presence`, `required`)

### Postconditions advertised by catalog

- When dryRun=false, the source audio is copied into the workspace and source_index.json / project metadata are updated. (`filesystem_write`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/onboard_speaker_import?mode=active"
```

## Workflow

1. **Discover** – Confirm `onboard_speaker_import` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Quality checklist

- [ ] Live catalog confirms `onboard_speaker_import` is currently exposed.
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
