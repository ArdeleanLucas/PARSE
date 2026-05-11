# mcp_get_exposure_mode

**Category:** Project
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~150 (short) / ~320 (full)

## One-Sentence Summary
Reads the active MCP exposure mode, config source, and tool counts — the diagnostic probe for "which tool surface am I talking to?".

## When to Use
- Verifying the MCP adapter is exposing the expected tool surface (full default vs. legacy opt-out vs. custom).
- Diagnosing missing tools — if a tool should be available but isn't, this confirms the active mode.
- Integration tests and capability checks against the catalog.
- After changing exposure config (e.g. setting `expose_all_tools=false`) to confirm the change took effect.

## When NOT to Use
- To inspect individual tool schemas — use the HTTP MCP bridge endpoint `GET /api/mcp/tools/<toolName>?mode=active` for that.
- To list every exposed tool by name — use `GET /api/mcp/tools?mode=active` (HTTP) or the catalog regeneration check documented in the parent README.
- For project state. This tool reports adapter / catalog configuration, not project data.

## Parameters
No parameters. Pass `{}`.

## Expected Output
Returns `{ readOnly, exposureMode, configSource, toolCounts: { chat, workflow, adapter, total } }`.

- `exposureMode` — `"all"` (full default surface) or `"legacy"` (`expose_all_tools=false` opt-out).
- `configSource` — where the active mode was loaded from (env var, project config file, default).
- `toolCounts` — counts by family.

Does not mutate project state.

## Example Successful Call
```json
{}
```

Representative response:
```json
{
  "readOnly": true,
  "exposureMode": "all",
  "configSource": "default",
  "toolCounts": {
    "chat": 60,
    "workflow": 3,
    "adapter": 1,
    "total": 64
  }
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Unexpected `exposureMode`              | Mode doesn't match what was set in config                            | Inspect `configSource` to see which input won. Env vars typically override file config.               |
| Wrong tool count                       | A tool you expect to use isn't counted                               | Pivot to `GET /api/mcp/tools?mode=active` over HTTP for the full list, or run the catalog regeneration check from the parent README. |
| Mode shows `"legacy"` unexpectedly      | Custom-curated narrow surface in play                                | Verify `expose_all_tools` is not set to `false` in the relevant config.                               |

## Agent Reasoning Notes
This is a diagnostic / configuration-introspection probe. Most session loops don't need to call it — most agents should just call the tools they need and handle "tool not exposed" as a configuration error surfaced by the dispatcher. Reach for `mcp_get_exposure_mode` when you're debugging "why isn't X available?" or running integration tests against an adapter instance.

## Related Skills
- `project_context_read` — project-level state (different from adapter configuration).
- HTTP MCP bridge endpoints `/api/mcp/tools`, `/api/mcp/tools/<toolName>` — per-tool schema inspection.
