# MCP schema and authentication model

This document describes the standardized external-agent surface added in Task 5.

## External surfaces

PARSE now exposes three closely related machine-facing surfaces:

1. **HTTP API** on port `8766`
   - browser workstation backend
   - documented via OpenAPI 3.1
2. **HTTP MCP bridge** on the same server
   - schema discovery and tool execution for Python wrappers
3. **stdio MCP adapter**
   - `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`)
   - for Claude Code, Cursor, Codex, Cline, Hermes, Windsurf, and other MCP-capable clients

## OpenAPI endpoints

- `GET /openapi.json`
- `GET /docs`
- `GET /redoc`

## HTTP MCP bridge endpoints

- `GET /api/mcp/exposure`
  - returns the active exposure configuration and tool counts
- `GET /api/mcp/tools`
  - returns the active tool catalog with full parameter schemas, annotations, and `x-parse` safety metadata
- `GET /api/mcp/tools/{toolName}`
  - returns one tool schema
- `POST /api/mcp/tools/{toolName}`
  - executes one MCP-visible PARSE tool via HTTP

### Exposure modes

`mode` query parameter accepts:
- `active` — obey `config/mcp_config.json` / `mcp_config.json`
- `default` — use the curated MCP subset
- `all` — expose the full tool surface

## Tool schema shape

Each listed tool includes:
- `name`
- `family`
  - `adapter`
  - `chat`
  - `workflow`
- `description`
- `parameters`
  - strict JSON schema derived from `ChatToolSpec.parameters`
- `annotations`
  - standard MCP hints such as `readOnlyHint`
- `meta.x-parse`
  - PARSE-specific safety metadata:
    - `mutability`
    - `supports_dry_run`
    - `dry_run_parameter`
    - `preconditions`
    - `postconditions`

## Authentication model

### HTTP API transport auth
PARSE's local HTTP API is **not bearer-protected** today. It is designed for local workstation use on `127.0.0.1:8766` / `localhost:8766` with permissive CORS for the browser UI and local automation.

### Provider credential auth
Provider credentials are managed locally through:
- `GET /api/auth/status`
- `POST /api/auth/key`
- `POST /api/auth/start`
- `POST /api/auth/poll`
- `POST /api/auth/logout`

Supported auth methods currently include:
- direct API-key storage for xAI/OpenAI-style providers
- OpenAI device/OAuth flow

Credentials are stored in local `config/auth_tokens.json` and mirrored into the live process environment when needed.

### MCP auth
The stdio MCP adapter does not add a separate network auth layer. Access is controlled by the local process launch context and environment, especially:
- `PARSE_PROJECT_ROOT`
- `PARSE_EXTERNAL_READ_ROOTS`
- `PARSE_CHAT_MEMORY_PATH`
- `PARSE_API_PORT`
- `PARSE_PORT`

## Recommended external-agent workflow

1. Read `GET /api/mcp/exposure`
2. Discover tools from `GET /api/mcp/tools`
3. Inspect `meta.x-parse.preconditions` and `supports_dry_run`
4. Prefer `dryRun=true` for mutating tools when available
5. Execute via `POST /api/mcp/tools/{toolName}`
6. Use normal HTTP endpoints or MCP-specific polling/status helpers as needed
