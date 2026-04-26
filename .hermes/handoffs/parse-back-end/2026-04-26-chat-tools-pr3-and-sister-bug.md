---
agent: parse-back-end
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #85 (chat_tools PR 2 implementation) should ship and be reviewed by parse-gpt first
  - Wait-rule relaxed — review cadence is normal, not explicit gate (AGENTS.md guard makes the prior wait-rule redundant)
related_prs:
  - 59  (original chat_tools decomposition prompt — PR 3 grouping anchor)
  - 68  (PR 1 pattern)
  - 85  (PR 2 execute handoff)
  - 83  (sister-bug audit identifying chat_tools.py:2271)
related_skills:
  - parse-expose-chat-tool
  - parse-mc-workflow
  - test-driven-development
  - systematic-debugging
---

# parse-back-end next task — chat_tools PR 3 (offset/import/memory) + sister-bug fix

**Why this exists:** PR #85's chat_tools PR 2 (acoustic + pipeline) is in flight. Once it ships and parse-gpt reviews, two related tasks are queued: (a) chat_tools PR 3 covering offset/import/memory tools per the original PR #59 grouping, (b) the sister-bug fix at `chat_tools.py:2271` that your PR #83 audit identified as the highest-priority follow-up.

**Wait-rule update**: the explicit per-PR wait-rule from PR #59 is **relaxed** going forward. Reason: AGENTS.md repo-target rule (PR #74 merged) plus your demonstrated discipline (every PR since #229 has been on the right repo) makes the prior over-conservative gate redundant. Normal review cadence applies — wait for parse-gpt to merge PR 2 before opening PR 3, but no separate "lift" handoff needed.

## Working environment

Same rule. AGENTS.md PR #74 has the full guard. Screenshot convention from PR #89 — markdown links, not inline embeds — applies if you ship any UI-touching PR (chat_tools PRs are backend-only so no screenshots needed).

## Task A — Sister-bug fix at chat_tools.py:2271 (small, ship first)

PR #83's sister-bug audit identified one **highest-priority** follow-up after #77:

- **Location**: `python/ai/chat_tools.py:2271` (in `_tool_stt_start`)
- **Current**: `str(safe_path.relative_to(self.project_root))`
- **Bug**: Builds `sourceWav` payload that crosses the STT callback / HTTP boundary; on Windows this leaks backslashes into JSON-visible payload fields
- **Classification from your audit**: payload-only (not persisted to disk), but cross-process/user-visible
- **Fix**: Same one-line normalize as #77 — `path.relative_to(self.project_root).as_posix()` instead of `str(path.relative_to(...))`

Ship as a small focused PR — same shape as #77.

### Deliverable

