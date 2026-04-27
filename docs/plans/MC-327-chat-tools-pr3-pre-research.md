# MC-327 — chat_tools PR 3 pre-research

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


## Objective
Produce the grounded post-PR-91 pre-research handoff for the next `chat_tools.py` decomposition slice: offset, import, and memory families.

## Scope
In scope:
1. Audit current `origin/main` after PR #91 merge.
2. Re-derive exact spec and handler line ranges for the PR 3 tools.
3. Map helper coupling, MCP/default-surface impact, and existing test coverage.
4. Recommend module boundaries and a reviewable implementation sequence.
5. Ship the research as a docs-only rebuild PR.

Out of scope:
- implementing PR 3
- rebasing or retargeting stacked PR #95
- PR 4 compare/enrichment/export work
- `mcp_adapter.py` extraction work

## Key facts
- PR #91 merged into rebuild `main` at commit `55f8226`.
- Current rebuild `origin/main` at research time: `b561475`.
- Current `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) length: `4850` lines.
- PR #93 is merged and is the governing handoff for this pre-research.
- All 9 PR 3 tools are still in `DEFAULT_MCP_TOOL_NAMES`; 6 are write-allowed, so MCP/default-catalog parity matters.

## Questions this pre-research must answer
1. Which exact modules are reviewable on the post-PR-91 line map?
2. Which helper blocks are family-local versus shared enough to keep in-class?
3. Which tests already pin the behavior, and where are the current gaps?
4. Is the earlier rough `4850 -> ~4150` estimate still credible after inspecting the real post-PR-91 monolith?

## Deliverables
- `docs/plans/MC-327-chat-tools-pr3-pre-research.md`
- `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr3-pre-research.md`

## Completion criteria
- Exact spec + handler line table for all 9 PR 3 tools.
- Grounded module recommendation with rationale.
- Test surface map with explicit gaps.
- Honest LoC estimate based on current file, not the older pre-PR-91 heuristic.
- Docs-only rebuild PR open with explicit `--repo TarahAssistant/PARSE-rebuild`.
