# MC-326 — stt_start sourceWav POSIX payload fix

## Objective
Ship the small sister-bug follow-up after PR #91 by fixing the remaining `stt_start` payload path serialization issue now living in `python/ai/tools/acoustic_starter_tools.py`.

## Scope
In scope:
1. Add a failing regression test proving `stt_start` returns POSIX separators in `sourceWav` payloads.
2. Apply the one-line `.as_posix()` fix in `python/ai/tools/acoustic_starter_tools.py`.
3. Re-run targeted backend tests, full backend tests, frontend/TypeScript gates, and a small branch-local MCP smoke.
4. Open a stacked rebuild PR from `fix/mc-326-stt-start-posix-payload` against `refactor/chat-tools-pr2-acoustic-pipeline`.

Out of scope:
- chat_tools PR 3 pre-research / implementation
- other payload-only sister bugs noted in earlier audits
- any `mcp_adapter.py` work

## Key facts
- Base branch is the open rebuild PR #91 branch: `origin/refactor/chat-tools-pr2-acoustic-pipeline`.
- The bug moved from `chat_tools.py` to `python/ai/tools/acoustic_starter_tools.py` during PR #91.
- Current suspect line shape: `str(safe_path.relative_to(tools.project_root))`.
- Desired fix: `safe_path.relative_to(tools.project_root).as_posix()`.

## TDD plan
1. Add a RED test in `python/ai/tools/test_acoustic_starter_tools.py` using `PureWindowsPath` semantics / Windows-style project roots to prove backslashes leak into `sourceWav` today.
2. Run just that test to confirm failure.
3. Apply the minimal one-line fix.
4. Re-run the focused suite, then the full gates.

## Completion criteria
- Regression test fails before code change and passes after.
- Existing `stt_start` behavior remains unchanged except for separator normalization.
- Stacked rebuild PR is open and green.
