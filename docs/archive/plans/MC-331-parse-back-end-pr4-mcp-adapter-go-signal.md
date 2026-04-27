> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../../).

# MC-331 — parse-back-end go signal for chat_tools PR 4 + mcp_adapter PR 1

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


## Objective
Ship a fresh parse-back-end handoff PR that makes the next backend execution order explicit after PR #120: chat_tools PR 4 first, then mcp_adapter PR 1 (`env_config.py`), with the pre-research gate preserved where PR #102 lacks grounded line ranges and LoC estimates.

## Grounded facts

- Working repo/lane: `TarahAssistant/PARSE-rebuild`
- Canonical handoff spec: PR #102 (`handoff(parse-back-end): chat_tools PR 4 + mcp_adapter PR 1 (env_config.py)`)
- User instruction: do **not** re-derive the task from scratch
- Current rebuild `origin/main` at planning time: `9dd8cc7d012a38d7e697a4ba0822e0e885da19e1`
- Current `origin/main` monolith sizes used for the scorecard refresh:
  - `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`): `3192` lines
  - `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`): `2050` lines
  - `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`): `7757` lines
  - `src/ParseUI.tsx`: `2035` lines
  - `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`): `1907` lines
- Current open rebuild PRs at planning time:
  - `#121` docs coordinator session snapshot
  - `#112` batch-report row extraction
  - `#107` TranscriptionLanes inline edit extraction

## Decision to encode in the handoff

The **first execution PR** for parse-back-end must be a **docs-only pre-research PR for chat_tools PR 4**, not the implementation PR, because:

1. PR #102 defines the grouped-domain shape and ordering, but
2. PR #102 does **not** provide grounded current line ranges or a current-family LoC estimate for PR 4, and
3. the target family is still a `>500`-LoC extraction class per the handoff rule Lucas restated.

By contrast, `mcp_adapter` PR 1 already has a grounded seam audit from the merged `2026-04-26-mcp-adapter-architecture-audit.md` handoff, so no extra pre-research PR is needed before the later `env_config.py` implementation slice.

## Files to ship in this coordinator PR

1. `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr4-mcp-adapter-pr1-go.md`
   - explicit ready-now signal
   - points at PR #102 as the governing spec
   - makes the first execution PR explicit
   - restates hard guards: rebuild repo, `git fetch origin --quiet --prune` before mergeability claims, screenshot links not embeds, MC/daily-log/scorecard after each PR
2. `docs/reports/2026-04-26-rebuild-progress-scorecard-late-refresh.md`
   - concise refreshed snapshot anchored on current `origin/main`
   - records that the next parse-back-end PR is the PR-4 pre-research docs slice

## Acceptance

- Handoff PR is opened on `TarahAssistant/PARSE-rebuild` using `--repo TarahAssistant/PARSE-rebuild`
- The handoff file exists at the exact path Lucas specified
- The handoff explicitly names the first parse-back-end execution PR:
  - `chat_tools PR 4 pre-research docs PR`
- The late scorecard refresh records the same next-step sequencing
- MC item, daily log, and profile note are updated after the PR is opened
