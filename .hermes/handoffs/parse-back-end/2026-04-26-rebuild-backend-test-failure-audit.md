# Rebuild backend test failure audit — PR #64 baseline evidence

## Scope
Classify the **8 failing rebuild backend tests** captured in PR #64 gate evidence, without starting any chat_tools PR 2 work.

## Evidence anchor
- Evidence source: `origin/docs/coordinator-phase0-baseline-signed:.hermes/reports/2026-04-26-rebuild-backend-gate.txt`
- Evidence repo/worktree in that run: `/home/lucas/gh/worktrees/PARSE-rebuild/job-observability-http-slice`
- Evidence rebuild SHA: `f9aa3db1aad1d77078c9105cd8b5e5254c066338`
- Evidence summary: `658 passed / 8 failed / 2 skipped / 1 warning`
- Audit branch head: `7d53f05166c4c3c570c3a975b89954a384e7ad21` (PR #72)
- Current `origin/main` at audit time: `4ffb31dd6fe6b779673ef900b2cc7f1e9fb894be`
- Method note: this audit is anchored to the frozen PR #64 evidence above; I did **not** re-run the whole backend suite on newer main because the request was to classify the baseline failures, not mix in later drift.

## Summary
- **accepted-quirk:** 0
- **real-bug:** 2
- **fixture-issue:** 6

No failure qualifies as `accepted-quirk`. The red tests are either:
1. **true persisted-path bugs** that leak Windows separators into saved workspace metadata, or
2. **environment-sensitive fixture assertions** that assume POSIX separators / LF-only bytes during a Windows pytest run.

## Classification table

| Test | Class | One-line note |
|---|---|---|
| `test_onboard_speaker_dry_run_reports_plan_without_callback` | fixture-issue | Dry-run preview string uses OS-native separators (`audio\\original\\...`) and the assertion is POSIX-only; no workspace file is written in this path. |
| `test_import_processed_speaker_dry_run_reports_plan` | fixture-issue | Same as above: preview payload uses display-path formatting, not persisted metadata. |
| `test_import_processed_speaker_write_copies_assets_and_builds_workspace_files` | real-bug | `source_index.json` persisted `audio\\working\\...` instead of project-stable POSIX paths; this leaks Windows separators into durable project metadata. |
| `test_import_processed_speaker_preserves_existing_sources_and_clears_stale_optional_metadata` | real-bug | Same persisted mixed-separator metadata bug as above; existing POSIX entries and new Windows-style entries coexist in the same manifest. |
| `test_read_audio_info_returns_metadata` | fixture-issue | Read-only return payload uses `_display_readable_path()` and therefore returns Windows separators during a Windows run; no on-disk state is corrupted. |
| `test_run_full_annotation_pipeline_orchestrates_low_level_jobs` | fixture-issue | Workflow callback path passed to the fake STT starter is OS-native under Windows; orchestration behavior is otherwise intact. |
| `test_build_get_export_lingpy_response_preserves_headers_and_cleans_up_tempfile` | fixture-issue | The fake exporter writes text through the host newline mode, so the byte assertion sees `CRLF`; the handler itself only reads bytes and preserves them. |
| `test_run_normalize_job_forces_wav_output_for_non_wav_input_without_guard` | fixture-issue | `normalizedPath` is a result payload string built with `str(relative_path)` under Windows; path-shape assertion is separator-strict but the output file rule is otherwise correct. |

## Root-cause notes

### Shared real-bug root cause
The two `import_processed_speaker` persistence failures share one underlying bug:
- helper: `python/ai/chat_tools.py:5316-5321` (`_display_readable_path`)
- current behavior: `return str(path.relative_to(self.project_root))`
- consequence on Windows: backslashes leak into persisted `annotation.source_audio` and `source_index.json`
- blame anchor: helper introduced at `1bc33c28`; processed-import write path added in commit `8ee68175`

That helper is safe for human-readable previews, but not for persisted cross-platform project metadata unless it normalizes to POSIX (`.as_posix()`).

### Why the other six are fixture issues, not accepted quirks
- They fail only because the test fixtures assert POSIX-style strings or LF-only bytes under a Windows pytest run.
- They do **not** show silent corruption of saved PARSE workspace artifacts.
- They are therefore better treated as fixture/test-environment issues than as intentional baseline behavior worth canonizing as accepted quirks.

## Follow-up actions for parse-gpt (do not file from this lane)
1. **Fix persisted project-relative path normalization** for processed-import writes in `python/ai/chat_tools.py` so saved workspace metadata always uses POSIX separators.
2. After that fix, re-check whether `_display_readable_path()` should stay preview-only while persisted metadata moves to a separate `project_relative_posix_path()` helper.
3. Separately, decide whether Windows-specific fixture expectations should be relaxed in the six non-persistence tests or whether result-payload strings should also be normalized for UI/API consistency.
