# PARSE last-48h PR documentation audit — 2026-05-16

**Audit window:** `2026-05-14T19:35:43Z` through `2026-05-16T19:35:43Z`
**Base audited:** `origin/main` `1f89497` (`docs: sync MC-400 ORTH schema docs (#505)`)
**Scope:** PRs with create/update/merge activity in the window for `ArdeleanLucas/PARSE`.

## TL;DR

Not all active docs were current after the merge wave. PR #505 fixed the MC-400 ORTH schema/user-doc drift, but this audit found remaining active-doc gaps:

1. MCP/tool-surface counts were stale after `populate_cross_survey_links` landed: code reports **61** default `ParseChatTools`, **65** default adapter tools, **41** legacy curated tools, and **45** legacy adapter tools.
2. Generic MCP/API docs omitted `populate_cross_survey_links` from exported tool tables.
3. `docs/api-reference.md` did not list `POST /api/concepts/{conceptId}/promote-survey-primary` even though the OpenAPI surface and frontend contract shipped it.
4. `AGENTS.md` still described older HF ORTH/VAD/`compute_type` and survey-chip placement language after MC-400/MC-399 follow-ups.

This PR patches those active docs and records the per-PR consequence matrix below.

## Code-truth checks

```text
default ParseChatTools: 61
legacy curated ParseChatTools: 41
workflow macros: 3
adapter default/expose_all total: 65
adapter legacy opt-out total: 45
populate_cross_survey_links in DEFAULT_MCP_TOOL_NAMES: yes
populate_cross_survey_links in LEGACY_CURATED_MCP_TOOL_NAMES: yes
```

## Per-PR documentation consequence matrix

