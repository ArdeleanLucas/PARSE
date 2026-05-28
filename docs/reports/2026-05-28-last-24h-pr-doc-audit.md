# Last-24h PR documentation audit — 2026-05-28

- **Audit window:** rolling 24 hours, `2026-05-27T21:43:41+02:00` → `2026-05-28T21:43:41+02:00` (`2026-05-27T19:43:41Z` → `2026-05-28T19:43:41Z`).
- **Repo:** `ArdeleanLucas/PARSE` via `/home/lucas/gh/tarahassistant/PARSE-rebuild` / isolated docs worktree.
- **Base reviewed:** `origin/main` = `16f6cf9c` (`fix(frontend): pivot annotate editor by realization (#577)`).
- **Coverage:** 31 PRs touched in the window: **30/30 merged PRs reviewed** plus **1 closed draft (#545)**; **0 open PRs** at audit time.

## Executive finding

The recent refactor wave did leave active docs stale in four places:

1. **MCP/tool counts and tool catalogs** were behind code. Code truth now reports `DEFAULT_MCP_TOOL_NAMES=63`, `LEGACY_CURATED_MCP_TOOL_NAMES=43`, workflow macros `3`, adapter self-inspection `1`, default/all adapter total `67`, and legacy opt-out total `47`.
2. **Concept/elicitation UI docs** still described the removed duplicate-concept-row workflow after MC-418/MC-421/MC-426. Current behavior is add/delete per-speaker elicitation intervals on the same canonical concept id, with render-time A/B/C realization keys.
3. **API/developer docs** omitted `POST /api/annotations/intervals/delete`, now the selected-realization delete endpoint.
4. **Review export / release-note status** still said default-mode review export was unsafe/in flight. MC-422/MC-424 now fixed and acceptance-tested the default path; MC-425 also changed clarifier-collapse status.

## Code-truth count check

```text
DEFAULT_MCP_TOOL_NAMES=63
LEGACY_CURATED_MCP_TOOL_NAMES=43
DEFAULT_MCP_WORKFLOW_TOOL_NAMES=3
adapter self-inspection tool=1
default/all adapter total=67
legacy curated adapter total=47
export_review_data in DEFAULT/LEGACY=yes/yes
migrate_concept_suffix_pollution in DEFAULT/LEGACY=yes/yes
populate_cross_survey_links in DEFAULT/LEGACY=yes/yes
```

## PR-by-PR documentation consequence matrix

| PR | State | Window timestamp | Merge SHA | Scope | Documentation consequence |
|---:|---|---|---|---|---|
| [#545](https://github.com/ArdeleanLucas/PARSE/pull/545) | CLOSED | `2026-05-28T09:32:08Z` | `—` | Add sociolinguistic survey report review skill | Closed draft; no shipped behavior. No active docs changed for it. |
| [#546](https://github.com/ArdeleanLucas/PARSE/pull/546) | MERGED | `2026-05-28T09:32:57Z` | `1a7b3671` | [MC-418-A] feat: assignVariantLetters helper for render-time variant rendering | Render-time variant-letter helper. Covered by release notes; no additional active doc beyond audit report. |
| [#547](https://github.com/ArdeleanLucas/PARSE/pull/547) | MERGED | `2026-05-28T09:45:51Z` | `ce901441` | [MC-418-C] refactor: consolidate concept canonical helpers | Backend canonical helper consolidation. Covered by release notes; no extra user/operator doc needed. |
| [#548](https://github.com/ArdeleanLucas/PARSE/pull/548) | MERGED | `2026-05-28T10:00:06Z` | `9462c63f` | [MC-418-H] feat: expose export_review_data as MCP/chat tool (#533) | `export_review_data` added to MCP/chat. Updated MCP counts, AI/API/MCP docs, and agent-skill pages. |
| [#549](https://github.com/ArdeleanLucas/PARSE/pull/549) | MERGED | `2026-05-28T10:12:24Z` | `b9f66c16` | [MC-419-A] fix(tests): isolate ortho cascade-guard validation | ORTH deselect guidance cleanup. Already touched AGENTS/tests; recorded as no further doc drift. |
| [#550](https://github.com/ArdeleanLucas/PARSE/pull/550) | MERGED | `2026-05-28T10:45:35Z` | `5fbb3218` | [MC-418-B] feat: replace duplicate-variant button with + Add elicitation; wire assignVariantLetters into concept-tier | `+ Add elicitation` replaces duplicate-variant workflow. Updated README/user/developer/frontend docs. |
| [#551](https://github.com/ArdeleanLucas/PARSE/pull/551) | MERGED | `2026-05-28T10:44:39Z` | `d74524e5` | [MC-418-D] refactor: slot-aware concept allocator with triple-keyed lookup | Slot-aware allocator. Release notes already cover; no additional active doc required. |
| [#552](https://github.com/ArdeleanLucas/PARSE/pull/552) | MERGED | `2026-05-28T10:58:04Z` | `e84269da` | [MC-418-E] Remove duplicate concept variant endpoint | Duplicate concept endpoint removed. Updated stale README/user/developer/API wording away from duplicate-row workflow. |
| [#553](https://github.com/ArdeleanLucas/PARSE/pull/553) | MERGED | `2026-05-28T11:11:06Z` | `c6eab734` | [MC-420-A] style: fix body indent on export_review_data + _review_export_invalid_args | Indent/style-only export tool cleanup. No docs needed. |
| [#554](https://github.com/ArdeleanLucas/PARSE/pull/554) | MERGED | `2026-05-28T11:17:38Z` | `4e76af16` | [MC-418-F] feat: concept identity migration script core (#529 + #541) | Migration script core. Updated MCP/agent-skill docs for migration tool context. |
| [#555](https://github.com/ArdeleanLucas/PARSE/pull/555) | MERGED | `2026-05-28T11:16:38Z` | `563968ae` | [MC-419-B] fix(ci): drop ortho deselect from CI workflow + extend guidance regression | CI deselect removal. Existing AGENTS/CI guidance is current; no extra docs. |
| [#556](https://github.com/ArdeleanLucas/PARSE/pull/556) | MERGED | `2026-05-28T11:44:17Z` | `90a20768` | [MC-418-G] feat: migration verification + idempotence + MCP wrapper + Fail01 regression | Migration MCP wrapper exposed. Updated MCP counts and agent-skill docs. |
| [#557](https://github.com/ArdeleanLucas/PARSE/pull/557) | MERGED | `2026-05-28T12:24:19Z` | `975b67b7` | [MC-418-K] fix(migration): canonicalize standalone (X)-suffix rows + re-key survey-overlap.json | Migration standalone/survey-overlap fix. Release notes cover; audit report records no further drift. |
| [#558](https://github.com/ArdeleanLucas/PARSE/pull/558) | MERGED | `2026-05-28T13:00:36Z` | `3f523386` | [MC-418-I] refactor: retire --legacy-anchor + MC-415-C strip after canonicalization (#537) | `--legacy-anchor` deprecation. Release note status superseded by MC-422/424 acceptance updates. |
| [#559](https://github.com/ArdeleanLucas/PARSE/pull/559) | MERGED | `2026-05-28T13:11:52Z` | `1cfc24a6` | [MC-418-J] docs: concept identity refactor release notes + parent close-out | Concept identity release notes. Superseded stale pending/regression sections where later PRs changed status. |
| [#560](https://github.com/ArdeleanLucas/PARSE/pull/560) | MERGED | `2026-05-28T13:31:32Z` | `ce5cd62f` | [MC-418-J] docs: mark release-note PR merged | Release-note status row fix. No further docs beyond current audit. |
| [#563](https://github.com/ArdeleanLucas/PARSE/pull/563) | MERGED | `2026-05-28T14:19:14Z` | `747c844c` | [MC-421-A] refactor(frontend): unified selectedRealizationKey state + chip path unification | `selectedRealizationKey` unifies chip selection. Updated user/frontend/architecture docs. |
| [#564](https://github.com/ArdeleanLucas/PARSE/pull/564) | MERGED | `2026-05-28T14:43:38Z` | `d323769f` | [MC-421-C] feat: delete-this-interval chip context menu + backend endpoint | `Delete this interval` UI + `POST /api/annotations/intervals/delete`. Updated API/developer/user docs. |
| [#565](https://github.com/ArdeleanLucas/PARSE/pull/565) | MERGED | `2026-05-28T15:05:47Z` | `964fc0d8` | [MC-421-B] feat(frontend): consume selectedRealizationKey in right panel + keyboard nav | Right panel + keyboard navigation consume realization selection. Updated user/frontend docs. |
| [#566](https://github.com/ArdeleanLucas/PARSE/pull/566) | MERGED | `2026-05-28T14:55:45Z` | `bb52c117` | [MC-422-A] docs: diagnostic — default-mode export divergence vs anchored mode (#562) | Default-export diagnostic. Added supersession note after fixes landed. |
| [#567](https://github.com/ArdeleanLucas/PARSE/pull/567) | MERGED | `2026-05-28T15:05:19Z` | `d9f79303` | [MC-422-G] docs: known regression note for #559 release notes (#562) | Known-regression release-note warning. Replaced with current repaired/default-mode status. |
| [#568](https://github.com/ArdeleanLucas/PARSE/pull/568) | MERGED | `2026-05-28T15:39:29Z` | `dc5d0996` | [MC-422-B] fix: default-mode cross-tier IPA + ortho join (#562 sub-bugs A+C) | Default IPA/ORTH cross-tier fix. Reflected in release-note/diagnostic supersession. |
| [#569](https://github.com/ArdeleanLucas/PARSE/pull/569) | MERGED | `2026-05-28T15:47:29Z` | `9dcd9e8f` | [MC-422-C] fix(backend): default-mode contact refs use workspace cache + accept script entries (#562 sub-bug B) | Workspace contact-cache/script-entry fix. Reflected in review_tool docs and supersession notes. |
| [#570](https://github.com/ArdeleanLucas/PARSE/pull/570) | MERGED | `2026-05-28T16:13:34Z` | `60777c38` | [MC-422-D] fix: clarifier-tolerant validator + export-time dedup (#561 Option 1 + #562 sub-bug D) | Clarifier-tolerant validator/export dedup. Reflected in release-note clarifier status. |
| [#571](https://github.com/ArdeleanLucas/PARSE/pull/571) | MERGED | `2026-05-28T17:10:35Z` | `4ef6605c` | [MC-423-A] refactor(backend): consolidate _shift_annotation_intervals + concept-identity helper into python/annotation_offset.py (#528) | Backend annotation-offset refactor; behavior-preserving. No user/operator docs required. |
| [#572](https://github.com/ArdeleanLucas/PARSE/pull/572) | MERGED | `2026-05-28T17:07:07Z` | `ac8049d5` | [MC-422-F] feat(scripts): SPEAKERS env-var forwarding + acceptance verify + prepare review_tool push (refs #537 #562) | `SPEAKERS` sync wrapper + acceptance. Updated review_tool export docs and release-note status. |
| [#573](https://github.com/ArdeleanLucas/PARSE/pull/573) | MERGED | `2026-05-28T17:37:13Z` | `b86732c2` | [MC-424-A] fix: close review export coverage gaps vs anchored (refs #562) | Default-vs-anchored gap fixes. Reflected in release-note acceptance status. |
| [#574](https://github.com/ArdeleanLucas/PARSE/pull/574) | MERGED | `2026-05-28T18:03:34Z` | `9ebd74b3` | [MC-424-B] docs: review_tool re-prepare after MC-424-A coverage fixes (refs #562) | Review_tool re-prepare docs. Reflected in release-note status; no extra active docs. |
| [#575](https://github.com/ArdeleanLucas/PARSE/pull/575) | MERGED | `2026-05-28T18:36:20Z` | `7b159b50` | [MC-425-A] feat(migration): clarifier-collapse pass + δ-format notes append (#561 Option 2) | Clarifier-collapse migration extension. Updated release-note clarifier status and agent-skill migration page. |
| [#576](https://github.com/ArdeleanLucas/PARSE/pull/576) | MERGED | `2026-05-28T18:57:04Z` | `84b9ea49` | [MC-425-B] chore(migration): live clarifier-collapse run on /home/lucas/parse-workspace + close #561 | Live clarifier-collapse acceptance. Linked from release notes; no further active user doc required. |
| [#577](https://github.com/ArdeleanLucas/PARSE/pull/577) | MERGED | `2026-05-28T19:42:16Z` | `16f6cf9c` | [MC-426-A] fix(frontend): annotate-view IPA/ortho editor pivots on chip selection (MC-421-B gap) | Annotate editor pivots by selected realization. Updated user/frontend docs. |

## Files refreshed

| File | Why |
|---|---|
| `README.md` | Public landing-page count and Compare copy no longer matched the 67-tool MCP surface or the removed duplicate-row workflow. |
| `AGENTS.md` | Coordinator/agent MCP count contract was stale after `export_review_data` + migration tools joined default/legacy MCP. |
| `docs/getting-started-external-agents.md` | External-agent setup counts and examples needed current 67/47 tool surfaces and new review/migration tool examples. |
| `docs/mcp-guide.md`, `docs/mcp/schema.md`, `docs/mcp_agent_roadmap.md` | MCP narrative/schema/status docs carried old 60/64/40/44 or 61/65/41/45 counts. |
| `docs/ai-integration.md`, `docs/api-reference.md` | Built-in tool table missed `export_review_data` / `migrate_concept_suffix_pollution`; API docs missed interval-delete and current counts. |
| `docs/architecture.md`, `docs/frontend-architecture.md`, `docs/user-guide.md`, `docs/developer-guide.md` | Current realization-key/add-elicitation/delete-interval behavior needed to replace duplicate concept-row prose. |
| `docs/exports/review-tool.md` | `sync_review_tool.sh` now prefers workspace contact config and forwards `SPEAKERS`; docs still showed old env contract. |
| `docs/release-notes/2026-05-28-concept-identity-refactor.md` | Later MC-422/424/425 PRs superseded the same-day known-regression and clarifier status sections. |
| `docs/diagnostics/2026-05-28-mc-422-default-export-divergence.md` | Added a supersession note preserving the diagnostic while preventing readers from treating fixed gaps as current. |
| `docs/agent-skills/parse-mcp-tools/**` | Portable MCP tool skill docs now match the 67-tool catalog and include the three missing default/legacy tools. |

## Open follow-ups

None from GitHub PR state at audit time (`gh pr list --repo ArdeleanLucas/PARSE --state open` returned `0`). The only non-shipped PR in the window was closed draft [#545](https://github.com/ArdeleanLucas/PARSE/pull/545), which had no repository effect.

## Coordinator sign-off

- **Parity/doc confidence:** good after the active-doc patch; no implementation behavior changes were required for this audit.
- **Known historical docs:** older dated reports/plans retain historical counts and are not rewritten except where a same-day active release note/diagnostic needed an explicit supersession note.
- **Next trigger:** rerun this audit after the next MCP/tool-surface addition, review_tool push, or realization-key UI change.
