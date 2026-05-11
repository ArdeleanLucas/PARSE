# PARSE rolling 24-hour PR documentation refresh — 2026-05-10

## Audit window

- **Window:** `2026-05-09T23:36:02+02:00` → `2026-05-10T23:36:02+02:00` (`2026-05-09T21:36:02Z` → `2026-05-10T21:36:02Z`).
- **Repository:** `ArdeleanLucas/PARSE` via canonical worktree `/home/lucas/gh/worktrees/parse-coordinator-last24-doc-refresh`.
- **Original base SHA audited:** `0ba0246` (`docs(mcp): add generic agent tool skills (#354)`).
- **PR base after freshness rebase:** `bd9ef88` (includes post-cutoff PR #358, merged at `2026-05-10T21:47:10Z`).
- **Coverage:** **22/22 PRs with activity in the window reviewed**: 21 merged before the cutoff, plus PR #358 tracked as a post-cutoff merge. PR number #351 does not exist as a pull request.
- **Method:** GitHub PR activity query, `git log --since`, PR file/body inspection, active-doc search, code-truth checks for job dispatch, rerun handlers, active-job dwell, language fallback, ORTH word-tier rebuild, subprocess tee usage, and final freshness rebase after #358 merged.

## PR documentation-consequence matrix

| PR | Merge SHA / state | Shipped behavior reviewed | Documentation consequence |
|---:|---|---|---|
| [#336](https://github.com/ArdeleanLucas/PARSE/pull/336) | `fe6a17c` | Codified long-running endpoint job-tracking rule in `AGENTS.md`. | Verified active; this report treats it as the governing invariant for #338/#342. |
| [#337](https://github.com/ArdeleanLucas/PARSE/pull/337) | `b0a1a82` | Added compute dispatch/jobId invariant tests. | No prose API change; report records test-only enforcement behind #336. |
| [#338](https://github.com/ArdeleanLucas/PARSE/pull/338) | `0c79e82` | `POST /api/lexemes/rerun-by-tag` now defaults to `202 + jobId` and compute type `lexemes_rerun_by_tag`. | Refreshed API/architecture/user/developer docs to describe job-tracked default and deprecated `async=false`. |
| [#339](https://github.com/ArdeleanLucas/PARSE/pull/339) | `4e9cd3b` | Restored live lexeme-rerun child stdout/stderr while keeping crash-tail logs. | `docs/architecture/compute-subprocess-stdio.md` preserved the incident and now includes #344 consolidation. |
| [#340](https://github.com/ArdeleanLucas/PARSE/pull/340) | `386f80e` | Introduced shared `install_child_tee` and used it for compute subprocess/persistent worker entries. | Existing AGENTS/architecture contract verified; report records the reusable helper as current. |
| [#341](https://github.com/ArdeleanLucas/PARSE/pull/341) | `fe308a2` | React header subscribes to `/api/jobs/active` for all running compute jobs. | Refreshed API/user/developer docs for active-job header visibility. |
| [#342](https://github.com/ArdeleanLucas/PARSE/pull/342) | `d2ae2bb` | Single-lexeme ORTH/IPA reruns now default to tracked compute jobs `lexeme_rerun_ortho` / `lexeme_rerun_ipa`; `async=false` remains legacy. | Replaced stale “synchronous rerun” wording in API/user/developer/architecture docs and added compute aliases. |
| [#343](https://github.com/ArdeleanLucas/PARSE/pull/343) | `b002a58` | Added compute-subprocess stdio docs and queued the lexeme tee consolidation handoff. | Superseded by #344; this pass moved the handoff to `done/` and updated the architecture inventory. |
| [#344](https://github.com/ArdeleanLucas/PARSE/pull/344) | `85c0896` | Replaced local lexeme rerun tee with shared `install_child_tee`. | Marked `.hermes/handoffs/parse-back-end/2026-05-10-consolidate-subprocess-tee.md` done and updated stdio docs. |
| [#345](https://github.com/ArdeleanLucas/PARSE/pull/345) | `d77d5a3` | Tagged-only rerun results persist back into annotations. | API/user/architecture docs now state successful tagged rerun writes are persisted. |
| [#346](https://github.com/ArdeleanLucas/PARSE/pull/346) | `4c1294c` | Added terminal active-job snapshot/header-strip test coverage. | No separate prose beyond #347/#348/#349 behavior; report records coverage. |
| [#347](https://github.com/ArdeleanLucas/PARSE/pull/347) | `f619661` | `/api/jobs/active` retains recently terminal jobs for a dwell window. | API/developer docs now include `PARSE_ACTIVE_JOBS_TERMINAL_DWELL_SEC` and terminal snapshot semantics. |
| [#348](https://github.com/ArdeleanLucas/PARSE/pull/348) | `2072ea3` | Header strip auto-dismisses errored terminal snapshots. | User docs now describe complete/error/cancelled terminal chips and auto-dismiss. |
| [#349](https://github.com/ArdeleanLucas/PARSE/pull/349) | `cb4b3aa` | Cancelled terminal snapshots render as amber chips and auto-dismiss. | User/API wording includes cancelled terminal snapshots. |
| [#350](https://github.com/ArdeleanLucas/PARSE/pull/350) | `5b9f872` | ORTH partial reruns rebuild affected `tiers.ortho_words`. | API/user/architecture docs now state word-tier rebuild after ORTH partial/tagged reruns. |
| [#352](https://github.com/ArdeleanLucas/PARSE/pull/352) | `e23db5d` | Frontend parser normalizes `/api/jobs/active` progress from backend 0-100 to UI 0-1. | API docs now call out backend vs TypeScript progress conventions. |
| [#353](https://github.com/ArdeleanLucas/PARSE/pull/353) | `e21f793` | Active-jobs feed keeps polling across field-equal responses. | No new prose; report records polling behavior behind header reliability. |
| [#354](https://github.com/ArdeleanLucas/PARSE/pull/354) | `0ba0246` | Added generic portable MCP tool skills and refreshed MCP/API docs. | Verified active; this report leaves README plain and documents deeper technical catch-up only. |
| [#355](https://github.com/ArdeleanLucas/PARSE/pull/355) | `9965332` | IPA compute now uses payload language or `annotation.metadata.language_code` before auto-detect. | Refreshed user/getting-started/AI/architecture wording from STT/ORTH-only to STT/ORTH/IPA. |
| [#356](https://github.com/ArdeleanLucas/PARSE/pull/356) | `6e096e5` | Concept-window ORTH chooses the saved lexeme word from overlapping Tier-2 words by midpoint distance, overlap, confidence, then order. | User/architecture docs now describe the midpoint-based word pick after partial ORTH reruns. |
| [#357](https://github.com/ArdeleanLucas/PARSE/pull/357) | `4609327` | Tier-2 forced alignment now emits progress during concept-window ORTH, rebudgeting 70→90% before write/complete. | Existing `docs/plans/MC-363-concept-windows-orth-progress-stall.md` is current; report records no broader API change needed. |
| [#358](https://github.com/ArdeleanLucas/PARSE/pull/358) | `dca4929` post-cutoff merge | Model-doc evidence for `wav2vec2-xlsr-53-espeak-cv-ft` merged at `2026-05-10T21:47:10Z`, 11 minutes after the fixed audit cutoff, while this docs branch was being finalized. | Rebased this PR onto `bd9ef88` so #358's model docs are present in the base. This report records #358 as reviewed but does not claim its shipped model evidence came from this docs-refresh diff. |

## Post-cutoff follow-up state

- **2026-05-11 / MC-371-A:** Concept duplicate now mirrors inherited tag membership through both per-speaker annotation `concept_tags` and global `tags_store` tag `concepts` lists, with ParseUI refreshing the tag store after duplicate reload.

| PR | State at final freshness check | Documentation handling |
|---:|---|---|
| [#358](https://github.com/ArdeleanLucas/PARSE/pull/358) | Merged at `2026-05-10T21:47:10Z`, after the fixed rolling-window cutoff | Rebased onto `bd9ef88` so the shipped model docs are present in this PR's base. No extra model-doc changes were added here; this refresh only records the post-cutoff state. |

## Files refreshed in this pass

| File | Why |
|---|---|
| `.hermes/handoffs/parse-back-end/done/2026-05-10-consolidate-subprocess-tee.md` | Moved completed PR #344 follow-up out of the active backend queue and recorded completion. |
| `docs/architecture/compute-subprocess-stdio.md` | Replaced stale “dedupe queued” wording with #344 shared-helper truth and updated stderr-fence expectation. |
| `docs/api-reference.md` | Updated job-tracked single-lexeme reruns, tagged rerun persistence, compute aliases, active-job terminal dwell, and progress scale conventions. |
| `docs/architecture.md` | Updated tag-filtered rerun architecture, per-lexeme job tracking, STT/ORTH/IPA language fallback, tagged persistence, word-tier rebuild, and midpoint word selection. |
| `docs/user-guide.md` | Updated user-visible tagged-only/per-lexeme rerun behavior, header terminal chips, persisted rerun writes, ORTH word-tier rebuild, and IPA language fallback. |
| `docs/developer-guide.md` | Updated relevant knobs/endpoints for tracked reruns and active-job dwell. |
| `docs/ai-integration.md` | Updated language-resolution wording to include IPA. |
| `docs/getting-started.md` | Updated language-resolution wording to include IPA. |
| `docs/plans/concept-scoped-pipeline.md` | Updated the active scoped-pipeline note from ORTH-only language resolution to STT/ORTH/IPA where supported. |
| `docs/reports/2026-05-10-rolling-24h-pr-doc-refresh.md` | Added this audit matrix and sign-off artifact. |

## Code-truth checks used

- `python/app/http/tag_filtered_rerun_handlers.py` — default `build_post_lexemes_rerun_by_tag_response` path creates a job and returns `HTTPStatus.ACCEPTED` with `jobId`; `async=false` returns the legacy blocking payload with `jobId: null`.
- `python/app/http/lexeme_rerun_handlers.py` — single-lexeme reruns default to compute jobs and launch `lexeme_rerun_ipa` / `lexeme_rerun_ortho`; `async=false` is legacy sync.
- `python/server_routes/jobs.py` — `/api/jobs/active` includes running jobs plus terminal snapshots inside `PARSE_ACTIVE_JOBS_TERMINAL_DWELL_SEC`; statuses include complete/error/cancelled variants.
- `src/api/contracts/job-observability.ts` — backend 0-100 progress is normalized to a 0-1 UI fraction.
- `python/server_routes/annotate.py` — `_transcription_language_from_payload_or_annotation` is used by STT, ORTH, and IPA; `_align_partial_ortho_words` rebuilds affected word tier; `_pick_lexeme_word_for_concept` uses midpoint/overlap/confidence/order.
- `python/server_routes/lexeme_rerun.py` — lexeme rerun child now imports and calls `install_child_tee`.
- `search_files(pattern='sys\.stderr\s*=\s*open', path='python', file_glob='*.py')` returned zero matches in active code.

## Coordinator sign-off

- **Coverage:** 22/22 PRs with rolling-window activity reviewed: 21 merged before the fixed cutoff and PR #358 merged post-cutoff while drafting.
- **Docs status:** active docs are refreshed for shipped behavior; PR #358's model evidence is present from the rebased `origin/main` base, not from this docs-refresh diff.
- **Queue status:** PR #344 backend follow-up handoff moved to `done/`; no active tracked handoff now points at the completed subprocess-tee consolidation task.
