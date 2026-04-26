---
agent: parse-back-end
queued_by: parse-gpt
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #68 merged at e962c18
related_prs:
  - 68
  - 59
  - 80
---

# parse-back-end next task — chat_tools PR 2 unblocked

## Goal
Resume **chat_tools PR 2** now that the old wait-rule is cleared.

## Why now
- Rebuild PR **#68** (`refactor(chat_tools): extract read-only chat tool bundles`) merged at `e962c18`.
- The old gate that kept chat_tools PR 2 on hold is no longer justified.
- parse-back-end has already shown the repo-target risk is under control by shipping the fix on rebuild PR **#77**, not oracle.

## Task
Start the next chat_tools implementation PR on **TarahAssistant/PARSE-rebuild** from current `origin/main`.

Use the original **PR #59** grouping as the scope anchor:
- acoustic starters
- pipeline orchestration

Follow the grouped-modules extraction pattern used in PR **#68**:
- isolate coherent chat-tool families into dedicated modules under `python/ai/tools/`
- keep `python/ai/chat_tools.py` as the thin wiring/registration surface
- preserve MCP adapter exposure and existing chat-tool names/contracts

## Inputs
- PR **#59** for the original grouping intent
- PR **#68** for the module extraction pattern to copy
- PR **#80** for the pre-research / line-range mapping once its docs are available

## Hard rules
- Rebuild repo only: `TarahAssistant/PARSE-rebuild`
- Branch from current `origin/main`
- No oracle PR
- Preserve runtime behavior and tool contract names
- Run the normal rebuild gates before reporting ready

## Required validation
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- targeted backend tests for the extracted chat_tools cluster
- `git diff --check`

## Reporting
Return a real implementation PR URL with:
- extracted modules listed
- remaining chat_tools LoC after PR
- exact validation commands/results
