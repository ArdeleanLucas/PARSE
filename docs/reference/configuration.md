# Configuration options

PARSE keeps shared defaults in tracked files and machine-local choices in untracked local configuration.

## Main files

| File | Purpose |
|---|---|
| `config/ai_config.example.json` | Tracked template for local AI/model/provider settings. |
| `config/ai_config.json` | Machine-local AI configuration; intentionally gitignored. |
| `config/mcp_config.example.json` | Template for MCP exposure settings. |
| `config/mcp_config.json` | Machine-local MCP exposure config. |
| `.parse-env` | Optional launcher environment overrides loaded outside git when present. |

## Environment overrides
Environment variables are the preferred way to change launch ports, workspace roots, compute mode, chunk duration, subprocess timeout, and CPU/GPU placement without editing tracked files. See [Environment variables](environment-variables.md).

## Workspace roots
Use `PARSE_WORKSPACE_ROOT` for real fieldwork data so generated annotations, peaks, transcripts, enrichments, and job snapshots live outside the repository checkout.

## Device and model settings
Model paths and provider defaults generally belong in `config/ai_config.json`; temporary CPU/GPU choices belong in environment variables such as `PARSE_COMPUTE_DEVICE` or `PARSE_STT_DEVICE`.

## MCP exposure
MCP tools are exposed through the shipped default surface unless `config/mcp_config.json` changes the exposure mode. See [MCP schema](../mcp/schema.md).
