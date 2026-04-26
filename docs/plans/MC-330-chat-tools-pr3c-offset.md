# MC-330 — chat_tools PR 3C offset-family extraction

## Objective
Execute PR 3C in `TarahAssistant/PARSE-rebuild` by extracting the offset-family chat tools from `python/ai/chat_tools.py` into two reviewable grouped modules under `python/ai/tools/`, preserving tool names, MCP exposure, schemas, and runtime behavior.

## Scope
In scope:
1. Add `python/ai/tools/offset_detection_tools.py` for:
   - `detect_timestamp_offset`
   - `detect_timestamp_offset_from_pair`
2. Add `python/ai/tools/offset_apply_tools.py` for:
   - `apply_timestamp_offset`
3. Move family-local helpers needed by those tools.
4. Update `python/ai/chat_tools.py` to merge bundle specs and delegate through thin wrappers.
5. Add direct extraction/regression tests for the new modules and bundle wiring.
6. Update duplicate-spec coverage in `python/adapters/test_mcp_adapter.py`.
7. Re-run targeted backend tests, full backend suite, frontend Vitest gate, TypeScript gate, and branch-local API smoke.
8. Open a rebuild implementation PR with explicit `--repo TarahAssistant/PARSE-rebuild`.

Out of scope:
- speaker-import rebasing/merging work beyond the already-completed PR #111 rebase
- PR 4 compare/enrichment/export work
- mcp_adapter PR 1 extraction work
- centralizing `_display_readable_path()` or `_load_project_concepts()`

## Key facts
- Fresh implementation worktree: `/home/lucas/gh/worktrees/PARSE-rebuild/chat-tools-pr3c-offset`.
- Base branch at task start: `origin/main` = `af46d82`.
- PR #111 and PR #95 have already been rebased to current main in the prerequisite phase of MC-330.
- Current rebuild `origin/main` includes PR #108 but not PR #111, by design.
- Coordinator-approved module split: `offset_detection_tools.py` + `offset_apply_tools.py`.
- Existing helper `_annotation_path_for_speaker()` is also used outside the offset-family extraction path (e.g. workflow tools), so preserve compatibility if needed.

## TDD plan
1. Add failing bundle-shape tests for the new offset modules before implementation.
2. Add direct failing tests for the extracted detection and apply handlers.
3. Add/update extraction wiring coverage asserting spec keys, handler keys, and `ParseChatTools(...).tool_names()` stay aligned.
4. Implement the minimal extraction to pass those tests.
5. Re-run focused suites, then full suites, then browser/API smoke.

## Completion criteria
- `ParseChatTools(...).tool_names()` remains stable at 50.
- Default MCP exposure remains stable at 36.
- Existing offset HTTP/backend tests still pass.
- New direct module tests and extraction-parity tests pass.
- `python/ai/chat_tools.py` line count drops materially from current main.
- Rebuild PR open with explicit `--repo TarahAssistant/PARSE-rebuild`.
