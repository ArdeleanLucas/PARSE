# MCP adapter architecture audit

## Scope correction
The queued prompt names `python/ai/mcp_adapter.py`, but the actual untouched monolith is:
- `python/adapters/mcp_adapter.py`
- current size: **2050 LoC**

I audited the real file above.

## Evidence anchor
- PR #72 branch head: `7d53f05166c4c3c570c3a975b89954a384e7ad21`
- Current `origin/main`: `4ffb31dd6fe6b779673ef900b2cc7f1e9fb894be`
- `python/adapters/mcp_adapter.py` is byte-identical on both (`sha256 61869ab5af68e0361ce25bced9f59e52b9ef9861b7363a10d847a73bd810c5bb`)
- File under audit is therefore current, not stale branch-only state.

## Executive take
`mcp_adapter.py` is not just one big adapter factory. It currently mixes **five distinct concerns** in one file:
1. environment/config/bootstrap resolution
2. HTTP callback builders that proxy into the running PARSE server
3. MCP server assembly and metadata synchronization
4. the curated 32-tool MCP wrapper surface
5. the `expose_all_tools` expansion wrappers plus workflow wrappers

The next decomposition prompt can be precise: **do not start by splitting wrapper functions randomly.** The lowest-risk PR 1 seam is the pure bootstrap/config layer, not the wrapper registry.

## Public surface inventory

### External callable surface
- `create_mcp_server(project_root: Optional[str] = None) -> FastMCP` — main programmatic entrypoint (`737-1999`)
- `main()` — CLI entrypoint (`2006-2046`)

### Test-visible private helpers already exercised directly
- `_load_repo_parse_env()` (`146-184`)
- `_load_mcp_config()` (`118-120`, delegating to shared catalog logic)
- `_resolve_onboard_http_timeout()` (`198-225`)

### What imports this module today?
- **Non-test code importing `adapters.mcp_adapter`: none found**
- `python/server.py`: imports **nothing** from `adapters.mcp_adapter`
- `python/external_api/catalog.py`: imports **nothing** from `adapters.mcp_adapter`
- direct imports found are only in `python/adapters/test_mcp_adapter.py`

### Reverse coupling that matters
`mcp_adapter.py` depends on:
- `ai.chat_tools.ParseChatTools` (lazy import inside `create_mcp_server`)
- `ai.workflow_tools.WorkflowTools` (lazy import inside `create_mcp_server`)
- `external_api.catalog` shared helpers at module import time:
  - `load_mcp_config`
  - `mcp_exposure_payload`
  - `resolve_mcp_config_path`
  - `selected_mcp_tool_names`
- FastMCP internals via `mcp._tool_manager._tools` inside `_sync_registered_tool_metadata()` (`825-834`)

That last dependency is the most fragile one in the file.

## Tool exposure layers

### Verified counts
Runtime verification on this audit branch produced:
- total PARSE chat tools: **50**
- curated default parse MCP subset: **32**
- workflow tools: **3**
- adapter-only introspection tool: **1** (`mcp_get_exposure_mode`)
- default MCP total: **36** (`32 + 3 + 1`)
- `expose_all_tools=true` total: **54** (`50 + 3 + 1`)

### Where each layer is built
1. **50 total PARSE chat tools**
   - source: `ParseChatTools.get_all_tool_names()` in `create_mcp_server` (`803`)
2. **Curated default 32-tool subset**
   - selection function: `_selected_mcp_tool_names()` (`123-125`)
   - real logic delegated to `external_api.catalog.selected_mcp_tool_names()`
   - list source of truth: `ai.chat_tools.DEFAULT_MCP_TOOL_NAMES`
3. **3 workflow tools**
   - source of truth: `ai.workflow_tools.DEFAULT_MCP_WORKFLOW_TOOL_NAMES`
   - copied at `805`
4. **Adapter-only tool**
   - `mcp_get_exposure_mode()` (`836-846`)
5. **Total count accounting**
   - `mcp_get_exposure_mode` payload adds `+1` explicitly (`844`)
   - `logger.info()` logs only `len(all_registered_tool_names)` (`1991-1997`), so the log says **35** in default mode even though `server.list_tools()` returns **36**. That asymmetry is intentional in the current implementation and must be preserved or cleaned up deliberately.

## Internal structure by line span

