# MC-328 — chat_tools PR 3A tag import + memory extraction

## Objective
Implement PR 3A in `TarahAssistant/PARSE-rebuild` by extracting the tag-import and parse-memory chat tool families from `python/ai/chat_tools.py` into reviewable grouped modules under `python/ai/tools/`, preserving tool names, MCP exposure, schemas, and runtime behavior.

## Scope
In scope:
1. Add `python/ai/tools/tag_import_tools.py` for:
   - `import_tag_csv`
   - `prepare_tag_import`
2. Add `python/ai/tools/memory_tools.py` for:
   - `parse_memory_read`
   - `parse_memory_upsert_section`
3. Move family-local helpers needed by those tools.
4. Update `python/ai/chat_tools.py` to merge bundle specs and delegate through thin wrappers.
5. Update `python/ai/tools/__init__.py` exports if needed.
6. Add direct extraction/regression tests for the new modules and bundle wiring.
7. Re-run targeted backend tests, full backend suite, frontend Vitest gate, TypeScript gate, and API smoke.
8. Open a rebuild implementation PR with explicit `--repo TarahAssistant/PARSE-rebuild`.

Out of scope:
- `speaker_import_tools.py` (PR 3B)
- offset extraction (PR 3C)
- `_display_readable_path` centralization or helper cleanup
- compare/enrichment/export PR 4 work
- `python/adapters/mcp_adapter.py` refactors beyond any minimal duplicate-spec test updates required by the extraction

## Key facts
- Working lane is the rebuild repo only: `/home/lucas/gh/tarahassistant/PARSE-rebuild` with `origin=TarahAssistant/PARSE-rebuild`.
- Fresh implementation worktree: `/home/lucas/gh/worktrees/PARSE-rebuild/chat-tools-pr3a-tag-memory`.
- Base branch at task start: `origin/main` = `cdb316c`.
- PR #91 and docs pre-research PR #100 are merged.
- Grounded gross footprint from PR #100 pre-research:
  - tag import family ≈ 326 lines
  - memory family ≈ 273 lines
  - combined PR 3A target ≈ 599 gross lines
- Coordinator decision: keep `_display_readable_path` on `ParseChatTools` for now; do not centralize it in PR 3A.
- Coordinator decision: `import_tag_csv` must call the shared extracted helper directly, not bounce through `self._tool_prepare_tag_import(...)`.

## TDD plan
1. Add failing bundle-shape tests for `tag_import_tools.py` and `memory_tools.py` exports before implementation.
2. Add direct failing tests for the extracted handlers where current coverage is missing or indirect, especially tag-import behavior.
3. Add/update extraction wiring coverage asserting spec keys, handler keys, and `ParseChatTools(...).tool_names()` stay aligned.
4. Implement the minimal extraction to pass those tests.
5. Re-run focused suites, then full suites, then browser/API smoke.

## Completion criteria
- `ParseChatTools(...).tool_names()` remains stable.
- Default MCP exposure counts remain unchanged.
- `import_tag_csv` delegates to shared extracted logic directly.
- `_display_readable_path` remains in-class on `ParseChatTools`.
- New direct module tests and existing chat/MCP suites pass.
- `python/ai/chat_tools.py` line count drops materially from current main.
- Rebuild PR open with explicit `--repo TarahAssistant/PARSE-rebuild`.
