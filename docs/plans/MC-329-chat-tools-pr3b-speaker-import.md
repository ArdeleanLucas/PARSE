# MC-329 — chat_tools PR 3B speaker-import extraction

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


## Objective
Implement PR 3B in `TarahAssistant/PARSE-rebuild` by extracting the speaker-import chat tool family from `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) into `python/ai/tools/speaker_import_tools.py`, preserving tool names, MCP exposure, schemas, and runtime behavior.

## Scope
In scope:
1. Add `python/ai/tools/speaker_import_tools.py` for:
   - `onboard_speaker_import`
   - `import_processed_speaker`
2. Move the speaker-import helper family needed by those tools.
3. Update `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) to merge bundle specs and delegate through thin wrappers.
4. Add direct extraction/regression tests for the new module and bundle wiring.
5. Update duplicate-spec coverage if needed.
6. Re-run targeted backend tests, full backend suite, frontend Vitest gate, TypeScript gate, and branch-local API smoke.
7. Open a rebuild implementation PR with explicit `--repo TarahAssistant/PARSE-rebuild`.

Out of scope:
- PR 3A rebasing/merging work
- offset extraction (PR 3C)
- `_display_readable_path()` centralization or general helper cleanup
- compare/enrichment/export PR 4 work
- `mcp_adapter.py` extraction work

## Key facts
- Work must stay in the rebuild lane only: `/home/lucas/gh/tarahassistant/PARSE-rebuild`, remote `TarahAssistant/PARSE-rebuild`.
- Fresh implementation worktree: `/home/lucas/gh/worktrees/PARSE-rebuild/chat-tools-pr3b-speaker-import`.
- Base branch at task start: `origin/main` = `cdb316c`.
- PR #108 is still open; per user instruction, branch from current `origin/main` anyway and treat any later rebase as mechanical.
- Grounded gross footprint from PR #100 pre-research:
  - speaker import family ≈ 630 lines
- Coordinator rule remains: keep `_display_readable_path()` on `ParseChatTools` for now.
- Practical rule from PR 3A: keep `_load_project_concepts()` on `ParseChatTools` too, because speaker-import still uses it.

## TDD plan
1. Add failing bundle-shape tests for `speaker_import_tools.py` exports before implementation.
2. Add direct failing tests for extracted `onboard_speaker_import` and `import_processed_speaker` handlers.
3. Add/update extraction wiring coverage asserting spec keys, handler keys, and `ParseChatTools(...).tool_names()` stay aligned.
4. Implement the minimal extraction to pass those tests.
5. Re-run focused suites, then full suites, then browser/API smoke.

## Completion criteria
- `ParseChatTools(...).tool_names()` remains stable at 50.
- Default MCP exposure counts remain unchanged at 36.
- `_display_readable_path()` remains in-class on `ParseChatTools`.
- `_load_project_concepts()` remains in-class on `ParseChatTools`.
- New direct module tests and existing chat/MCP suites pass.
- `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) line count drops materially from current main.
- Rebuild PR open with explicit `--repo TarahAssistant/PARSE-rebuild`.
