> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../../).

# MC-324 — PR #80 while-waiting docs on sister bugs and chat_tools PR 2 seams

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


## Objective
Use the PR #80 wait window for two docs-only research tasks while PR #77 is under review and chat_tools PR 2 remains explicitly gated.

## Scope
1. Audit possible sister occurrences of the Windows path-separator bug pattern across:
   - `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`)
   - `python/ai/tools/`
   - `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`)
2. Pre-research chat_tools PR 2 by locating the 8 queued tools, mapping line ranges/dependencies, and proposing a grouped-module extraction structure.
3. Prepare the research outputs for the PR #80 lane; if PR #80 merges before push, ship them as a fresh follow-up docs PR from current `origin/main`.

## Non-goals
- Do not start chat_tools PR 2.
- Do not fix any discovered sister bugs in this task.
- Do not open speculative follow-up PRs beyond updating PR #80.

## Grounded facts
- PR #80 branch: `handoff/parse-back-end-while-waiting-2-sister-bugs-and-pr2-research`
- Current rebuild `origin/main` at task start: `bf9912c`
- PR #77 is still the referenced wait target in the PR #80 prompt.
- PR #80 deliverables must live under `.hermes/handoffs/parse-back-end/`.
- PR #80 merged on rebuild `origin/main` at `12fcc36` while this work was in flight, so shipping requires a fresh follow-up docs PR.

## Files
- `docs/plans/MC-324-pr80-while-waiting-docs.md`
- `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-path-separator-sister-bugs.md`
- `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr2-pre-research.md`

## Validation
- `git diff --check`
- verify PR #80 file list and branch head after push
- keep repo changes docs-only (no `python/` source diffs)

## Completion criteria
- Task A doc classifies all relevant path-string patterns and flags real-bug candidates.
- Task B doc maps all 8 PR 2 tools with line ranges, coupling, module proposal, and LoC reduction estimate.
- PR #80 updated on rebuild with explicit `--repo TarahAssistant/PARSE-rebuild` discipline preserved.
- Stand down again after shipping.