| Slice | Lines | Approx LoC | What lives there |
|---|---:|---:|---|
| env/config helpers | `99-225`, `587-625` | 166 | project root, `.parse-env`, MCP config, API base, timeout, external roots, memory path |
| HTTP callback builders | `228-584`, `628-734` | 464 | STT, pipeline, normalize, jobs, job logs, onboarding HTTP proxy callbacks |
| server-factory shell | `737-816`, `1986-2046` | 141 | instantiate tools, apply config, build `FastMCP`, finish registration, CLI |
| metadata sync + adapter tool | `817-846` | 30 | JSON wrappers, metadata patch-up, `mcp_get_exposure_mode` |
| curated default wrappers | `853-1693` | 841 | 32 explicit `@mcp.tool()` wrappers for the default surface |
| expose-all wrappers | `1695-1947` | 253 | 18 additional wrappers only registered when `expose_all_tools=true` |
| workflow wrappers | `1949-1984` | 36 | 3 workflow macro wrappers |

## Coupling audit

### Coupling to `chat_tools.py`
Strong.

`mcp_adapter.py` does **not** import the new `python/ai/tools/*.py` modules directly. It still treats `ParseChatTools` as the single registry boundary:
- `ParseChatTools.get_all_tool_names()` for counts
- `tools.execute(...)` for every MCP wrapper call
- `tools.tool_spec(name)` for schema/description/metadata sync

That is the right boundary **for now**, but it means:
- the chat-tools decomposition can proceed behind the registry safely
- the future MCP adapter decomposition should keep importing the registry, not jump early to per-tool modules
- if chat tools ever stop exposing stable `tool_spec()` / `execute()` / `get_all_tool_names()`, MCP refactors become coupled to that ABI change

### Coupling to `workflow_tools.py`
Moderate.

The pattern is parallel to chat tools but smaller:
- `WorkflowTools(...)` instantiated once (`789-800`)
- `DEFAULT_MCP_WORKFLOW_TOOL_NAMES` imported at module top
- three explicit wrappers call `workflow_tools.execute(...)`
- metadata sync reuses `workflow_tools.tool_spec(name)`

This is cleaner than the chat-tool surface because the wrapper count is only three.

### Coupling to `external_api/catalog.py`
Useful and already partially modularized.

The adapter **reuses** shared config/exposure logic from `external_api.catalog` instead of duplicating it. That is good evidence for the next refactor direction: move more pure exposure/config code into reusable helper modules before touching the MCP wrappers themselves.

### Coupling to FastMCP internals
High-risk seam.

`_sync_registered_tool_metadata()` reaches into:
- `mcp._tool_manager._tools`

and mutates:
- `registered.description`
- `registered.parameters`
- `registered.annotations`
- `registered.meta`

This is private-object surgery. Any FastMCP internal change could break metadata publication even if tool execution still works.

## Candidate decomposition seams (5-module plan)

### 1. `python/adapters/mcp/env_config.py`
- Approx LoC: **166**
- Source lines: `99-225`, `587-625`
- Contents:
  - `_resolve_project_root`
  - `_resolve_mcp_config_path`
  - `_load_mcp_config`
  - `_selected_mcp_tool_names`
  - `_mcp_exposure_payload`
  - `_load_repo_parse_env`
  - `_resolve_api_base`
  - `_resolve_onboard_http_timeout`
  - `_resolve_external_read_roots`
  - `_resolve_memory_path`
- Risk: **low**
- Test surface to follow:
  - `test_load_repo_parse_env_sets_missing_vars`
  - `test_repo_parse_env_can_disable_mcp_path_sandbox`
  - `test_load_mcp_config_rejects_non_boolean_expose_all_tools`
  - `test_resolve_onboard_http_timeout_scales_for_large_files`
- Why it is coherent:
  - pure bootstrap/config logic
  - minimal FastMCP coupling
  - no decorator motion

### 2. `python/adapters/mcp/http_callbacks.py`
- Approx LoC: **464**
- Source lines: `228-584`, `628-734`
- Contents:
  - `_build_stt_callbacks`
  - `_build_pipeline_callbacks`
  - `_build_normalize_callback`
  - `_build_jobs_callback`
  - `_build_jobs_list_callback`
  - `_build_job_logs_callback`
  - `_build_onboard_callback`
