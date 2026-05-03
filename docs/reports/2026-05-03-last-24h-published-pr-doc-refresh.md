# PARSE last-24h published PR documentation refresh — 2026-05-03

## Scope and grounding

- Audit request: review all PRs **published/opened** in the rolling last 24 hours and ensure docs are updated.
- Audit window used: `2026-05-02T22:55:33+02:00` through `2026-05-03T22:55:33+02:00` local time (`2026-05-02T20:55:33Z` through `2026-05-03T20:55:33Z`).
- Grounded repo: `/home/lucas/gh/tarahassistant/PARSE-rebuild`, remote `git@github.com:ArdeleanLucas/PARSE.git`.
- Docs worktree: `/home/lucas/gh/worktrees/PARSE/docs-2026-05-03-last-24h-pr-refresh` on branch `docs/2026-05-03-last-24h-pr-refresh`.
- `origin/main` at branch cut: `27a9062` (merge of PR #263).
- Coverage: **10/10 PRs published in the window reviewed** (#255-#264). **9/10 were merged** at initial audit (#255-#263); **#264 was open** and is documented as pending, not shipped.

## Evidence commands

```bash
date -Is && date -u -Is
git -C /home/lucas/gh/tarahassistant/PARSE-rebuild fetch origin --quiet --prune
gh api --paginate 'repos/ArdeleanLucas/PARSE/pulls?state=all&sort=created&direction=desc&per_page=100'
gh pr view <255..264> --repo ArdeleanLucas/PARSE --json number,title,state,isDraft,createdAt,mergedAt,closedAt,url,author,headRefName,baseRefName,body,files,commits,statusCheckRollup
PYTHONPATH=python python3 - <<'PY'
from pathlib import Path
from ai.chat_tools import ParseChatTools, DEFAULT_MCP_TOOL_NAMES, LEGACY_CURATED_MCP_TOOL_NAMES, REGISTRY
from ai.workflow_tools import DEFAULT_MCP_WORKFLOW_TOOL_NAMES
from external_api.catalog import build_mcp_http_catalog
root = Path.cwd()
tools = ParseChatTools(project_root=root)
print(len(REGISTRY), len(tools.tool_names()), len(DEFAULT_MCP_TOOL_NAMES), len(LEGACY_CURATED_MCP_TOOL_NAMES), len(DEFAULT_MCP_WORKFLOW_TOOL_NAMES))
print(build_mcp_http_catalog(project_root=root, mode='default')['count'])
print(build_mcp_http_catalog(project_root=root, mode='all')['count'])
PY
```

Code count check on current main/worktree: `REGISTRY=58`, `ParseChatTools=58`, `DEFAULT_MCP_TOOL_NAMES=58`, `LEGACY_CURATED_MCP_TOOL_NAMES=38`, workflow macros `3`, default/all MCP HTTP catalog `62`, active local config legacy catalog `42`, `set_concept_field` present.

## Published PR documentation-consequence matrix

| PR | State at audit | Published / merged | Reviewed shipped behavior | Documentation consequence |
|---|---:|---|---|---|
| [#255](https://github.com/ArdeleanLucas/PARSE/pull/255) `fix(backend): harden full-pipeline OOM recovery` | Merged | Created `2026-05-03T12:50:07Z`; merged `2026-05-03T14:03:04Z` | Adds host-memory preflight for full-pipeline work via `PARSE_FULL_PIPELINE_MIN_MEM_GB`, structured `oom_suspect` job details, durable job snapshots under `PARSE_JOB_SNAPSHOT_DIR` / `.parse/jobs`, restart recovery as `server_restarted`, and launcher warning when `PARSE_COMPUTE_MODE` is unset. | Updated `AGENTS.md`, `docs/api-reference.md`, `docs/developer-guide.md`, and `docs/getting-started.md` so operators and agents see OOM/restart semantics and knobs. |
| [#256](https://github.com/ArdeleanLucas/PARSE/pull/256) `A/B realization viewer + canonical selection in speaker forms (FE)` | Merged | Created `2026-05-03T14:00:41Z`; merged `2026-05-03T14:53:41Z` | Compare speaker forms surface all matching IPA realizations, A/B/C pills, IPA/ORTH/time/play context, and canonical per-speaker picks persisted as `manual_overrides.canonical_realizations`. | Updated README Compare summary, `docs/user-guide.md`, `docs/architecture.md`, and `AGENTS.md`. |
| [#257](https://github.com/ArdeleanLucas/PARSE/pull/257) `Add source_item concept schema and MCP field tool` | Merged | Created `2026-05-03T14:55:40Z`; merged `2026-05-03T15:10:03Z` | Current `concepts.csv` schema is `id,concept_en,source_item,source_survey,custom_order`; Audition cue prefixes feed `source_item`; `set_concept_field` safely edits `source_item`, `source_survey`, or `custom_order`; MCP/chat counts rise to 58 parse tools / 62 adapter tools. | PR #257 already touched core schema/MCP docs; this pass fixed remaining 57/61 and legacy 36/40 drift in README, MCP docs, API docs, roadmap, and prior reports. |
| [#258](https://github.com/ArdeleanLucas/PARSE/pull/258) `Show source values in concept sidebar` | Merged | Created `2026-05-03T15:24:54Z`; merged `2026-05-03T15:30:00Z` | Concept sidebar badges prefer `sourceSurvey sourceItem`, then `sourceItem`, then `#id`; sort tab label is `Source` and source-aware ordering auto-promotes after values load unless the user touched sorting. | Updated README, `docs/user-guide.md`, and `AGENTS.md` Compare/source metadata sections. |
| [#259](https://github.com/ArdeleanLucas/PARSE/pull/259) `chore(frontend): drop dead survey badge prefix` | Merged | Created `2026-05-03T15:36:20Z`; merged `2026-05-03T15:42:51Z` | Removes unused `surveyBadgePrefix` helper/test only; no user/operator contract changes. | No active-doc content change required beyond this matrix. |
| [#260](https://github.com/ArdeleanLucas/PARSE/pull/260) `feat(compare): group source-item variants in speaker forms` | Merged | Created `2026-05-03T15:52:59Z`; merged `2026-05-03T18:10:32Z` | Concepts sharing a `source_item` render as one source-item row with variant realizations; source-item canonical picks use the `source_item` override key; singleton behavior preserved. | Updated README, `docs/user-guide.md`, `docs/architecture.md`, and `AGENTS.md`. |
| [#261](https://github.com/ArdeleanLucas/PARSE/pull/261) `feat: classify audition cue source surveys` | Merged | Created `2026-05-03T17:03:25Z`; merged `2026-05-03T18:02:50Z` | Audition cue parsing returns `(source_item, source_survey, label)` for KLQ, EXT, and JBIL families; onboarding/merge/backfill propagate `source_survey` conservatively. | Updated `docs/runtime/audition-csv-import.md` and `AGENTS.md` source-survey wording. |
| [#262](https://github.com/ArdeleanLucas/PARSE/pull/262) `fix(compare): match singleton concept intervals by key` | Merged | Created `2026-05-03T18:16:52Z`; merged `2026-05-03T18:38:03Z` | Singleton speaker-form interval matching uses stable `Concept.key` / annotation `concept_id`, not emitted sequential sidebar ids; grouped/source-item matching still uses variant concept keys. | Documented in `AGENTS.md`; no separate user-facing how-to change needed because this is a correctness fix under existing identity-match contract. |
| [#263](https://github.com/ArdeleanLucas/PARSE/pull/263) `feat(frontend): add concept merge action` | Merged | Created `2026-05-03T20:15:39Z`; merged `2026-05-03T20:21:23Z` | Adds sidebar right-click merge picker, unmerge action, absorbed-count badge, and `manual_overrides.concept_merges` so Compare speaker forms combine underlying concept ids without rewriting concepts or annotations. | Updated README, `docs/user-guide.md`, `docs/architecture.md`, and `AGENTS.md`. |
| [#264](https://github.com/ArdeleanLucas/PARSE/pull/264) `fix(frontend): scope concept merges to compare mode` | Open at initial audit | Created `2026-05-03T20:44:31Z` | Proposed follow-up scopes concept-merge overrides to Compare mode so Annotate keeps raw concept rows independently navigable. | Not documented as shipped. This report records the pending follow-up; active docs intentionally avoid claiming Compare-only scoping until #264 merges. |

## Files refreshed

| File | Why |
|---|---|
| `AGENTS.md` | Added current shipped notes for full-pipeline OOM/restart recovery and Compare source-item / canonical realization / concept-merge behavior; marks #264 as open/pending. |
| `README.md` | Fixed stale 57/61 MCP counts to 58/62 and refreshed first-impression Compare bullets for source badges, source-item variants, canonical realization picks, and concept merges. |
| `docs/api-reference.md` | Added full-pipeline OOM/restart job semantics and fixed legacy MCP 36/40 wording to 38/42. |
| `docs/developer-guide.md` | Added `PARSE_FULL_PIPELINE_MIN_MEM_GB`, `PARSE_JOB_SNAPSHOT_DIR`, and launcher warning behavior to compute runtime notes. |
| `docs/getting-started.md` | Added operator environment variables and runtime notes for full-pipeline memory preflight and durable job snapshots. |
| `docs/mcp-schema.md` | Fixed default/all adapter totals from 61 to 62. |
| `docs/mcp-guide.md` | Fixed default/all adapter totals from 61 to 62. |
| `docs/mcp_agent_roadmap.md` | Fixed current-state totals from 61 to 62. |
| `docs/runtime/audition-csv-import.md` | Added EXT alongside KLQ/JBIL source-survey examples. |
| `docs/user-guide.md` | Documented Compare source badges, source-item variant rows, canonical realization picks, and manual concept merges. |
| `docs/architecture.md` | Documented `canonical_realizations` and `concept_merges` as reversible enrichment-layer manual overrides. |
| `docs/reports/2026-04-29-parse-last-24h-change-log.md` | Added numeric supersession note for PR #257's current 58/62 MCP surface. |
| `docs/reports/2026-04-30-calendar-day-merged-pr-doc-refresh.md` | Added numeric supersession note for PR #257's current 58/62 MCP surface. |
| `docs/reports/2026-05-03-last-24h-published-pr-doc-refresh.md` | Added this audit/sign-off report. |

## Handoff queue review

The clean docs worktree contains only the tracked historical `.hermes/handoffs/` queue files from `origin/main`; the many newer untracked handoffs visible in the canonical clone are not tracked on main and were not staged into this docs PR. No tracked active handoff matched #255-#264, so no queue-file lifecycle move was made in this pass.

## Coordinator sign-off

- Published-PR coverage: **10/10 reviewed**.
- Shipped-behavior docs: **9/9 merged PRs covered** where user/operator/agent contracts changed.
- Pending behavior: **#264 open**, documented only as pending; active docs do not claim Compare-only merge scoping as shipped.
- MCP count truth: code-verified as **58** parse tools, **62** default/all adapter tools, **38/42** legacy curated opt-out.
