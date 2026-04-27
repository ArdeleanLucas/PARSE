# MC-323 — Fix persisted Windows path-separator leakage in `chat_tools.py`

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


## Objective
Ship the smallest focused rebuild PR that fixes project-relative path serialization in `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) so persisted metadata uses POSIX separators across platforms.

## Scope
- Add one regression test that fails on current code even on Linux by simulating Windows-style relative paths.
- Apply the one-line fix in `_display_readable_path()`.
- Re-run the new regression plus the two processed-import tests called out in the audit.
- Run a focused backend validation set, then package as a rebuild PR.

## Non-goals
- Do not start chat_tools PR 2.
- Do not refactor `mcp_adapter.py`.
- Do not broaden this into fixture-only path normalization work unless required by the failing regression.

## Grounded facts
- Root cause identified in PR #72 audit: `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`):5316-5321`.
- Current implementation uses `str(path.relative_to(self.project_root))`, which leaks backslashes on Windows.
- Real-bug impact is on persisted metadata written by processed import (`source_index.json`, `annotation.source_audio`).
- Rebuild `origin/main` is `ca4299c` at implementation time.

## Files
- `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`)
- `python/ai/test_parse_memory_tool.py` or a new focused backend regression test file
- `docs/plans/MC-323-display-readable-path-posix.md`

## Validation plan
1. New regression test fails first.
2. New regression test passes after fix.
3. Re-run:
   - `python/ai/test_parse_memory_tool.py::test_import_processed_speaker_write_copies_assets_and_builds_workspace_files`
   - `python/ai/test_parse_memory_tool.py::test_import_processed_speaker_preserves_existing_sources_and_clears_stale_optional_metadata`
4. Run a focused backend test slice around display/import paths.
5. Run `git diff --check` before PR.

## Completion criteria
- Persisted project-relative paths normalize to POSIX on all platforms.
- Regression test exists and passed after failing first.
- Focused validation is green.
- Rebuild PR opened with `--repo TarahAssistant/PARSE-rebuild`.
