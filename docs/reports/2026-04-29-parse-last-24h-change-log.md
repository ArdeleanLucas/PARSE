# PARSE last-24h documentation refresh — 2026-04-29

## TL;DR

- Original audit window: 2026-04-28 01:08+02 through 2026-04-29 01:08+02, grounded on `origin/main` at `5153669`; rebase refresh folded forward current `origin/main` at `680a97f` after PR #182 merged.
- Main moved through 11 merged PRs in the original window: #168, #169, #170, #171, #172, #173, #174, #175, #176, #177, #179. Post-window rebase addendum: #182 is now merged on `main`.
- Original-audit open follow-up: PR #180 (`fix: create missing IPA lexeme interval on save`) was open at that audit time, but it later merged during the same local calendar day. See `2026-04-29-calendar-day-merged-pr-doc-refresh.md` for the superseding calendar-day ledger.
- Documentation updates in this PR refresh current user/developer/coordinator docs for CLEF, MCP counts, lexeme save retiming, active handoff queue state, and stale post-cutover repo wording.

## Grounding evidence

```text
repo: /home/lucas/gh/tarahassistant/PARSE-rebuild
origin: git@github.com:ArdeleanLucas/PARSE.git
origin/main at original audit: 5153669
origin/main at rebase refresh: 680a97f
current branch for this doc refresh: docs/last-24h-parse-change-refresh
```

Tool-grounded checks used:

- `git fetch origin --quiet --prune`
- `git log --since='24 hours ago' origin/main`
- `gh pr list --repo ArdeleanLucas/PARSE --state merged --search 'merged:>=2026-04-28'`
- `gh pr view <168|169|170|171|172|173|174|175|176|177|179|180|182> --repo ArdeleanLucas/PARSE`
- local code count check: `ParseChatTools=55`, `DEFAULT_MCP_TOOL_NAMES=55`, workflow macros `3`, default adapter total `59`.

## Merged changes in the window

