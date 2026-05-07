# PARSE post-#265 merged PR documentation refresh — 2026-05-07

## Scope and grounding

- Audit request: update PARSE docs from PRs merged since the last broad coordinator docs update.
- Baseline selected: [PR #265](https://github.com/ArdeleanLucas/PARSE/pull/265), `docs: refresh 2026-05-03 published PR docs`, merged `2026-05-03T21:13:04Z`.
- Later one-off docs/audit PRs (#266, #274, #285, #300) are included as merged PRs in scope but are not treated as the broad baseline.
- Grounded repo: `/home/lucas/gh/tarahassistant/PARSE-rebuild`, remote `git@github.com:ArdeleanLucas/PARSE.git`.
- Docs worktree: `/home/lucas/gh/worktrees/PARSE-rebuild/docs-post-265-merged-pr-refresh` on branch `docs/post-265-merged-pr-refresh`.
- `origin/main` at initial branch cut: `4bea7a8` (merge of PR #303); freshness rebase target: `9036ae1` (merge of PR #305).
- Coverage: **40/40 PRs merged after PR #265 reviewed**.

## Evidence commands

```bash
git fetch origin --quiet --prune
gh pr list --repo ArdeleanLucas/PARSE --state merged --json number,title,mergedAt,url,author,headRefName,baseRefName --limit 100
gh pr view <post-265 PR> --repo ArdeleanLucas/PARSE --json number,title,mergedAt,url,headRefName,baseRefName,files,commits,body
```

Code truth was cross-checked against:

- `src/api/contracts/annotation-data.ts` for `/api/lexeme/run_ortho` and `/api/lexeme/run_ipa` helpers.
- `src/api/contracts/concepts.ts` and `python/test_concept_duplicate_endpoint.py` for A/B concept duplication semantics.
- `src/api/contracts/project-config-and-pipeline-state.ts`, `src/api/types.ts`, `python/survey_overlap.py`, and `python/external_api/openapi.py` for survey-overlap sidecar shape.
- `python/app/http/lexeme_rerun_handlers.py`, `python/server_routes/lexeme_rerun.py`, and `python/test_orth_no_parrot_regression.py` for pad values and prompt-suppression behavior.
- `python/test_annotation_round_trip_ipa_sidecars.py`, `src/stores/annotation/actions.ts`, and `src/ParseUI.tsx` for speaker-local `concept_tags` behavior.

## Merged PR documentation-consequence matrix

| PR | Merged | Shipped behavior reviewed | Documentation consequence |
|---|---|---|---|
| [#264](https://github.com/ArdeleanLucas/PARSE/pull/264) | 2026-05-04T07:19Z | Concept merges are Compare-mode-only; Annotate keeps raw concept rows. | Updated #265-era pending note, `README.md`, `docs/user-guide.md`, `docs/architecture.md`, and `AGENTS.md`. |
| [#267](https://github.com/ArdeleanLucas/PARSE/pull/267) | 2026-05-04T08:35Z | Backend persists `AnnotationRecord.concept_tags` per speaker. | Updated sidecar architecture, user/architecture/developer docs, and AGENTS concept-tag state. |
| [#266](https://github.com/ArdeleanLucas/PARSE/pull/266) | 2026-05-04T08:37Z | Published concept-tag collision audit and sidecar architecture plan. | Preserved report; updated sidecar status from companion/plan wording to shipped implementation. |
| [#268](https://github.com/ArdeleanLucas/PARSE/pull/268) | 2026-05-04T08:50Z | Empty concept-tag memberships normalize away instead of writing blank sidecars. | Added empty-sidecar normalization to architecture/user/dev docs and AGENTS. |
| [#269](https://github.com/ArdeleanLucas/PARSE/pull/269) | 2026-05-04T08:56Z | Adds Claude PR review workflow. | No active user/API docs change required; CI workflow exists under `.github/workflows/`. |
| [#270](https://github.com/ArdeleanLucas/PARSE/pull/270) | 2026-05-04T10:52Z | Frontend writes/reads speaker-local concept tag memberships. | Updated README, user guide, architecture, developer guide, and AGENTS. |
| [#271](https://github.com/ArdeleanLucas/PARSE/pull/271) | 2026-05-04T12:21Z | Source-item backfill matches by concept label only. | Covered in the source-item/import hardening cluster in AGENTS/report; no standalone user/API doc needed. |
| [#273](https://github.com/ArdeleanLucas/PARSE/pull/273) | 2026-05-04T16:58Z | MCP/processed-speaker onboarding preserves the current `concepts.csv` schema. | Added to source-item/import hardening cluster in AGENTS/report; existing runtime import docs already describe the schema. |
| [#272](https://github.com/ArdeleanLucas/PARSE/pull/272) | 2026-05-04T16:59Z | Adds smarter source-item backfill matching. | Covered in source-item/import hardening cluster; no new route/user surface. |
| [#274](https://github.com/ArdeleanLucas/PARSE/pull/274) | 2026-05-04T17:46Z | README readability pass. | Preserved; this refresh builds on the rewritten README structure. |
| [#275](https://github.com/ArdeleanLucas/PARSE/pull/275) | 2026-05-05T20:23Z | Lexeme search can filter tiers. | Updated README/user guide/AGENTS to mention tier-filtered word finder. |
| [#279](https://github.com/ArdeleanLucas/PARSE/pull/279) | 2026-05-05T21:57Z | Annotate displays intervals past source-audio end gracefully. | Updated user guide and AGENTS manual-review notes. |
| [#277](https://github.com/ArdeleanLucas/PARSE/pull/277) | 2026-05-05T21:58Z | Retires OpenClaw clone guidance and locks recurrence guard. | Already in AGENTS/memory; no further active-doc patch required here. |
| [#278](https://github.com/ArdeleanLucas/PARSE/pull/278) | 2026-05-05T21:58Z | Processed-speaker import preserves concept schema, copies WAV idempotently, refreshes `.parse.json`. | Added to source-item/import hardening cluster; existing speaker-import docs remain current. |
| [#276](https://github.com/ArdeleanLucas/PARSE/pull/276) | 2026-05-05T22:26Z | Adds API regression guards for Khan workspace misconfig. | Test-only protection; no user/API contract change. |
| [#280](https://github.com/ArdeleanLucas/PARSE/pull/280) | 2026-05-05T22:26Z | Documents Khan rain/ice concept backfill. | Existing report preserved; no broader docs change needed. |
| [#282](https://github.com/ArdeleanLucas/PARSE/pull/282) | 2026-05-06T09:34Z | Documents Khan01 three-WAV concat/re-import evidence. | Existing report preserved; no broader docs change needed. |
| [#283](https://github.com/ArdeleanLucas/PARSE/pull/283) | 2026-05-06T09:49Z | ORTH editor avoids saving fallback `ortho_words` as reviewed ORTH. | Existing user/AGENTS direct-ORTH wording verified; no extra patch beyond current-state date. |
| [#284](https://github.com/ArdeleanLucas/PARSE/pull/284) | 2026-05-06T11:35Z | Concept-tag filters/counts are speaker-scoped. | Updated README, user guide, architecture, developer guide, AGENTS. |
| [#286](https://github.com/ArdeleanLucas/PARSE/pull/286) | 2026-05-06T21:08Z | Frontend matches annotations by raw concept key instead of display id. | Updated AGENTS; existing identity-only docs remain consistent. |
| [#285](https://github.com/ArdeleanLucas/PARSE/pull/285) | 2026-05-06T21:10Z | Publishes concept display-id mismatch audit/TSVs. | Existing report preserved; this refresh records the broader documentation consequence. |
| [#287](https://github.com/ArdeleanLucas/PARSE/pull/287) | 2026-05-07T08:30Z | Annotate speaker notes persist. | Updated README/user guide/AGENTS. |
| [#288](https://github.com/ArdeleanLucas/PARSE/pull/288) | 2026-05-07T10:32Z | Mark Done persists pending inline edits before confirming. | Updated user guide and AGENTS. |
| [#289](https://github.com/ArdeleanLucas/PARSE/pull/289) | 2026-05-07T14:28Z | React exposes lexeme ORTH/IPA rerun controls. | Updated README/user/API docs and AGENTS. |
| [#290](https://github.com/ArdeleanLucas/PARSE/pull/290) | 2026-05-07T14:28Z | Backend adds synchronous `/api/lexeme/run_ortho` and `/api/lexeme/run_ipa`. | Updated API reference, user guide, developer guide, architecture, AGENTS. |
| [#293](https://github.com/ArdeleanLucas/PARSE/pull/293) | 2026-05-07T15:26Z | Confirmed lexeme reruns auto-persist into annotations. | Updated README/user guide/AGENTS. |
| [#291](https://github.com/ArdeleanLucas/PARSE/pull/291) | 2026-05-07T15:28Z | Adds survey-overlap backend/UI and import preview/commit support. | Updated API reference, user guide, architecture, developer guide, AGENTS. |
| [#292](https://github.com/ArdeleanLucas/PARSE/pull/292) | 2026-05-07T15:46Z | Exposes survey color directory controls in the right panel. | Updated README/user/API/dev/AGENTS survey-overlap wording. |
| [#295](https://github.com/ArdeleanLucas/PARSE/pull/295) | 2026-05-07T16:35Z | Fixes survey-overlap wire format and Current survey copy. | API docs now state direct sidecar payloads/no wrapper; user guide notes Current survey copy. |
| [#297](https://github.com/ArdeleanLucas/PARSE/pull/297) | 2026-05-07T16:48Z | Adds `POST /api/concepts/{conceptId}/duplicate`. | Updated API reference, README, user guide, developer guide, AGENTS. |
| [#294](https://github.com/ArdeleanLucas/PARSE/pull/294) | 2026-05-07T16:49Z | Annotate sidebar shows active-speaker elicited concepts. | Updated README/user guide/AGENTS. |
| [#296](https://github.com/ArdeleanLucas/PARSE/pull/296) | 2026-05-07T16:57Z | Frontend right-click duplicates a concept into A/B rows. | Updated README/user guide/AGENTS. |
| [#299](https://github.com/ArdeleanLucas/PARSE/pull/299) | 2026-05-07T17:30Z | HF ORTH suppresses configured prompts by default across full-file, concept-window, and lexeme rerun paths. | Updated user guide, architecture, AGENTS; dedicated prompt-suppression doc already exists. |
| [#298](https://github.com/ArdeleanLucas/PARSE/pull/298) | 2026-05-07T17:30Z | ORTH/IPA lexeme rerun dialog exposes pad selector. | Updated README/user/API/architecture/AGENTS. |
| [#300](https://github.com/ArdeleanLucas/PARSE/pull/300) | 2026-05-07T17:39Z | Publishes ORTH prompt suppression regression report and no-parrot test. | Linked from user guide; AGENTS now records prompt-suppression state. |
| [#301](https://github.com/ArdeleanLucas/PARSE/pull/301) | 2026-05-07T18:32Z | ORTH action-menu pad selector flows through frontend compute payloads. | Updated API compute-field docs, architecture, user guide, AGENTS. |
| [#302](https://github.com/ArdeleanLucas/PARSE/pull/302) | 2026-05-07T18:33Z | Backend threads compute pad through concept-window ORTH. | Updated API compute-field docs, architecture, user guide, AGENTS. |
| [#303](https://github.com/ArdeleanLucas/PARSE/pull/303) | 2026-05-07T19:42Z | Survey color coding reaches sidebar badge text and multi-survey chips. | Updated README/user guide/AGENTS survey color/multi-chip wording. |
| [#304](https://github.com/ArdeleanLucas/PARSE/pull/304) | 2026-05-07T19:59Z | Action-menu pad selector expands from ORTH-only to STT / ORTH / IPA in concept-window and edited-only bulk runs. | Updated README, user guide, API reference, architecture, AGENTS, and this report; retained the landed MC-353 plan doc on main. |
| [#305](https://github.com/ArdeleanLucas/PARSE/pull/305) | 2026-05-07T19:59Z | Adds `docs/models/README.md` plus the Razhan `whisper-base-sdh` model reference and links the high-level AI docs to per-model docs. | Rebased onto the landed model docs and added the Models index to README; this report records the docs lane as shipped. |

## Files refreshed

| File | Why |
|---|---|
| `AGENTS.md` | Updated current-state cutoff, replaced #264 pending state with shipped behavior, and added post-#265 clusters for lexeme reruns, prompt suppression, concept tags, source-item import hardening, survey overlap, and A/B concept duplication. |
| `README.md` | Reworked the landing page into plain-language feature copy while still pointing readers to deeper docs for technical details such as model references, automation, and API contracts. |
| `docs/user-guide.md` | Added user-facing workflows for lexeme ORTH/IPA reruns, pad choices for STT/ORTH/IPA scoped action-menu runs, Mark Done save semantics, speaker-scoped tags/sidebar, survey overlap, and A/B duplication. |
| `docs/api-reference.md` | Added `/api/survey-overlap`, `/api/lexeme/run_ortho`, `/api/lexeme/run_ipa`, `/api/concepts/{conceptId}/duplicate`, lexeme-rerun semantics, survey-overlap payload shape, and scoped STT/ORTH/IPA compute `pad`. |
| `docs/architecture.md` | Updated data model for `concept_tags`, `survey-overlap.json`, Compare-only concept merges, prompt-suppressed HF ORTH, and pad-stable scoped reruns. |
| `docs/developer-guide.md` | Added contributor-facing reminders for typed helpers and current route/data surfaces. |
| `docs/architecture/annotation-record-sidecars.md` | Changed `concept_tags` from planned companion wording to shipped implementation/status. |
| `docs/reports/2026-05-03-last-24h-published-pr-doc-refresh.md` | Added a supersession note because #264 merged after its cutoff. |
| `docs/reports/2026-05-07-post-265-merged-pr-doc-refresh.md` | New evidence-backed audit/sign-off report, expanded after freshness rebase to include #304/#305. |

## Open follow-ups at final freshness check

None. PRs #304 and #305 merged during drafting; this branch was rebased onto `origin/main@9036ae1`, and both PRs were added to the shipped-change matrix instead of left as pending.

## Handoff queue review

The isolated docs worktree contains only tracked historical `.hermes/handoffs/` files from `origin/main`. The canonical clone has many newer untracked handoff artifacts, but those are not tracked on main and were intentionally not staged into this docs-only PR. No tracked active handoff exactly matched this post-#265 docs-refresh scope, so no queue-file lifecycle move was made.

## Coordinator sign-off

- Merged-PR coverage: **40/40 reviewed** for PRs merged after PR #265.
- Shipped behavior: Active docs now reflect the shipped user/API/data-contract surfaces from PRs #264 and #266-#305.
- Pending behavior: no open PARSE PRs at the final freshness check.
- Historical integrity: The previous #265 report keeps its original cutoff and now carries a supersession note for #264.