- Risk: **medium**
- Test surface to follow:
  - onboarding timeout/env tests in `python/adapters/test_mcp_adapter.py`
  - indirect job/state assertions from MCP metadata + lock tests
  - future targeted unit tests for HTTP error translation would be worth adding here
- Why it is coherent:
  - all functions proxy from MCP into the live HTTP server / shared in-memory jobs
  - shared failure model: translate `urllib`/HTTP issues into tool-safe errors

### 3. `python/adapters/mcp/curated_registry.py`
- Approx LoC: **871**
- Source lines: `817-846`, `853-1693`
- Contents:
  - `_json_tool_result`
  - `_json_workflow_tool_result` (or keep in factory if preferred)
  - `_sync_registered_tool_metadata`
  - `mcp_get_exposure_mode`
  - 32 default explicit MCP wrappers
- Risk: **high**
- Test surface to follow:
  - allowlist cross-checks
  - default 36-tool exposure tests
  - safety metadata / dry-run / precondition assertions
  - duplicate-spec guard and project-loaded metadata tests
- Why it is coherent:
  - all default-surface wrapper declarations live here
  - this is the main reviewable registry seam once bootstrap/config is extracted

### 4. `python/adapters/mcp/extended_registry.py`
- Approx LoC: **253**
- Source lines: `1695-1947`
- Contents:
  - 18 `expose_all_tools`-only wrappers
- Risk: **medium**
- Test surface to follow:
  - `test_create_mcp_server_exposes_all_54_tools_when_enabled_in_config_dir`
  - `test_create_mcp_server_exposes_all_54_tools_when_enabled_in_root_config`
  - metadata assertions that mention full tool publication
- Why it is coherent:
  - registered only under one mode gate
  - clean separation from the curated 32-tool default surface

### 5. `python/adapters/mcp/server_factory.py`
- Approx LoC: **177**
- Source lines: `737-816`, `1949-2046`
- Contents:
  - `create_mcp_server`
  - final registration loops
  - 3 workflow wrappers
  - `main`
- Risk: **medium**
- Test surface to follow:
  - package smoke/import tests
  - default/all exposure count tests
  - package bridge tests under `python/packages/parse_mcp/tests/*`
- Why it is coherent:
  - becomes the thin composition root after the other seams are extracted

## Recommended PR 1 seam
**PR 1 should extract `env_config.py`.**

Why this first:
- smallest behavior surface
- already covered by direct tests
- no `@mcp.tool()` decorators move
- no FastMCP private metadata mutation moves
- no tool-count or schema changes should be observable if done correctly

A good PR 1 acceptance target would be:
- `python/adapters/mcp_adapter.py` drops by ~150-170 lines
- zero MCP surface changes
- same `36` / `54` totals
- same `mcp_get_exposure_mode` payload

## Test relocation map

### Stays as top-level adapter contract tests
Keep in `python/adapters/test_mcp_adapter.py` (or split later by concern, but still integration-level):
- full server exposure counts (`36`, `54`)
- phantom-tool / allowlist guarantees
- metadata publication guarantees
- stateful-job mutability guarantees
- source-index dry-run no-write guarantee

### Good candidates to move with `env_config.py`
- `.parse-env` loading tests
- MCP config parsing tests
- onboarding timeout scaling test

### Good candidates to move with `curated_registry.py`
- tool exposure default-surface tests
- metadata sync / strict schema / project_loaded precondition tests
- dry-run gating tests that assert registry-published metadata

### Good candidates to move with `extended_registry.py`
- expose-all count tests
- any future tests for extended-only wrappers

### Package-level tests that should remain where they are
Under `python/packages/parse_mcp/tests/`:
- HTTP bridge client tests
- CrewAI / LangChain / LlamaIndex adapter tests
- package smoke + packaging metadata tests

These are public-package contract tests, not internal module-placement tests.

## Sequencing warning
The chat-tools refactor and MCP-adapter refactor should **not** be tightly interleaved at the per-tool level.

Because `mcp_adapter.py` still depends on the stable `ParseChatTools` registry boundary, the safe sequence is:
1. finish the queued `chat_tools.py` decomposition while preserving the registry ABI
2. only then decompose `mcp_adapter.py` behind that unchanged registry surface

That means parse-back-end can safely resume PR 2 of chat_tools once parse-gpt clears PR #68, and the MCP adapter prompt can start later from this audit without reopening the chat-tools seam choice.