| PR | Merge | Area | Documentation consequence |
|---:|---|---|---|
| [#168](https://github.com/ArdeleanLucas/PARSE/pull/168) | `ea2ae96` | CLEF sources config/report UX | User docs should describe source reports, provider config UX, and screenshot assets. |
| [#169](https://github.com/ArdeleanLucas/PARSE/pull/169) | `796eba9` | MCP default exposes all safe ParseChatTools | README/AGENTS/MCP docs must use the full-default model, not the older curated-default wording. |
| [#170](https://github.com/ArdeleanLucas/PARSE/pull/170) | `7b68fe3` | CLEF source modal copy/API target | CLEF docs should avoid stale thesis-header copy and assume API target handling is fixed. |
| [#171](https://github.com/ArdeleanLucas/PARSE/pull/171) | `50dc53e` | CLEF real tabs/targeting | Guided Configure CLEF modal docs should describe real tab behavior, not implicit button-only flows. |
| [#172](https://github.com/ArdeleanLucas/PARSE/pull/172) | `62eb1f8` | Annotate Save Annotation bundle/scope retime | Coordinator guardrails must stop saying timestamps are absolutely immutable; retime is allowed only through explicit reviewed flows. |
| [#173](https://github.com/ArdeleanLucas/PARSE/pull/173) | `9b5ce5c` | Python requirements/runtime deps | Setup docs already received requirements/install-path updates; this report records it in the 24h ledger. |
| [#174](https://github.com/ArdeleanLucas/PARSE/pull/174) | `70cbadd` | CLEF exact doculect matching | Architecture/user docs should say CLDF/Lexibank matching is exact/folded, not substring-based. |
| [#175](https://github.com/ArdeleanLucas/PARSE/pull/175) | `4d57dab` | CLEF clear endpoint + `clef_clear_data` | API/MCP/user/developer docs must include `POST /api/clef/clear` and the new tool count. |
| [#176](https://github.com/ArdeleanLucas/PARSE/pull/176) | `c0d026f` | CLEF populate warnings banner | User/setup docs should state provider warnings surface visibly for empty/partial runs. |
| [#177](https://github.com/ArdeleanLucas/PARSE/pull/177) | `f977b43` | CLEF clear endpoint/auth alignment | Docs should preserve xAI/Grok direct-key auth expectations and avoid treating `grokipedia` as a real encyclopedia provider. |
| [#179](https://github.com/ArdeleanLucas/PARSE/pull/179) | `5153669` | Lexeme save by overlap | Annotate docs/guardrails should reflect overlap-based IPA/ORTH retime and BND midpoint rescaling as shipped. |

## Post-window rebase addendum

| PR | Merge | Area | Documentation consequence |
|---:|---|---|---|
| [#182](https://github.com/ArdeleanLucas/PARSE/pull/182) | `680a97f` | CLEF Grok LLM rename, Wiktionary translation tables, Settings tab | Conflict resolution preserves current provider id `grok_llm`, places it last after `literature`, treats Grokipedia.com as explicitly out of scope, and retires the now-executed backend handoff to `done/`. |

## Original-audit follow-up state (superseded later the same day)

| PR | State | Why it matters |
|---:|---|---|
| [#180](https://github.com/ArdeleanLucas/PARSE/pull/180) | OPEN at this report's original audit time; later merged on 2026-04-29 | Adds missing IPA interval creation on Save Annotation. Superseding calendar-day docs now treat it as shipped behavior. |

## Files refreshed by this documentation pass

| File | Reason |
|---|---|
| `AGENTS.md` | Fixed post-cutover remote wording, updated current state, MCP counts, client/server contract table, validation gates, timestamp-retime invariant, safe-work queue. |
| `README.md` | Updated first-impression counts to 55/59, CLEF clear/warnings/source reporting, and lexeme save/retime wording. |
| `docs/ai-integration.md` | Corrected stale 54-tool heading/date to 55. |
| `docs/api-reference.md` | Advanced date and added the missing frontend-helper note for `POST /api/clef/clear`. |
| `docs/architecture.md` | Updated CLEF provider order/keys, current `grok_llm` fallback naming, current MCP/chat counts, and CLEF hardening summary. |
| `docs/user-guide.md` | Added CLEF warning/clear endpoint notes and exact matching clarification. |
| `docs/getting-started.md` | Added CLEF warnings and dry-run clear/reset guidance. |
| `docs/getting-started-external-agents.md` | Corrected stale curated-default wording; current default is full 59-tool adapter surface. |
| `docs/developer-guide.md` | Added `POST /api/clef/clear` / `clef_clear_data` to CLEF extension responsibilities. |
| `docs/plans/lexibank-setup.md` | Corrected the default provider cascade to end with `literature -> grok_llm` and clarified that `grok_llm` is not a Grokipedia.com source. |
| `docs/plans/deferred-validation-backlog.md` | Refreshed the automated baseline command/count from the 2026-04-20 `npm run test -- --run` snapshot to the current `npx vitest run` / 456-test baseline from PR #179. |
| `.hermes/handoffs/README.md` | Updated lane names and historical directory compatibility. |
| `.hermes/handoffs/parse-builder/done/2026-04-28-lexeme-save-overlap-bundle.md` | Retired the stale active parse-front-end queue item after PR #179 merged. |
| `.hermes/handoffs/parse-back-end/done/2026-04-29-clef-grok-llm-and-wiktionary-tables.md` | Moved the backend handoff to `done/` after PR #182 executed and merged it. |

## Coordinator sign-off

- Last-24h doc drift found and corrected: **yes**.
- Active queue ambiguity reduced: **yes** — the PR #179-completed frontend handoff moved to `done/`; the CLEF backend follow-up was executed by PR #182 and is now also under `done/`.
- Shipped MCP counts at that audit time: **55** `ParseChatTools`, **55** default MCP task tools, **59** default adapter tools. Supersession note: PR #206 later raised current counts to **57** `ParseChatTools`, **57** default MCP task tools, and **61** default adapter tools; see `docs/reports/2026-04-30-calendar-day-merged-pr-doc-refresh.md`.
- Current shipped Annotate behavior at original audit time: PR #179 overlap retime was merged and PR #180 was pending; later 2026-04-29 docs supersede this with PR #180/#188/#195 shipped save/retime behavior. Current shipped CLEF behavior also includes PR #182 `grok_llm` naming, Wiktionary translation-table extraction, and the CLEF Settings tab.
- Superseded action: PR #180 has merged; use `2026-04-29-calendar-day-merged-pr-doc-refresh.md` for current same-day state.
