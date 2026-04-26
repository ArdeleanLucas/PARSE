# parse-back-end — next task: chat_tools.py decomposition

**Lane:** Agent B (backend)
**Date queued:** 2026-04-26
**Rebuild oracle SHA at queue time:** `f9aa3db1aa`
**Live oracle SHA at queue time:** `ArdeleanLucas/PARSE@0951287a81`
**Branch from:** `origin/main`
**Estimated PR count:** 4 (one per tool group, in order)

---

## Why this task

`python/ai/chat_tools.py` is **6408 LoC, byte-identical to the live oracle**, and is the single largest untouched monolith in the rebuild. After PR #57 (speech/suggestion HTTP handlers) lands, it will be the dominant remaining structural risk.

Three reasons it matters now:

1. **It's the AI/MCP surface.** Every chat tool the React shell calls and every tool exposed via `mcp_adapter.py` is registered here. The Option-3 desktop pivot is gated on this surface being stable and modular — splitting it later is more expensive because `mcp_adapter.py` (2050 LoC, also untouched) and `python/external_api/catalog.py` both consume its registry shape.
2. **It blocks parallel work on AI features.** Any future "expose new chat tool" or "add workflow macro" PR currently has to serialize against this file. Splitting it into per-tool handlers unblocks parallel autonomy.
3. **It's the next file the parity inventory will need to verify.** `option1-parity-inventory.md` §5.2 lists the AI/chat shell as a P1 surface — without per-tool boundaries, parity evidence is impossible to scope.

This task pulls each tool's spec + handler into its own file under `python/ai/tools/`, leaves `chat_tools.py` as a thin registry that imports from `tools/` and exposes the existing `ParseChatTools` interface unchanged, and adds per-tool unit tests.

The pattern is documented in the `parse-expose-chat-tool` skill — read it before starting.

---

## Scope

### In scope

1. Create `python/ai/tools/` package with `__init__.py`, a `_registry.py` for the spec aggregation, and one file per tool.
2. Move each tool's spec dict and its handler function (currently inlined in `chat_tools.py` as `_handle_<tool_name>` or similar) into its own file under `python/ai/tools/`.
3. Reduce `chat_tools.py` to a registry/orchestrator that imports specs and handlers from `python/ai/tools/`, wires them into the existing `ParseChatTools` class, and re-exports `ChatToolExecutionError`, `ChatToolValidationError`, `ParseChatTools` for callers (`python/server.py`, `python/adapters/mcp_adapter.py`, `python/ai/chat_orchestrator.py`).
4. Add one test file per extracted tool: `python/ai/tools/test_<tool_name>.py`. Each test file covers the tool's happy path, its argument validation errors, and at least one execution-error case.
5. Update `python/ai/workflow_tools.py` only if it directly imports from `chat_tools.py` internals; do not change its public shape.

### Out of scope

- Any change to the tool list exposed via `mcp_adapter.py` (count must remain 32 native + 36 with workflow macros + `mcp_get_exposure_mode`, per `README.md` claims).
- Any change to tool behavior, argument schema, return shape, or error wording.
- Touching `mcp_adapter.py`, `provider.py`, `chat_orchestrator.py`, or `workflow_tools.py` beyond import-path updates.
- Touching `python/server.py` beyond import-path updates if the registry export shape changes.
- Touching the React shell (`src/`) — frontend lane owns that.
- Renaming any tool. Tool names are part of the chat-tool ABI and the MCP catalog.

---

## Tool inventory + grouping (proposed)

`chat_tools.py` currently registers ~50 tools per the live README claim. Group them by domain, one PR per group:

### Group 1 (PR 1) — Workspace/project read tools (lowest risk, no side effects)

Files under `python/ai/tools/`:
- `list_speakers.py`
- `list_concepts.py`
- `list_concept_speakers.py`
- `read_workspace_config.py`
- `read_audio_info.py`
- `read_csv_preview.py`
- `read_text_preview.py`
- `get_speaker_status.py`

### Group 2 (PR 2) — Annotation / editing tools

Files under `python/ai/tools/`:
- `read_annotation.py`
- `write_annotation.py`
- `add_interval.py`
- `update_interval.py`
- `delete_interval.py`
- `move_interval.py`
- `mark_concept_done.py`
- `apply_tag.py`
- `remove_tag.py`

### Group 3 (PR 3) — Compute / job-orchestration tools