| PR | State | Window time | Title | Documentation consequence |
|---:|---|---|---|---|
| [#467](https://github.com/ArdeleanLucas/PARSE/pull/467) | MERGED | 2026-05-15 08:38Z | [MC-394-C] refactor(react): extract SurveyBadge component from ConceptSidebar | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#468](https://github.com/ArdeleanLucas/PARSE/pull/468) | MERGED | 2026-05-15 08:37Z | [MC-394-A] feat(scripts+mcp): populate concept_survey_links from reference lexeme CSV | Cross-survey linking shipped; user guide covered workflow, this audit fixes generic MCP/API/count drift. |
| [#469](https://github.com/ArdeleanLucas/PARSE/pull/469) | MERGED | 2026-05-15 08:37Z | [MC-394-B] feat(api): POST /api/concepts/{id}/promote-survey-primary | Cross-survey linking shipped; user guide covered workflow, this audit fixes generic MCP/API/count drift. |
| [#470](https://github.com/ArdeleanLucas/PARSE/pull/470) | MERGED | 2026-05-15 08:50Z | [MC-394-E] feat(react): popover variant of SurveyBadge for 3+ linked surveys | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#471](https://github.com/ArdeleanLucas/PARSE/pull/471) | MERGED | 2026-05-15 08:51Z | [MC-394-D] feat(react): lift activeSpeaker gate and wire promote-primary | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#472](https://github.com/ArdeleanLucas/PARSE/pull/472) | MERGED | 2026-05-15 08:53Z | [MC-394-A] test(api): cover cross-survey conflict reasons | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#473](https://github.com/ArdeleanLucas/PARSE/pull/473) | MERGED | 2026-05-15 09:13Z | [MC-394-C] test(react): cover SurveyBadge legacy-fallback case | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#474](https://github.com/ArdeleanLucas/PARSE/pull/474) | MERGED | 2026-05-15 09:13Z | [MC-394-B] test(api): cover promote-survey-primary edge cases | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#475](https://github.com/ArdeleanLucas/PARSE/pull/475) | MERGED | 2026-05-15 09:23Z | [MC-394-F] fix(react): route SurveyBadge popover through onPromote in no-speaker mode | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#476](https://github.com/ArdeleanLucas/PARSE/pull/476) | MERGED | 2026-05-15 10:16Z | [MC-394-G] docs: user guide for cross-survey concept linking | Cross-survey linking shipped; user guide covered workflow, this audit fixes generic MCP/API/count drift. |
| [#477](https://github.com/ArdeleanLucas/PARSE/pull/477) | MERGED | 2026-05-15 10:07Z | [MC-394-H] feat(scripts+mcp): replace mode for cross-survey link population | Cross-survey linking shipped; user guide covered workflow, this audit fixes generic MCP/API/count drift. |
| [#478](https://github.com/ArdeleanLucas/PARSE/pull/478) | MERGED | 2026-05-15 10:24Z | [MC-394-I] fix(react): merge legacy primary with sidecar entries in sidebar bucket assembly | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#479](https://github.com/ArdeleanLucas/PARSE/pull/479) | MERGED | 2026-05-15 10:37Z | [MC-394-J] fix(react): honor speakerSurveyChoices in sidebar badge resolution | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#480](https://github.com/ArdeleanLucas/PARSE/pull/480) | MERGED | 2026-05-15 11:09Z | [MC-394-K] feat(scripts+mcp): stripped-parens fallback for cross-survey link matching | Cross-survey linking shipped; user guide covered workflow, this audit fixes generic MCP/API/count drift. |
| [#481](https://github.com/ArdeleanLucas/PARSE/pull/481) | MERGED | 2026-05-15 11:52Z | [MC-394-L] fix(scripts): prefer bare reference entry in stripped-parens index | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#482](https://github.com/ArdeleanLucas/PARSE/pull/482) | MERGED | 2026-05-15 12:10Z | [MC-394-M] fix(scripts): replace mode writes full matched patch, not delta | Cross-survey refactor/test/bugfix; no standalone prose change beyond MC-394 guide/report needed. |
| [#483](https://github.com/ArdeleanLucas/PARSE/pull/483) | MERGED | 2026-05-15 16:15Z | [MC-395-A] fix: clamp ConceptSidebar context menu to viewport edges | Small UI polish/color bugfix; no user/operator contract doc required. |
| [#484](https://github.com/ArdeleanLucas/PARSE/pull/484) | MERGED | 2026-05-15 16:58Z | [MC-396-B] feat: surface concept-group variants in sidebar | Concept variant sidebar display; existing user guide covers grouped variant rows. |
| [#485](https://github.com/ArdeleanLucas/PARSE/pull/485) | MERGED | 2026-05-15 16:59Z | [MC-396-A] feat: guard duplicate concept rows and workflow tags | Duplicate concept audit/safeguard; docs/audits report exists. |
| [#486](https://github.com/ArdeleanLucas/PARSE/pull/486) | MERGED | 2026-05-16 13:20Z | [MC-397-A] fix: survey swatch "purple" slot renders blue, not purple | Small UI polish/color bugfix; no user/operator contract doc required. |
| [#487](https://github.com/ArdeleanLucas/PARSE/pull/487) | MERGED | 2026-05-16 14:12Z | [MC-400-A] docs: HFWhisperProvider cleanup pre-research and target schema | MC-400 ORTH/HF schema/confidence; PR #505 refreshed user docs, this audit updates AGENTS/tool-surface leftovers. |
| [#488](https://github.com/ArdeleanLucas/PARSE/pull/488) | MERGED | 2026-05-16 14:13Z | feat(frontend): relocate survey badges to annotate header | Survey-chip UI location/data fixes; this audit updates active user/agent wording for Annotate header chips. |
| [#489](https://github.com/ArdeleanLucas/PARSE/pull/489) | MERGED | 2026-05-16 14:33Z | Revert "feat(frontend): relocate survey badges to annotate header" | Survey-chip UI location/data fixes; this audit updates active user/agent wording for Annotate header chips. |
| [#490](https://github.com/ArdeleanLucas/PARSE/pull/490) | MERGED | 2026-05-16 14:49Z | [MC-400-A] docs: amend HFWhisperProvider cleanup spec — drop dtype honoring + 4 review fixes | MC-400 ORTH/HF schema/confidence; PR #505 refreshed user docs, this audit updates AGENTS/tool-surface leftovers. |
| [#491](https://github.com/ArdeleanLucas/PARSE/pull/491) | MERGED | 2026-05-16 14:52Z | [MC-398-A] feat: export PARSE workspace to legacy review_tool format | review_tool export path; docs/exports/review-tool.md covers workflow and later drift fix. |
| [#492](https://github.com/ArdeleanLucas/PARSE/pull/492) | MERGED | 2026-05-16 14:56Z | [MC-399-B] feat: relocate multi-survey chip row from sidebar to SpeakerHeader | Survey-chip UI location/data fixes; this audit updates active user/agent wording for Annotate header chips. |
| [#493](https://github.com/ArdeleanLucas/PARSE/pull/493) | MERGED | 2026-05-16 15:10Z | [MC-398-C] feat: review_tool sync wrapper | review_tool export path; docs/exports/review-tool.md covers workflow and later drift fix. |
| [#494](https://github.com/ArdeleanLucas/PARSE/pull/494) | MERGED | 2026-05-16 16:09Z | [MC-400-C] refactor: VAD config removal + ai_config migrator + strict ortho reader | MC-400 ORTH/HF schema/confidence; PR #505 refreshed user docs, this audit updates AGENTS/tool-surface leftovers. |
| [#495](https://github.com/ArdeleanLucas/PARSE/pull/495) | MERGED | 2026-05-16 16:33Z | [MC-400-B] refactor: typed ConfidenceScore + downstream consumer audit | MC-400 ORTH/HF schema/confidence; PR #505 refreshed user docs, this audit updates AGENTS/tool-surface leftovers. |
| [#496](https://github.com/ArdeleanLucas/PARSE/pull/496) | MERGED | 2026-05-16 16:44Z | [MC-399-C] fix: surface multi-survey chips in SpeakerHeader (data feed + Option B styling) | Survey-chip UI location/data fixes; this audit updates active user/agent wording for Annotate header chips. |
| [#497](https://github.com/ArdeleanLucas/PARSE/pull/497) | MERGED | 2026-05-16 18:09Z | [MC-398-B] feat: populate analytical fields from PARSE enrichments | review_tool export path; docs/exports/review-tool.md covers workflow and later drift fix. |
| [#498](https://github.com/ArdeleanLucas/PARSE/pull/498) | MERGED | 2026-05-16 18:09Z | [MC-400-A] fix: HF Whisper runtime warnings + compatibility probe | MC-400 ORTH/HF schema/confidence; PR #505 refreshed user docs, this audit updates AGENTS/tool-surface leftovers. |
| [#499](https://github.com/ArdeleanLucas/PARSE/pull/499) | MERGED | 2026-05-16 18:12Z | [MC-399-D] fix: merge concept.surveys with sidecar instead of overwriting on configStore hydration | Survey-chip UI location/data fixes; this audit updates active user/agent wording for Annotate header chips. |
| [#500](https://github.com/ArdeleanLucas/PARSE/pull/500) | MERGED | 2026-05-16 18:40Z | [MC-399-E] fix: merge concept.surveys with sidecar in activeResolvedSurvey useMemo | Survey-chip UI location/data fixes; this audit updates active user/agent wording for Annotate header chips. |
| [#501](https://github.com/ArdeleanLucas/PARSE/pull/501) | MERGED | 2026-05-16 18:38Z | [MC-398-D] fix: try concept_id then label for enrichment lookups | review_tool export path; docs/exports/review-tool.md covers workflow and later drift fix. |
| [#502](https://github.com/ArdeleanLucas/PARSE/pull/502) | MERGED | 2026-05-16 18:47Z | [MC-398-E] fix: drop INCLUDE_SPECTROGRAMS drift + cover non-Mapping enrichments | review_tool export path; docs/exports/review-tool.md covers workflow and later drift fix. |
| [#503](https://github.com/ArdeleanLucas/PARSE/pull/503) | MERGED | 2026-05-16 18:53Z | [MC-399-F] fix: honor speakerSurveyChoices in chip toggle + color both pills | Survey-chip UI location/data fixes; this audit updates active user/agent wording for Annotate header chips. |
| [#504](https://github.com/ArdeleanLucas/PARSE/pull/504) | OPEN | 2026-05-16 19:18Z | [MC-401-A] fix: Batch Report banner contrast + modal width overflow | Open PR; not documented as shipped. No docs required until merge unless UI guide needs contrast/width notes. |
| [#505](https://github.com/ArdeleanLucas/PARSE/pull/505) | MERGED | 2026-05-16 19:34Z | [MC-400-D] docs: sync user-facing docs to sectioned ORTH schema + confidence provenance | MC-400 ORTH/HF schema/confidence; PR #505 refreshed user docs, this audit updates AGENTS/tool-surface leftovers. |

## Files refreshed by this audit

| File | Why |
|---|---|
| `AGENTS.md` | Align coordinator context with MC-400 strict HF ORTH config, MC-399 survey-chip placement, and current MCP tool counts. |
| `docs/ai-integration.md` | Add `populate_cross_survey_links` to the tool table and correct 61/65/41/45 counts. |
| `docs/api-reference.md` | Document `promote-survey-primary`, add `populate_cross_survey_links` to the legacy MCP table, and correct MCP counts. |
| `docs/getting-started-external-agents.md` | Correct external-agent MCP counts and mention `populate_cross_survey_links`. |
| `README.md` | Keep the public automation count aligned without adding implementation detail. |
| `docs/mcp-guide.md` | Correct HTTP/stdin MCP surface counts. |
| `docs/mcp_agent_roadmap.md` | Correct MCP roadmap shipped-surface counts. |
| `docs/user-guide.md` | Update active survey-chip wording to the Annotate header row and use generic survey examples. |
| `docs/user-guides/cross-survey-linking.md` | Mention the Annotate header chip row and speaker-specific chip interaction. |

## Sign-off

- **Cross-survey docs:** now cover CSV/MCP usage, merge/replace behavior, parenthetical stripping, UI badges/header chips, and promote-primary API behavior.
- **review_tool docs:** already covered by `docs/exports/review-tool.md`; no additional active-doc change needed.
- **MC-400 docs:** PR #505 fixed sectioned ORTH schema/confidence prose; this audit only corrected remaining AGENTS/tool-count leftovers.
- **Open PR #504:** excluded from shipped docs; leave pending until merge.