Branch: `fix/mc-NNN-stt-start-payload-posix` (use next MC number after #323)

Files changed:
- `python/ai/chat_tools.py:2271` — one line
- `python/test_chat_tools_*.py` — add a Windows-path-payload regression test (capture sourceWav from a dry-run, assert no backslash)
- (Optional) Update PR #83's sister-bug audit doc to mark this candidate as **fixed** with PR link

### Acceptance

- One-line code change at `chat_tools.py:2271`
- Regression test asserting POSIX separators in sourceWav payload
- All existing tests still pass
- PR title: `fix(chat_tools): normalize stt_start sourceWav payload to POSIX separators`
- Reference PR #83 audit + #77 precedent in PR body

This can ship in parallel with chat_tools PR 3 (Task B below). They don't conflict.

## Task B — chat_tools PR 3 (offset/import/memory bundles)

Per the original PR #59 grouping (now updated post-PR 2 to the grouped-modules pattern from PR #68 / PR #85).

### Pre-research first (matches the PR 2 / PR #83 pattern)

Before implementing, do a short pre-research doc following PR #83's structure:

- Locate each tool from the PR 3 group in current `chat_tools.py` (will be ~4910 LoC after PR 2 merges)
- Record line ranges, LoC, dependencies on private state, coupling to PR #68 / PR 2 modules
- Propose grouped-module structure (probably 2-3 modules given the diversity of offset / import / memory)
- Estimate predicted LoC reduction
- Map test surface

### Tools to extract (from PR #59 original grouping)

- **Offset tools**: `detect_timestamp_offset`, `detect_timestamp_offset_from_pairs`, `apply_timestamp_offset`, `poll_offset_detect_job` (verify exact tool names — these are best guesses from the React-side `client.ts` API surface)
- **Import tools**: `onboard_speaker`, `import_processed_speaker`, `import_tag_csv` (CSV import + processed import + onboard speaker import)
- **Memory tools**: `parse_memory_read`, `parse_memory_upsert_section`, `parse_memory_write` (whatever exists)

### Suggested grouped-module structure (verify in pre-research)

```
python/ai/tools/
  offset_tools.py            # detect / apply / poll
  import_tools.py            # onboard + processed import + tag csv
  memory_tools.py            # parse_memory_*
```

Each gets a paired test file. Same shape as PR #68 + #85 (TOOL_SPECS list + HANDLERS dict).

### Coupling note (anticipate from your audit)

The processed-import tools were the source of the path-separator real-bug fixed in #77. They have heavy on-disk write coupling. Test scaffolding should follow the same fixture patterns from `parse-mcp-large-file-onboarding-timeouts` skill.

### Estimated reduction

If PR 2 brings chat_tools.py to ~4910 LoC, PR 3 should drop another **~600-800 LoC** (offset + import + memory tools are larger than the read-only set from PR 1 due to write-side complexity).

### Sequence

1. **Ship pre-research first** as a docs-only PR — same shape as PR #83. Title: `docs(parse-back-end): chat_tools PR 3 pre-research (offset/import/memory)`
2. **Then ship PR 3 implementation** in 1-3 PRs depending on grouping (your judgment from pre-research).

### Acceptance for PR 3 implementation (cumulative)

- `wc -l python/ai/chat_tools.py` ≤ ~4150 (~600-800 LoC reduction from PR 2's ~4910)
- 2-3 new module files under `python/ai/tools/`, each with paired tests
- All existing `python/ai/test_*.py` and `python/adapters/test_*.py` tests pass
- ParseChatTools, ChatToolExecutionError, ChatToolValidationError still importable from `ai.chat_tools`
- MCP catalog tool count unchanged

## Out of scope

- **PR 4** (compare/enrichment/export bundles) — separate handoff after PR 3 lands
- **mcp_adapter.py decomposition** — coordinator (parse-gpt) will queue env_config.py extraction as PR 1 of that sequence per your PR #72 audit
- **FastMCP private API mutation** — fragile per PR #72; needs dedicated handoff later
- **Other payload-only sister-bugs** at `chat_tools.py:3708`, `3816`, `python/ai/tools/preview_tools.py:119` — your audit classified these as "optional consistency fixes." Ship them as a single small PR after PR 3 lands if you want, or defer.

## Conventions

- One commit per logical step
- PR title format: `refactor(chat_tools): <action>` for PR 3, `fix(chat_tools): <action>` for sister-bug
- Co-author line: `Co-Authored-By: parse-back-end <noreply@anthropic.com>`
- Do not merge your own PRs
- File MC items before opening (per `parse-mc-workflow` skill) — MC-323 (path fix), MC-324 (PR 80 followup) already used; pick next available

## Out-of-band notes

- **Wait for parse-gpt's review of PR #85 before starting PR 3 implementation** — but the explicit "wait-rule lift handoff" pattern from #59/#81 is no longer needed; review cadence is normal. If parse-gpt has merged PR 2 by the time you read this, you're free to proceed.
- **Pre-research first, implementation second** — same discipline as PR 2. The pre-research doc is small but it makes the implementation PR honest.
- **Don't bundle the sister-bug fix INTO PR 3** — keep them separate. Sister-bug is a fix; PR 3 is a refactor. Different review needs.
- After PR 3 lands, parse-gpt will queue PR 4 (compare/enrichment/export) and the mcp_adapter env_config.py PR 1 separately.