Files under `python/ai/tools/`:
- `start_normalize.py`
- `start_stt.py`
- `start_compute.py`
- `start_offset_detect.py`
- `apply_offset.py`
- `poll_job.py`
- `cancel_job.py`
- `get_job_logs.py`
- `start_lexeme_search.py`
- `read_lexeme_results.py`

### Group 4 (PR 4) — Onboarding / import / CLEF / export tools

Files under `python/ai/tools/`:
- `onboard_speaker_import.py`
- `import_csv.py`
- `import_comments.py`
- `start_clef_populate.py`
- `read_clef_status.py`
- `read_contact_lexeme_coverage.py`
- `export_lingpy.py`
- `export_nexus.py`
- `read_parse_memory.py`
- `write_parse_memory.py`

> **Before starting**, the agent must run `grep -nE "^def _handle_|^TOOL_SPEC_|tool_specs\\.append|register_tool" python/ai/chat_tools.py` and reconcile the actual tool list against the proposed grouping. If the real count differs from the proposed grouping (some tools may have been added or renamed since this prompt was written), update the grouping in PR 1's body and proceed with that revised grouping for PRs 2–4. **Do not silently drop or add tools.**

---

## Per-PR procedure

Each of the 4 PRs follows the same pattern. Use Group 1 as the worked example; repeat for Groups 2–4.

### Step 1 — Create the per-tool file

For each tool in the group, the new file should contain:

```python
# python/ai/tools/list_speakers.py
"""Chat tool: list_speakers — return all speakers in the workspace."""

from typing import Any, Dict
# any other imports the handler needs

TOOL_SPEC: Dict[str, Any] = {
    "name": "list_speakers",
    "description": "...",   # copy verbatim from chat_tools.py
    "parameters": { ... },  # copy verbatim
}


def handle(workspace_root: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Implementation. Signature must match the existing _handle_list_speakers in chat_tools.py."""
    # body cut from chat_tools.py
    ...
```

The handler signature must match what `ParseChatTools.execute` currently dispatches to. Read the dispatch site in `chat_tools.py` first to confirm signature shape (positional args vs **kwargs, sync vs async).

### Step 2 — Update the registry

`python/ai/tools/_registry.py`:

```python
"""Aggregated chat-tool registry. chat_tools.py imports from here."""

from typing import Callable, Dict, List
from . import (
    list_speakers,
    list_concepts,
    list_concept_speakers,
    # ... rest of the group
)

TOOLS = [
    list_speakers,
    list_concepts,
    # ...
]

def all_specs() -> List[Dict]:
    return [t.TOOL_SPEC for t in TOOLS]

def all_handlers() -> Dict[str, Callable]:
    return {t.TOOL_SPEC["name"]: t.handle for t in TOOLS}
```

For PRs 2–4, append to the existing `_registry.py` rather than rewriting it.

### Step 3 — Slim chat_tools.py

Replace the inlined spec dicts and `_handle_*` functions for this group with:

```python
from ai.tools import _registry as _tools_registry

# In ParseChatTools.__init__ or where the tool table is built:
self._tool_specs.extend(_tools_registry.all_specs())
self._tool_handlers.update(_tools_registry.all_handlers())
```

Important constraints:
- The public class `ParseChatTools` must remain in `chat_tools.py` with the same public methods.
- `ChatToolExecutionError` and `ChatToolValidationError` must remain importable from `python.ai.chat_tools` (existing callers depend on this — `grep -rn "from ai.chat_tools" python/ src/` first).
- The combined tool list returned by `ParseChatTools.list_tools()` (or equivalent) must be identical in name, order is acceptable as long as MCP catalog tests pass.

### Step 4 — Tests

For each new file `python/ai/tools/<tool>.py`, create `python/ai/tools/test_<tool>.py` covering:

1. **Spec shape:** `TOOL_SPEC` has `name`, `description`, `parameters` keys; name matches filename.
2. **Happy path:** call `handle()` against a fixture workspace, assert return shape matches what the existing `python/test_chat_tools_*.py` (if any) expects.
3. **Validation error:** missing required arg → `ChatToolValidationError`.
4. **Execution error path:** at least one realistic failure (e.g. workspace not found, file unreadable). Use existing fixture patterns from `python/test_*.py`.

If existing `python/test_chat_tools*.py` tests cover the tool already, add a parallel test in `python/ai/tools/test_<tool>.py` that exercises the per-file handler directly. Do not delete the existing tests.

