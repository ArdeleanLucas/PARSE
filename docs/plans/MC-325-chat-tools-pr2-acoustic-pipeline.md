# MC-325 — chat_tools PR 2 acoustic + pipeline bundle extraction

## Objective
Execute PR #85 in `TarahAssistant/PARSE-rebuild` by extracting 8 chat tools from `python/ai/chat_tools.py` into two grouped modules under `python/ai/tools/`, preserving tool names, schemas, MCP exposure counts, and runtime behavior.

## Scope
In scope:
1. Add `python/ai/tools/acoustic_starter_tools.py` for:
   - `stt_start`
   - `stt_word_level_start`
   - `forced_align_start`
   - `ipa_transcribe_acoustic_start`
   - `audio_normalize_start`
2. Add `python/ai/tools/pipeline_orchestration_tools.py` for:
   - `pipeline_state_read`
   - `pipeline_state_batch`
   - `pipeline_run`
3. Update `python/ai/chat_tools.py` to merge bundle specs and delegate through thin wrappers.
4. Update `python/ai/tools/__init__.py` exports if needed.
5. Add direct bundle tests:
   - `python/ai/tools/test_acoustic_starter_tools.py`
   - `python/ai/tools/test_pipeline_orchestration_tools.py`
   - `python/ai/test_chat_tool_bundle_extract_pr2.py`
6. Update cross-file duplicate-spec coverage in `python/adapters/test_mcp_adapter.py` if current assertions only scan the monolith.
7. Run targeted backend tests, full backend suite, frontend Vitest gate, and TypeScript gate.

Out of scope:
- sister-bug fix at `chat_tools.py:2271` (`project_relative` payload path normalization)
- PR 3 offset/import/memory bundles
- `python/adapters/mcp_adapter.py` refactors
- any FastMCP private API changes

## Key facts
- Working repo/remote must remain `TarahAssistant/PARSE-rebuild`.
- Branch target: `refactor/chat-tools-pr2-acoustic-pipeline`.
- Base commit at task start: `origin/main` = `d41fb95`.
- PR #68 established the grouped-module + thin-wrapper extraction pattern.
- Special handling required:
  - `stt_word_level_start` should delegate to shared module helper rather than bouncing through an in-class wrapper.
  - `pipeline_state_batch` should use `project_read_tools` helper directly if the coupling is shallow enough.

## TDD plan
1. Add failing bundle-shape tests for the new module exports before implementation.
2. Add direct failing tests for `stt_start` and `audio_normalize_start` bundle handlers before implementation.
3. Add failing pipeline bundle test verifying `pipeline_state_batch` still enumerates speakers correctly through the extracted module.
4. Implement minimal extraction to pass those tests.
5. Re-run focused suites, then full suites.

## Completion criteria
- `ParseChatTools(...).tool_names()` still returns 50.
- MCP/default exposure counts stay unchanged.
- New bundle tests and existing chat/MCP suites pass.
- `python/ai/chat_tools.py` line count drops materially from current main.
- A rebuild PR is open with explicit `--repo TarahAssistant/PARSE-rebuild`.
