---
agent: parse-back-end
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - chat_tools PR 3 from handoff #93 should complete first (Task B sequence: pre-research → implementation)
  - PR #95 (sister-bug fix MC-326) should merge first
related_prs:
  - 59  (original chat_tools decomposition prompt — PR 4 grouping anchor)
  - 68  (PR 1 pattern)
  - 72  (mcp_adapter architecture audit — env_config.py PR 1 candidate)
  - 91  (PR 2 implementation)
  - 93  (handoff covering Task A sister-bug + Task B PR 3)
related_skills:
  - parse-expose-chat-tool
  - parse-mc-workflow
  - test-driven-development
---

# parse-back-end follow-on — chat_tools PR 4 + mcp_adapter PR 1

**Why this exists:** After handoff #93's chat_tools PR 3 (offset/import/memory) completes, two related backend tasks queue up: chat_tools PR 4 (the final batch) and the first slice of mcp_adapter decomposition. Bundled in one handoff because they're sequential and both leverage your existing audit work.

## Working environment

Same rule. AGENTS.md repo-target guard from PR #74 (rebuild repo only — `--repo TarahAssistant/PARSE-rebuild` mandatory).

## Task A — chat_tools PR 4 (compare/enrichment/export bundles)

The fourth and final chat_tools decomposition slice per the original PR #59 grouping. After this lands, chat_tools.py should be ≤2500 LoC (the original PR #59 acceptance target).

### Pre-research first (matches your PR #83 / PR 3 pattern)

Output: `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr4-pre-research.md`

Same shape as your previous pre-research:
- Locate each PR 4 tool in current `chat_tools.py` (will be ~3500-4150 LoC after PR 3 lands)
- Record line ranges, LoC, dependencies, coupling to PRs 1/2/3 modules
- Propose grouped-module structure (probably 2-3 modules)
- Estimate predicted LoC reduction
- Map test surface

### Tools to extract (verify in pre-research; these are best-guess from PR #59 grouping)

- **Compare tools**: `compare_concept`, `compare_speakers`, cognate adjudication helpers (split_concept, merge_concept, mark_borrowing, etc.)
- **Enrichment tools**: `read_enrichments`, `write_enrichment`, CLEF integration (`read_clef_config`, `populate_clef`, `read_contact_lexeme_coverage`, etc.)
- **Export tools**: `export_lingpy`, `export_nexus`, NEXUS variant exports

### Suggested grouped-module structure (verify in pre-research)

```
python/ai/tools/
  compare_tools.py
  enrichment_tools.py
  export_tools.py
```

Each gets a paired test file. Same shape as PRs 1/2/3.

### Estimated reduction

PR 3 expected to bring chat_tools.py to ~3500-4150 LoC. PR 4 should drop another ~1000-1500 LoC (export tools are larger than compare/enrichment due to format-conversion code). Final target: **chat_tools.py ≤ 2500 LoC** (the original PR #59 cumulative goal).

### Acceptance for PR 4 implementation

- `wc -l python/ai/chat_tools.py` ≤ 2500 (cumulative across PRs 1-4)
- 2-3 new module files with paired tests
- All existing tests pass
- ParseChatTools, ChatToolExecutionError, ChatToolValidationError still importable from `ai.chat_tools`
- MCP catalog tool count unchanged (32 native + 36 with workflow macros + `mcp_get_exposure_mode`)

## Task B — mcp_adapter PR 1 (env_config.py extraction)

After Task A completes (chat_tools fully decomposed), pivot to the next backend monolith: `python/adapters/mcp_adapter.py` (2050 LoC, untouched).

### Source of truth

Your PR #72 architecture audit identified `env_config.py` as the **lowest-risk PR 1 candidate**:
- Already test-covered
- No tool decorator motion
- No tool-count drift expected
- Independent of FastMCP private-API mutation (which is the highest-risk seam, deferred)

Reference doc: `.hermes/handoffs/parse-back-end/2026-04-26-mcp-adapter-architecture-audit.md` (your PR #72 deliverable, now on main).

### Procedure

Same grouped-modules + thin-delegating-wrapper pattern as PR #68 / #91. Extract env-related config into `python/adapters/mcp/env_config.py`. Keep `mcp_adapter.py` as the thin orchestrator.

Estimated reduction: ~150-250 LoC.

### Hard rule

**Do NOT touch FastMCP private-API mutation** (`mcp._tool_manager._tools`) in this PR. Per your PR #72 audit, that's the highest-risk seam and needs its own dedicated handoff later.

### Acceptance

- `python/adapters/mcp/env_config.py` exists with paired test
- `mcp_adapter.py` shrinks by ~150-250 LoC
- All existing `python/adapters/test_mcp_adapter.py` tests pass without modification
- MCP exposure counts unchanged (32 native + 36 with workflow + `mcp_get_exposure_mode`)
- Runtime logger still reports 35 (excludes adapter-only tool — your PR #72 audit's count nuance)

## Sequence

Task A first (chat_tools PR 4) → Task B second (mcp_adapter PR 1). Both gated by chat_tools PR 3 from handoff #93 completing.

## Out of scope

- mcp_adapter PRs 2-5 (separate handoffs after PR 1 lands)
- FastMCP private API mutation (highest-risk seam, dedicated handoff later)
- provider.py decomposition (1907 LoC, untouched, future monolith — separate audit needed first)
- Optional payload-only sister-bugs at chat_tools.py:3708, 3816, preview_tools.py:119 (your PR #83 audit identified these as deferrable)

## Conventions

- One commit per logical step
- PR title format: `refactor(chat_tools): <action>` for PR 4, `refactor(mcp_adapter): extract env_config.py` for mcp_adapter PR 1
- Co-author line: `Co-Authored-By: parse-back-end <noreply@anthropic.com>`
- Do not merge your own PRs
- File MC items before opening (next available after MC-326)

## After both tasks land

- chat_tools.py decomposition complete (≤2500 LoC, 6408 → 2500 represents 61% reduction)
- mcp_adapter.py decomposition begun (PR 1 of ~5)
- Coordinator queues mcp_adapter PR 2 (likely `http_callbacks.py` per your audit) separately
