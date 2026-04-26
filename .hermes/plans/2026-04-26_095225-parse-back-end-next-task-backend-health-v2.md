# PARSE-rebuild parse-back-end next task — backend health blockers on current main

## Goal
Bring the current `TarahAssistant/PARSE-rebuild` backend suite back to green on top of current `origin/main` without overlapping the active Builder lane.

## Current grounded context (revalidated 2026-04-26)
- Canonical repo: `TarahAssistant/PARSE-rebuild`
- Current `origin/main` head when this prompt was prepared: `bce0252` (`refactor(parseui): extract stage2 offset workflow (#11)`)
- Live open PR topology at prompt time:
  - **PR #19** open and green: `fix(annotate): prevent TranscriptionLanes hook-order crash`
  - URL: https://github.com/TarahAssistant/PARSE-rebuild/pull/19
- Builder lane already owns the Compare -> Annotate `TranscriptionLanes` crash in PR #19. **Do not touch** that frontend slice or widen into `src/components/annotate/TranscriptionLanes*` / `src/ParseUI*`.
- Root local checkout `/home/lucas/gh/tarahassistant/PARSE-rebuild` is on a stale local branch with a gone upstream and untracked debris. **Do not use that checkout as merge truth.** Start from fresh `origin/main`.

## Fresh backend failure snapshot
I re-ran the full backend suite on a temporary clean worktree from current `origin/main`:

```bash
PYTHONPATH=python python3 -m pytest -q
```

Result:
- **553 passed, 3 failed, 1 warning**

Exact failing tests:
1. `python/test_external_api_surface.py::test_http_mcp_bridge_lists_and_executes_tools`
2. `python/test_stt_configurable_transcribe.py::test_ortho_section_defaults_cascade_guard`
3. `python/test_stt_configurable_transcribe.py::test_ortho_explicit_override_beats_defaults`

### Failure 1: MCP HTTP bridge regression
`/api/mcp/tools?mode=all` returns **HTTP 500** inside `test_http_mcp_bridge_lists_and_executes_tools`.

Relevant test lines:
- `python/test_external_api_surface.py:136-156`

Relevant server/runtime surfaces:
- `python/server.py:2300-2354` (`_get_chat_runtime`, `_execute_mcp_http_tool`)
- `python/server.py:7014-7044` (`_api_get_mcp_tools`, `_api_get_mcp_tool`, `_api_post_mcp_tool`)
- `python/test_chat_docs_root.py:29-54`

Likely issue shape:
- singleton/runtime contamination around `_chat_tools_runtime` / `_chat_orchestrator_runtime`
- a prior test can poison the cached chat runtime so the MCP HTTP catalog path later serves a mismatched project/docs root or stale tool runtime

### Failures 2-3: ORTH contract drift
Both ORTH-specific configurable-transcribe tests now fail during provider construction because `LocalWhisperProvider(config_section="ortho")` raises immediately when `ortho.model_path` is empty.

Relevant failing test lines:
- `python/test_stt_configurable_transcribe.py:223-277`

Relevant provider lines:
- `python/ai/provider.py:1043-1075`

Current behavior:
- `LocalWhisperProvider(..., config_section="ortho")` hard-fails with:
  - `ValueError: [ORTH config error] ortho.model_path is empty in ai_config.json ...`

Task nuance:
- Do **not** casually remove the ORTH fail-closed safeguard.
- The repo intentionally moved away from silently falling back from `ortho.model_path` to `stt.model_path`.
- The real task is to make **code, tests, and documented contract consistent**:
  - either refine the implementation so unit tests can still exercise ORTH defaults without reintroducing silent runtime fallback, or
  - update the tests/fixtures/config plumbing so they provide an explicit safe ORTH model path while still verifying the cascade-guard defaults and override semantics.
- The fix must preserve the safety goal: **ORTH must not silently run the STT model by accident.**

## Required scope
Own only the backend health slice needed to restore the 3 failing tests.

In scope:
- `python/server.py`
- `python/ai/provider.py`
- backend pytest fixtures/tests needed to make the runtime contract explicit
- related backend docs/config examples if the contract is clarified

Out of scope:
- Builder PR #19 frontend crash fix
- unrelated frontend refactors or UI behavior
- broad API redesign beyond what is necessary to make the current backend contract truthful and green

## Recommended execution sequence
1. Branch from current `origin/main` in a fresh worktree.
2. Reproduce all 3 failures locally with the full suite.
3. Isolate the MCP HTTP bridge failure first.
   - prove whether cached chat runtime globals are contaminating the catalog/tool execution tests
   - fix with the smallest durable runtime reset / construction discipline that preserves current behavior
4. Resolve the ORTH contract drift second.
   - preserve the no-silent-fallback safety guarantee
   - make the testable contract explicit instead of relying on implicit fallback behavior
5. Re-run targeted tests while iterating.
6. Re-run the full backend suite before opening the implementation PR.

## Minimum validation before opening your implementation PR
Run at least:

```bash
PYTHONPATH=python python3 -m pytest -q python/test_external_api_surface.py -k 'http_mcp_bridge_lists_and_executes_tools or http_mcp_bridge_rejects_invalid_mode_with_400'
PYTHONPATH=python python3 -m pytest -q python/test_stt_configurable_transcribe.py -k 'ortho_section_defaults_cascade_guard or ortho_explicit_override_beats_defaults'
PYTHONPATH=python python3 -m pytest -q
python3 -m py_compile python/server.py python/ai/provider.py
```

If your final delta touches shared request/response surfaces or anything likely to affect repo-wide CI, also run:

```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
git diff --check
```

## Acceptance criteria
- Full backend suite is green on your branch.
- The MCP HTTP bridge test passes without order dependence / singleton contamination.
- The ORTH tests pass with an explicit, documented contract.
- The final behavior still prevents silent ORTH fallback onto the STT model.
- Your implementation PR clearly explains the chosen contract for ORTH model-path handling and the runtime/reset logic for MCP HTTP tooling.

## Reporting requirements
In your implementation PR body, include:
- exact root cause for failure 1
- exact root cause for failures 2-3
- files changed
- targeted validation results
- full backend-suite result
- whether any docs/config examples had to be updated to keep the contract truthful

## Handoff note
This prompt PR is coordination/docs only. The actual fix should ship in a separate parse-back-end implementation PR branched fresh from current `origin/main`.