### Step 5 — Verify

Run:

```bash
pytest python/ai/tools/ python/ -x -k "chat_tools or tools"
pytest python/test_external_api_surface.py
pytest python/test_optional_websocket_dependency.py  # catches import-side-effect regressions
```

All must be green. No skips added.

Then start the dev server and run a sanity check via the chat panel: invoke at least one tool from the extracted group and verify the MCP catalog still lists all expected tools (`curl localhost:8766/api/external/mcp/tools` or equivalent).

### Step 6 — PR

PR title: `refactor(chat_tools): extract <group-name> tools into python/ai/tools/`
PR body must include:
- Before/after `wc -l python/ai/chat_tools.py`
- List of extracted files
- Output of `pytest python/ai/tools/ -v` (truncated to passing summary)
- Confirmation that MCP catalog tool count is unchanged
- Any tool grouping deviations from this prompt + reasoning

---

## Acceptance (cumulative across all 4 PRs)

- `wc -l python/ai/chat_tools.py` ≤ 2500 (down from 6408 — about a 60% reduction)
- `python/ai/tools/` contains one file per chat tool, each with a paired test
- `python/ai/tools/_registry.py` is the single aggregation point
- `mcp_adapter.py` is unchanged in size and behavior; tool count exposed via MCP is unchanged
- All existing `python/test_*.py` tests pass without modification
- All new `python/ai/tools/test_*.py` tests pass
- Dev server boots; chat panel can invoke at least one tool from each group (manual smoke test, screenshots in PR 4 body)

---

## Test gates (every PR)

- `pytest python/ -x` — green
- `pytest python/ai/tools/ -v` — green, no skips added
- `python -c "from ai.chat_tools import ParseChatTools, ChatToolExecutionError, ChatToolValidationError"` — succeeds
- `python -c "from adapters.mcp_adapter import build_adapter; print(len(build_adapter().list_tools()))"` — returns the same tool count as on `origin/main` before this PR
- `npm run typecheck` — green (catches if TS types coupled to backend tool shapes drift)

---

## Conventions

- One commit per tool extraction is acceptable but not required; one commit per logical step (extract, registry update, tests, fix imports) is preferred.
- PR title format: `refactor(chat_tools): extract <group-name> tools into python/ai/tools/`
- Co-author line: `Co-Authored-By: parse-back-end <noreply@anthropic.com>`
- Do not merge your own PRs. Coordinator (parse-gpt) reviews and merges.

---

## Skill references

Use these installed Hermes skills:

- `parse-expose-chat-tool` — encodes the 3-file pattern (spec + handler + test) and the dispatch contract in `chat_tools.py`. Read first; the extracted files should look like the inverse of an "expose new chat tool" PR.
- `test-driven-development` — write the per-tool test file before cutting the handler out, use it as a regression detector during the cut.
- `systematic-debugging` — for any tool whose handler has subtle workspace-path or env-var coupling. `chat_tools.py` has a number of these.
- `parse-mc-workflow` — file an MC item for this work before opening PR 1, append outcomes after each PR lands.

---

## What "done" looks like at the end of all 4 PRs

- `python/ai/chat_tools.py` ≤ 2500 LoC
- `python/ai/tools/` contains ~37 tool modules + `_registry.py` + per-tool tests
- All existing tests still green
- New per-tool tests green
- MCP catalog tool count unchanged (32 native, 36 with workflow macros + `mcp_get_exposure_mode`)
- ParseChatTools, ChatToolExecutionError, ChatToolValidationError still importable from `ai.chat_tools` for unchanged caller compatibility

---

## Out-of-band notes

- **Do not modify `mcp_adapter.py` in this task.** It will be the next backend monolith after `chat_tools.py` lands. Splitting it now would conflict with the parity work this task enables.
- The currently-checked-out branch on `/home/lucas/gh/tarahassistant/PARSE-rebuild` is stale. Branch from `origin/main` directly.
- If a tool handler depends on private state inside `chat_tools.py` (a module-level cache, a closure over `__init__` args), pull that state into the new tool file as module-level state, OR pass it as a constructor arg if it must remain shared. Document the choice in the PR body.
- If the actual tool count differs from the proposed grouping (because tools have been added/renamed since this prompt was written), update the grouping in PR 1 and proceed — but do not silently drop tools.
- If any existing test relies on patching `ai.chat_tools._handle_<tool>` directly, update those patches to target the new module path. Do not delete the tests.
