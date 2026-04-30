# PARSE calendar-day merged PR documentation refresh — 2026-04-29

## TL;DR

- Audit window: local calendar day **2026-04-29** (`2026-04-29T00:00:00+02:00` through `2026-04-30T00:00:00+02:00`; UTC window `2026-04-28T22:00:00Z` through `2026-04-29T22:00:00Z`).
- Grounded repo: `/home/lucas/gh/tarahassistant/PARSE-rebuild`, remote `git@github.com:ArdeleanLucas/PARSE.git`, `origin/main` at `494a575` when this docs branch was first cut, `bdbf886` after rebase over PR #198, and `efff72b` after rebase over PR #200.
- Merged PRs in original local-day window: **19** PRs (#180 through #198, with #183 merged into the #180 feature branch and shipped through #180). Explicit post-cutoff inclusion by request: **PR #200** (`2026-04-29T22:01:58Z`, local `2026-04-30T00:01:58+02:00`).
- This pass updates active docs for shipped concept-scoped pipeline modes, Annotate save/retime and UX changes, ORTH/STT language safety, MCP/package contract details, Audition CSV onboarding, current validation counts, worktree grounding, and the prior same-day report's now-stale PR #180 pending note.
- Open follow-up at that report's final freshness check: **comments-file row-index joining only**. This is now superseded by PR #201, which merged just after the 2026-04-29 report and shipped row-index companion comments import; see `docs/reports/2026-04-30-calendar-day-merged-pr-doc-refresh.md`.

## Grounding evidence

```text
repo: /home/lucas/gh/tarahassistant/PARSE-rebuild
origin: git@github.com:ArdeleanLucas/PARSE.git
origin/main at branch cut: 494a575; rebased over bdbf886 after PR #198 merged; rebased over efff72b after PR #200 merged
current branch for this doc refresh: docs/calendar-day-2026-04-29-merged-pr-refresh
local audit window: 2026-04-29T00:00:00+02:00..2026-04-30T00:00:00+02:00
utc audit window: 2026-04-28T22:00:00Z..2026-04-29T22:00:00Z
```

Tool-grounded checks used:

- `date -Is` / Python timezone conversion for the local calendar-day window.
- `git fetch origin --quiet --prune` before branch/status decisions.
- `gh pr list --repo ArdeleanLucas/PARSE --state merged --json ... --limit 100`, filtered by mergedAt within the local-day UTC bounds.
- `gh pr view <180..198,200> --repo ArdeleanLucas/PARSE --json body,files,commits,mergeCommit,...` for file-level doc implications.
- `gh pr list --repo ArdeleanLucas/PARSE --state open ...`, `gh pr view 198 ...`, and `gh pr view 200 ...` before/after rebase to avoid stale open-vs-merged claims.
- Code count check: `ParseChatTools=55`, `DEFAULT_MCP_TOOL_NAMES=55`, `LEGACY_CURATED_MCP_TOOL_NAMES=36`, workflow macros `3`, default adapter total `59`.

## Merged PRs covered by this refresh

| PR | Merged | Base | Area | Documentation consequence |
|---:|---|---|---|---|
| [#180](https://github.com/ArdeleanLucas/PARSE/pull/180) | `ff965e9` | `main` | Save Annotation creates missing IPA lexeme intervals | Annotate docs/guardrails now treat missing-IPA creation as shipped when concept span matches and typed IPA has no overlapping IPA interval. |
| [#181](https://github.com/ArdeleanLucas/PARSE/pull/181) | `32f5126` | `main` | Earlier last-24h docs refresh | Keep its report as historical, but update stale “PR #180 pending” language now that #180 merged. |
| [#182](https://github.com/ArdeleanLucas/PARSE/pull/182) | `680a97f` | `main` | CLEF `grok_llm`, Wiktionary translation tables, Settings tab | Active CLEF docs remain aligned: `grok_llm` is final LLM fallback after citable/local providers; Wiktionary reads translation tables; Settings tab/delete confirmation are shipped. |
| [#183](https://github.com/ArdeleanLucas/PARSE/pull/183) | `a37dd61` | `fix/lexeme-save-tier-count-and-bnd-refresh` | BND visual refresh code trace + lane virtualization fix | Treat as branch-level evidence folded into #180/#188 save-retime work; no separate main-only feature claim. |
| [#184](https://github.com/ArdeleanLucas/PARSE/pull/184) | `37f9fd7` | `main` | Waveform quick-retime selection | User/README docs now mention drag-select waveform quick retime and existing `saveLexemeAnnotation` commit path. |
| [#185](https://github.com/ArdeleanLucas/PARSE/pull/185) | `607db34` | `main` | Playhead chip + quick-retime cancel | Annotate docs now use the two-decimal waveform playhead chip and cancel/Escape transient selection behavior. |
| [#186](https://github.com/ArdeleanLucas/PARSE/pull/186) | `adc85cf` | `main` | Manual volume control | Annotate docs now mention the transport-bar volume slider and WaveSurfer volume binding. |
| [#187](https://github.com/ArdeleanLucas/PARSE/pull/187) | `f147df0` | `main` | Default volume 1.0 | Docs now state the current default is 100%, not 0.8. |
| [#188](https://github.com/ArdeleanLucas/PARSE/pull/188) | `862b442` | `main` | Saved lexeme bounds refresh | Save/retime docs now state local timestamp inputs and visual BND state refresh from saved bounds. |
| [#189](https://github.com/ArdeleanLucas/PARSE/pull/189) | `f473d1c` | `main` | Offset apply reports `shiftedConcepts` | MCP/package/API docs now mention concept counts alongside legacy interval counts. |
| [#190](https://github.com/ArdeleanLucas/PARSE/pull/190) | `71708ba` | `main` | Concept-scoped pipeline contract | Plan/worktree docs now treat the contract as shipped historical coordination rather than an active unmerged lane. |
| [#191](https://github.com/ArdeleanLucas/PARSE/pull/191) | `397d6fc` | `main` | Frontend run modes | User/API/external-agent docs now mention `full`, `concept-windows`, and `edited-only` run modes, edited-concepts preview, scoped step gating, and selective post-run refresh. |
| [#192](https://github.com/ArdeleanLucas/PARSE/pull/192) | `3f1c28e` | `main` | Backend/MCP concept-scoped modes | API/MCP/parse-mcp docs now treat `run_mode`, `concept_ids`, no-op `edited-only`, and `affected_concepts` as shipped backend/MCP contract. |
| [#193](https://github.com/ArdeleanLucas/PARSE/pull/193) | `6ee5140` | `main` | Response-contract amendment | Plan/API docs preserve the corrected `affected_concepts` response contract. |
| [#194](https://github.com/ArdeleanLucas/PARSE/pull/194) | `ff9b4f7` | `main` | Annotate notes, label, keyboard navigation, drawer polish | User docs now mention per-lexeme notes, generic `Orthographic` label, visible-list arrow navigation, and removal of compute drawer tag filters. |
| [#195](https://github.com/ArdeleanLucas/PARSE/pull/195) | `96ec29b` | `main` | Save Annotation unwraps server-normalized state | Docs now state Save Annotation/quick-retime success copy and visual refresh are based on the full server annotation response and distinct changed tier names. |
| [#196](https://github.com/ArdeleanLucas/PARSE/pull/196) | `d7b7833` | `main` | ORTH/STT language fallback + no English prompt seeding | AI/setup/API docs now state concept-window short clips avoid English concept/gloss `initial_prompt`, and language resolves from payload then annotation metadata before auto-detect. |
| [#197](https://github.com/ArdeleanLucas/PARSE/pull/197) | `494a575` | `main` | Remove Annotate drawer concept filters + `npm run typecheck` alias | User/AGENTS docs now say ConceptSidebar remains the canonical concept filter and current validation includes `npm run typecheck` alias plus PR #197's 82-file/485-test frontend baseline. |
| [#198](https://github.com/ArdeleanLucas/PARSE/pull/198) | `bdbf886` | `main` | Audition CSV creates lexeme intervals on onboarding | Runtime/API/user docs now treat Audition marker CSV detection and CSV-order `concept` + `ortho_words` interval seeding as shipped; PR #200 later hardens concept-id resolution and trace metadata. |
| [#200](https://github.com/ArdeleanLucas/PARSE/pull/200) | `efff72b` | `main` | Audition CSV integer concept ids + import traceability | Runtime/API/user/AGENTS docs now treat case-insensitive `concept_en` reuse, stable integer-id allocation, `import_index`, `audition_prefix`, preserved `source_audio_duration_sec`, and detection-failure logging as shipped; comments-file row-index joining remains the only Audition follow-up called out here. |

## Follow-ups not documented as shipped

| Scope | State at audit | Why it matters |
|---|---|---|
| Audition comments-file row-index joining | queued follow-up, no PR merged at 2026-04-29 cutoff; superseded by PR #201 on 2026-04-30 local day | PR #200 shipped integer-only concept-id resolution plus `import_index` / `audition_prefix` traceability for Audition marker imports; PR #201 later shipped companion comments CSV row-index joining, so this row is historical cutoff evidence rather than current pending work. |

## Files refreshed by this documentation pass

| File | Reason |
|---|---|
| `AGENTS.md` | Updated current-state bullets, safe-work priorities, MCP/offset/run-mode notes, Audition import status, and frontend/backend validation baselines after #180-#198 plus explicit PR #200 refresh. |
| `README.md` | Refreshed first-impression Annotate and MCP workflow language for quick retime, volume, notes, server-normalized save, and concept-scoped reruns. |
| `docs/user-guide.md` | Added current Annotate UX and concept-scoped pipeline behavior, plus language-safety notes for STT/ORTH concept windows. |
| `docs/api-reference.md` / `docs/user-guide.md` / `README.md` | Cross-linked the shipped Audition CSV import contract from PRs #198/#200, including integer concept-id resolution and `import_index` / `audition_prefix` trace metadata while keeping comments-file row joining pending. |
| `docs/api-reference.md` | Added `run_mode` / `concept_ids` / `affected_concepts` compute contract, shifted-concept offset response notes, and updated MCP default wording. |
| `docs/ai-integration.md` | Updated ORTH safety behavior and workflow macro descriptions. |
| `docs/getting-started.md` | Added ORTH language fallback and concept-window prompt-safety notes. |
| `docs/getting-started-external-agents.md` | Updated examples for scoped pipeline reruns and clarified the shipped default MCP surface. |
| `docs/mcp-guide.md` | Removed stale curated-default wording; default MCP surface is the shipped full safe 59-tool surface. |
| `docs/architecture.md` | Added concept-scoped pipeline architecture and updated MCP surface semantics. |
| `docs/mcp_agent_roadmap.md` | Recorded shipped workflow macro support for concept-scoped pipeline parameters. |
| `python/packages/parse_mcp/README.md` | Added package-facing notes for `run_full_annotation_pipeline` scoped inputs and offset concept counts. |
| `docs/plans/concept-scoped-pipeline.md` | Converted active-lane coordination language into shipped contract/status language. |
| `docs/plans/worktree-setup.md` | Corrected canonical checkout/worktree paths and marked concept-scoped lanes as shipped. |
| `docs/plans/deferred-validation-backlog.md` | Refreshed current automated baseline after PR #197/#196/#198 and PR #200's Audition revalidation. |
| `docs/reports/2026-04-29-parse-last-24h-change-log.md` | Clarified historical #180-pending statements now superseded by the calendar-day pass. |
| `docs/reports/2026-04-29-calendar-day-merged-pr-doc-refresh.md` | Added this audit report. |

## Coordinator sign-off

- Calendar-day merged PR coverage after rebase: **19/19 original-window merged PRs accounted for**, plus **1/1 explicit post-cutoff PR #200 update accounted for**.
- Open PRs kept pending, not shipped: **yes at the 2026-04-29 cutoff** — Audition comments-file row-index joining was pending then, while PR #200's concept-id/traceability hardening was documented as shipped. PR #201 later shipped the comments import path and is covered by the 2026-04-30 report.
- Contract fidelity: **current docs treat `run_mode`, `concept_ids`, `affected_concepts`, `shiftedConcepts`, server-normalized Save Annotation state, and Audition CSV interval seeding/concept-id/trace metadata as shipped behavior only where merged PR evidence supports it**.
- Validation completed before push: `git diff --check` passed; changed Markdown relative-link scan checked **56** relative links across **16** changed Markdown files, found **0** missing links, and ignored only the known placeholder `docs/pr-assets/foo.png`.
