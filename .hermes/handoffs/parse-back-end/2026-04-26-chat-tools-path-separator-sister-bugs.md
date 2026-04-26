# Sister-bug audit — path-separator leak patterns after PR #77 root-cause fix

## Scope
Audit the PR #77 bug pattern across the scoped surfaces named by PR #80:
- `python/ai/chat_tools.py`
- `python/ai/tools/`
- `python/adapters/mcp_adapter.py`

No code changes. This is classification only.

## Evidence anchor
- Audit branch head: `9af9caaff6a1df0dfd95b6aa075bd93186444f63` (PR #80 base commit)
- Current rebuild `origin/main` inspected for code truth: `bf9912c...`
- Known root bug already handled separately in open PR #77:
  - `python/ai/chat_tools.py:_display_readable_path()`
  - old expression: `str(path.relative_to(self.project_root))`
  - fix in PR #77: `.as_posix()`

## Summary
- **New persisted-to-disk sister bugs found:** 0
- **Payload-only consistency candidates:** 4
- **Logged-only candidates:** 0
- **Path-comparison-only uses (safe / non-emitting):** 5
- **Scoped `mcp_adapter.py` matches:** 0

So the root bug from PR #77 appears isolated as the only **persisted-to-disk** case in the scoped grep. The remaining raw `str(...relative_to(...))` patterns are response/request payload formatting issues, not on-disk metadata corruption.

## Emitting matches

| File:line | Function | Current expression | Class | Assessment | Recommended fix |
|---|---|---|---|---|---|
| `python/ai/chat_tools.py:2271` | `_tool_stt_start` | `str(safe_path.relative_to(self.project_root))` | payload-only | Feeds `sourceWav` into dry-run payloads and the STT start callback/HTTP boundary. Not persisted to disk, but still cross-process/user-visible. | Follow-up small PR: normalize to `.as_posix()` when building `project_relative`. Highest-priority sister candidate after PR #77. |
| `python/ai/chat_tools.py:3708` | `_tool_detect_timestamp_offset` | `str(annotation_path.relative_to(self.project_root))` | payload-only | Read-only response field `annotationPath`; no write path. | Optional consistency fix: use `.as_posix()` for agent/UI-facing payloads. |
| `python/ai/chat_tools.py:3816` | `_tool_apply_timestamp_offset` | `str(annotation_path.relative_to(self.project_root))` | payload-only | Returned after a write, but only as response metadata; annotation file itself is written via `annotation_path.write_text(...)`, not this string. | Optional consistency fix: use `.as_posix()` in response payload. |
| `python/ai/chat_tools.py:4490` | `_display_readable_path` | `str(path.relative_to(self.project_root))` | persisted-to-disk | **Known root bug** already addressed by PR #77. This helper fans out into processed-import writes plus multiple read payloads. | Merge PR #77; no new action in this PR #80 lane. |
| `python/ai/tools/preview_tools.py:119` | `tool_spectrogram_preview` | `str(safe_audio.relative_to(tools.project_root))` | payload-only | Placeholder preview request surface only; not persisted. It bypasses `_display_readable_path()`, so PR #77 does **not** fix it. | Low-risk follow-up: normalize to `.as_posix()` if Windows response parity matters for spectrogram preview consumers. |

## Path-comparison-only uses (safe in current scope)

These `relative_to(...)` calls are guard checks or containment tests only. They do **not** stringify project-relative paths into emitted JSON, so they are not separator-leak bugs.

| File:line | Function | Current use | Class | Why safe |
|---|---|---|---|---|
| `python/ai/chat_tools.py:2161` | `_resolve_project_path` | `resolved.relative_to(self.project_root)` | path-comparison-only | Pure escape check; result discarded. |
| `python/ai/chat_tools.py:2170` | `_resolve_project_path` | `resolved.relative_to(root_resolved)` | path-comparison-only | Allowed-root membership check; result discarded. |
| `python/ai/chat_tools.py:2225` | `_resolve_readable_path` | `resolved.relative_to(root)` | path-comparison-only | Read-root membership check; result discarded. |
| `python/ai/chat_tools.py:2244` | `_annotation_path_for_speaker` | `candidate.relative_to(self.annotations_dir.resolve())` | path-comparison-only | Annotation-directory containment check only. |
| `python/ai/chat_tools.py:5344` | `_tool_parse_memory_upsert_section` | `self.memory_path.relative_to(self.project_root)` | path-comparison-only | Writable-location guard only; not emitted. |

## Negative result: `python/adapters/mcp_adapter.py`
No scoped sister pattern surfaced there:
- no `str(...relative_to(...))` matches
- no `str(Path(...))`-style project-relative emission that mirrors the PR #77 bug

That is useful because it narrows the separator-risk family to `chat_tools.py` and one preview helper in `python/ai/tools/` rather than the MCP adapter layer.

## Remediation order (research only)
1. **Merge PR #77** — fixes the only known persisted-to-disk bug in this family.
2. **Small consistency PR for `chat_tools.py:2271`** — highest-value sister candidate because it crosses the STT callback / HTTP boundary.
3. **Optional payload-cleanup PR** for `annotationPath` responses at `3708` and `3816`.
4. **Optional preview cleanup** for `python/ai/tools/preview_tools.py:119`.

## Bottom line
The sister-bug audit is a mostly negative result:
- **no new persisted metadata bugs** beyond the `_display_readable_path()` root cause already fixed in PR #77
- **four response/request payload formatting candidates** remain
- **no MCP adapter sibling** was found in the scoped files
