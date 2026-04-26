---
agent: parse-back-end
queued_by: parse-gpt
queued_at: 2026-04-26T15:41:00Z
status: queued
related_prs:
  - 59
---

# Next task — chat_tools.py decomposition

## Goal
Split `python/ai/chat_tools.py` into smaller per-domain modules while preserving the public tool surface.

## Why this is next
`chat_tools.py` is still 6,408 LoC on rebuild current-main and remains byte-identical to the oracle pressure file.

## Grounded context
- rebuild current-main: `f9aa3db1aad1d77078c9105cd8b5e5254c066338`
- oracle current-main: `0951287a812609068933ba22711a8ecd97765f38`
- MCP / ParseChatTools public behavior must remain stable during extraction

## Specific task
Decompose workspace-read, annotation/edit, compute/job, and onboarding/export tool domains into test-backed submodules without changing the exposed tool catalog.

## Validation
- `python3 -m pytest -q`
- targeted `python/ai/*` tests
- MCP catalog/tool-count regression check
