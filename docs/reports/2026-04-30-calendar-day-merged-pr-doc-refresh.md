# PARSE calendar-day merged PR documentation refresh — 2026-04-30

## TL;DR

- Audit window: local calendar day **2026-04-30** (`2026-04-30T00:00:00+02:00` through `2026-05-01T00:00:00+02:00`; UTC window `2026-04-29T22:00:00Z` through `2026-04-30T22:00:00Z`).
- Grounded repo: `/home/lucas/gh/tarahassistant/PARSE-rebuild`, remote `git@github.com:ArdeleanLucas/PARSE.git`, docs worktree `/home/lucas/gh/worktrees/PARSE/docs-2026-04-30-merged-pr-refresh`, `origin/main` at `8a79e80` when this docs branch was cut, `eb03fa4` after rebase over PRs #212/#213, `713a031` after rebase over PR #215, `0b58a1e` after rebase over PR #216, and `e031895` after rebase over PR #217.
- Merged PRs in local-day window: **18** PRs (#199 through #213 plus #215, #216, and #217; PR #214 is this open docs PR and is not counted as shipped; PR #200 is included because it merged at local `2026-04-30T00:01:58+02:00`).
- Rolling 21-hour cross-check at `2026-04-30T23:56:21+02:00` (`2026-04-30T00:56:21Z..2026-04-30T21:56:21Z`) covers **15/15** merged PRs: #202, #203, #204, #205, #206, #207, #208, #209, #210, #211, #212, #213, #215, #216, and #217. The report retains #199-#201 as local-day/near-midnight context, while PR #214 remains open and is not documented as shipped.
- This pass updates active docs for Audition `commentsCsv` row-index note import, bracket/bare-row cue parsing, trace-field round trips, save-time concept-id enforcement, identity-only frontend concept matching, strict Annotate status badges, BND header-chip progress, MCP/default tool count drift after `csv_only_reimport` / `revert_csv_reimport` landed, full-mode IPA concept-window fallback, Razhan/DOLMA `fa` language-token citation guidance, Razhan SDH ORTH default decoder prime/model-init logging, post-compute canonical disk reload after scoped pipeline refresh, and run-mode-aware IPA preview gating in the transcription run modal.
- Freshness re-audit: PR #212, PR #213, PR #215, PR #216, and PR #217 merged during drafting; this pass rebased over `origin/main` and now documents them as shipped. The only open PARSE PR at the latest freshness check was this docs PR (#214).

## Grounding evidence

```text
repo: /home/lucas/gh/tarahassistant/PARSE-rebuild
origin: git@github.com:ArdeleanLucas/PARSE.git
origin/main at branch cut: 8a79e80; after freshness rebases: eb03fa4, then 713a031, then 0b58a1e, then e031895
current docs branch: docs/2026-04-30-merged-pr-refresh
local audit window: 2026-04-30T00:00:00+02:00..2026-05-01T00:00:00+02:00
utc audit window: 2026-04-29T22:00:00Z..2026-04-30T22:00:00Z
```

Tool-grounded checks used:

- `date -Is` / UTC conversion for the local calendar-day window.
- `git fetch origin --quiet --prune` before branch/status decisions.
- `gh pr list --repo ArdeleanLucas/PARSE --state merged --search 'merged:>=2026-04-29' --json ... --limit 100`, filtered by `mergedAt` within the local-day UTC bounds.
- `gh pr view <199..213,215,216,217> --repo ArdeleanLucas/PARSE --json body,files,commits,mergeCommit,...` for file-level doc implications.
- `gh pr list --repo ArdeleanLucas/PARSE --state open ...` before and after rebases; final state had only this docs PR (#214) open.
- Rolling 21-hour verification via `gh pr list --repo ArdeleanLucas/PARSE --state merged --json number,title,mergedAt,url --limit 100`, filtered to `2026-04-30T00:56:21Z..2026-04-30T21:56:21Z`, produced #202-#213 plus #215/#216/#217 exactly.
- Code count check at that audit cutoff: `REGISTRY=57`, `ParseChatTools._tool_specs=57`, `DEFAULT_MCP_TOOL_NAMES=57`, `LEGACY_CURATED_MCP_TOOL_NAMES=38`, workflow macros `3`, default adapter total `61`, legacy adapter total `42`. Supersession note: PR #257 later raised current counts to `REGISTRY=58`, `ParseChatTools=58`, `DEFAULT_MCP_TOOL_NAMES=58`, default/all adapter total `62`, while legacy curated remains `38` parse-task tools / `42` adapter tools.

## Merged PRs covered by this refresh

| PR | Merged UTC | Merge | Area | Documentation consequence |
|---:|---|---|---|---|
| [#200](https://github.com/ArdeleanLucas/PARSE/pull/200) | `2026-04-29T22:01:58Z` | `efff72b` | Audition integer concept ids + trace metadata | Already folded into the late #199 docs refresh, but remains in this local-day audit because it merged at `00:01:58+02:00`; current docs keep integer-id resolution and `import_index` / `audition_prefix` as shipped. |
| [#199](https://github.com/ArdeleanLucas/PARSE/pull/199) | `2026-04-29T22:33:30Z` | `4fa0e21` | 2026-04-29 docs refresh | Kept as historical basis; this pass amends its now-stale “comments-file row-index joining pending” cutoff language after PR #201 shipped. |
| [#201](https://github.com/ArdeleanLucas/PARSE/pull/201) | `2026-04-29T22:36:59Z` | `f9e386f` | Audition comments CSV row-index notes | User/API/AGENTS docs now treat multipart `commentsCsv` companion import as shipped: row-index pairing writes `import_note`, `import_raw`, `import_index`, `audition_prefix`, and `updated_at` into lexeme notes. |
| [#202](https://github.com/ArdeleanLucas/PARSE/pull/202) | `2026-04-30T07:17:43Z` | `d8d0d75` | Canonical clone/worktree discipline | Preserved in grounding language: canonical root stays on `main`; PR work happens in isolated worktrees from `origin/main`. |
| [#203](https://github.com/ArdeleanLucas/PARSE/pull/203) | `2026-04-30T10:14:20Z` | `898a724` | Audition parser no-row-left-behind | User/API/AGENTS docs now mention square-bracket prefixes and bare/malformed rows importing with opaque synthetic `row_<import_index>` prefixes instead of being skipped. |
| [#204](https://github.com/ArdeleanLucas/PARSE/pull/204) | `2026-04-30T10:26:34Z` | `65ab0f1` | Trace metadata round trip | AGENTS/runtime docs now state annotation read/save normalization preserves allowed additive trace fields such as `concept_id`, `import_index`, `audition_prefix`, `source`, and `conceptId`. |
| [#205](https://github.com/ArdeleanLucas/PARSE/pull/205) | `2026-04-30T14:04:32Z` | `e2ab6ec` | Deterministic concept-id ↔ interval pairing | README/user/AGENTS docs now call out identity-only concept lookup rather than concept-name substring matching. |
| [#206](https://github.com/ArdeleanLucas/PARSE/pull/206) | `2026-04-30T14:27:41Z` | `47eacad` | MCP csv-only reimport + revert | MCP docs and tool-count claims now use `57/57/61` default and `38/42` legacy counts; docs list `csv_only_reimport` and `revert_csv_reimport` as dry-run/backup-gated write-capable tools. |
| [#207](https://github.com/ArdeleanLucas/PARSE/pull/207) | `2026-04-30T14:47:03Z` | `f622433` | Save-time `concept_id` enforcement gate | AGENTS/user/runtime docs now state non-empty concept-tier labels are normalized to integer `concept_id` values on save, with unknown labels allocating new integer concept rows. |
| [#208](https://github.com/ArdeleanLucas/PARSE/pull/208) | `2026-04-30T15:12:45Z` | `b7bf6f8` | Drop text/regex frontend matcher fallback | Docs now state legacy concept intervals without `concept_id` remain visibly unannotated until reimported or saved; interval text is display metadata only. |
| [#209](https://github.com/ArdeleanLucas/PARSE/pull/209) | `2026-04-30T16:12:52Z` | `d44c234` | Split Annotate badges | README/user/AGENTS docs now distinguish `Annotated` from `Complete`. |
| [#210](https://github.com/ArdeleanLucas/PARSE/pull/210) | `2026-04-30T16:22:00Z` | `cd3d8c6` | BND progress header chip | AGENTS/docs now state BND progress surfaces in the global header chip rather than as duplicate drawer progress text. |
| [#211](https://github.com/ArdeleanLucas/PARSE/pull/211) | `2026-04-30T17:29:05Z` | `8a79e80` | Badge ignores `ortho_words` tier | README/user/AGENTS docs now state `Complete` requires strict `ortho` overlap; auto-imported `ortho_words` remains useful for BND/word display but does not count as reviewed orthography. |
| [#212](https://github.com/ArdeleanLucas/PARSE/pull/212) | `2026-04-30T19:22:52Z` | `cf1fec0` | Full-mode IPA fallback to concept windows | Report/AGENTS docs now treat server-side IPA full-mode auto-routing to concept windows as shipped when ORTH/`ortho_words` are empty but concept intervals exist. |
| [#213](https://github.com/ArdeleanLucas/PARSE/pull/213) | `2026-04-30T19:24:39Z` | `eb03fa4` | Razhan SDH language-token normalization + citations | README/getting-started/AI/user/research docs now state provider-side Whisper decoding maps `sd`/`sdh` to `fa`, while PARSE metadata remains `sdh`, and cite the Hameed et al. 2025 ASR-ME PDF/DOI with Razhan model references. |
| [#215](https://github.com/ArdeleanLucas/PARSE/pull/215) | `2026-04-30T19:58:18Z` | `713a031` | Pipeline compute completion reload | README/user/API/architecture/AGENTS docs now state scoped concept-row refresh is advisory and `reloadSpeakerAnnotation`/disk reload remains canonical after IPA, ORTH, STT, or BND compute completion. This covers the Saha01 stale-UI failure where 497 disk-written IPA intervals existed but the UI still showed “No IPA intervals yet.” |
| [#216](https://github.com/ArdeleanLucas/PARSE/pull/216) | `2026-04-30T20:22:41Z` | `0b58a1e` | Razhan SDH default ORTH prompt + model-init logging | README/getting-started/AI/user/config/AGENTS docs now state omitted `ortho.initial_prompt` gets the built-in Southern Kurdish Arabic-script decoder prime, explicit empty string opts out, and faster-whisper emits `[STT]`/`[ORTH] loaded model: ... language=... initial_prompt=...` after successful model init. |
| [#217](https://github.com/ArdeleanLucas/PARSE/pull/217) | `2026-04-30T21:53:33Z` | `e031895` | Run modal IPA concept-window preview gating | README/user/API/architecture/AGENTS docs now state the transcription run grid carries `run_mode` into cell computation: `concept-windows` / `edited-only` IPA can show runnable despite stale full-mode `ipa.can_run=false` when ORTH/concept-tier presence is observable, while full-mode IPA-without-ORTH and pure-empty concept-window speakers remain blocked. |


## Rolling 21-hour PR coverage cross-check

Strict rolling window checked at `2026-04-30T23:56:21+02:00`: `2026-04-30T00:56:21Z..2026-04-30T21:56:21Z`.

| PR | Merged UTC | Title | URL |
|---:|---|---|---|
| #202 | `2026-04-30T07:17:43Z` | docs(agents): canonical clone stays on main; explicit worktree-only rule + post-merge checklist | https://github.com/ArdeleanLucas/PARSE/pull/202 |
| #203 | `2026-04-30T10:14:20Z` | feat(onboard): parser accepts [N.M] brackets and bare-phrase rows | https://github.com/ArdeleanLucas/PARSE/pull/203 |
| #204 | `2026-04-30T10:26:34Z` | fix(annotate): preserve interval trace metadata across save round-trip | https://github.com/ArdeleanLucas/PARSE/pull/204 |
| #205 | `2026-04-30T14:04:32Z` | fix(annotate): deterministic concept-id ↔ interval pairing | https://github.com/ArdeleanLucas/PARSE/pull/205 |
| #206 | `2026-04-30T14:27:41Z` | feat(mcp): csv_only_reimport + revert_csv_reimport tools with backup | https://github.com/ArdeleanLucas/PARSE/pull/206 |
| #207 | `2026-04-30T14:47:03Z` | feat(annotate): save-time concept_id enforcement gate | https://github.com/ArdeleanLucas/PARSE/pull/207 |
| #208 | `2026-04-30T15:12:45Z` | fix(annotate): id-only concept matcher; drop regex text fallback | https://github.com/ArdeleanLucas/PARSE/pull/208 |
| #209 | `2026-04-30T16:12:52Z` | fix(annotate): split badge into Annotated and Complete | https://github.com/ArdeleanLucas/PARSE/pull/209 |
| #210 | `2026-04-30T16:22:00Z` | fix(annotate): unify BND progress in header chip | https://github.com/ArdeleanLucas/PARSE/pull/210 |
| #211 | `2026-04-30T17:29:05Z` | fix(annotate): badge ignores auto-imported ortho_words; check ortho tier strictly | https://github.com/ArdeleanLucas/PARSE/pull/211 |
| #212 | `2026-04-30T19:22:52Z` | fix(ipa): auto-route full-mode to concept-windows when ortho is empty | https://github.com/ArdeleanLucas/PARSE/pull/212 |
| #213 | `2026-04-30T19:24:39Z` | fix(ortho): map sdh/sd → fa for Razhan Whisper provider; cite DOLMA models | https://github.com/ArdeleanLucas/PARSE/pull/213 |
| #215 | `2026-04-30T19:58:18Z` | fix(pipeline): always reload speaker after compute completes; scoped refresh no longer gates disk reload | https://github.com/ArdeleanLucas/PARSE/pull/215 |
| #216 | `2026-04-30T20:22:41Z` | fix(ortho): default Razhan SDH initial_prompt + model-init logging | https://github.com/ArdeleanLucas/PARSE/pull/216 |
| #217 | `2026-04-30T21:53:33Z` | fix(run-modal): IPA cell is runnable in concept-windows mode when concept-tier is present | https://github.com/ArdeleanLucas/PARSE/pull/217 |

Rolling 21-hour coverage result: **15/15 PRs cited explicitly**.

## Follow-ups not documented as shipped

| Scope | State at final freshness check | Why it matters |
|---|---|---|
| Open PARSE PRs | #214 only | PR #212, PR #213, PR #215, PR #216, and PR #217 merged during drafting and are documented as shipped after rebase; #214 is this documentation PR and remains open for review. |

## Files refreshed by this documentation pass

| File | Reason |
|---|---|
| `AGENTS.md` | Updated current-state bullets for Audition comments/import parsing, trace round trips, save-time concept-id enforcement, identity-only concept lookup, strict Annotate badges, BND header-chip progress, canonical post-compute disk reload, run-mode-aware IPA preview gating, Razhan ORTH prompt/log defaults, and MCP 57/61/38/42 counts. |
| `README.md` | Refreshed first-impression Annotate, Audition CSV, MCP write-tool language, post-compute disk reload, run-modal IPA preview gating, and Razhan/DOLMA model citation/prompt/log language after PRs #201/#203/#205-#213/#215/#216/#217. |
| `docs/user-guide.md` | Added user-facing identity-only concept lookup, strict `Annotated`/`Complete` badge semantics, `commentsCsv`/bare-row Audition import behavior, post-compute disk reload semantics, run-mode-aware IPA preview gating, Razhan model paper citation, and Razhan ORTH default prompt/model-init logging. |
| `docs/api-reference.md` | Updated onboarding endpoint notes for `commentsCsv`; added `csv_only_reimport` / `revert_csv_reimport` rows to the MCP write/import table and dry-run rules; clarified `affected_concepts` is a refresh hint rather than a reload gate. |
| `docs/mcp-guide.md` | Replaced stale “newest write-capable tool is `clef_clear_data`” language with current CLEF + CSV reimport/revert tool set. |
| `docs/getting-started-external-agents.md` | Updated default external-agent tool summary to include CSV reimport/revert workflows. |
| `docs/mcp_agent_roadmap.md` | Fixed stale top-level counts from 54/58/40 to 57/61/42. |
| `docs/ai-integration.md` / `docs/getting-started.md` / `docs/research-context.md` | Added the Hameed et al. 2025 ASR-ME paper PDF/DOI alongside Razhan model references; corrected provider-side ORTH language-token guidance to `fa`; documented the built-in ORTH decoder prime and model-init log line. |
| `docs/plans/MC-334-razhan-sdh-language-normalize-and-cite.md` | Added the explicit ASR-ME paper PDF/DOI to the PR #213 plan and PR #216 follow-up note so Razhan citation/prompt guidance is preserved in the implementation record. |
| `config/ai_config.example.json` | Added the ASR-ME paper PDF/DOI to the ORTH model comment and preserved the PR #216 default `initial_prompt` so copied configs keep the citation and decoder prime with the Razhan model. |
| `docs/mcp-schema.md` | Added CSV reimport/revert to the current default MCP write-capable surface summary. |
| `docs/plans/deferred-validation-backlog.md` | Refreshed automated validation baseline with PR #203/#206/#207/#216 backend suites and PR #211/#215/#217 frontend/typecheck/build counts. |
| `docs/architecture.md` / `docs/plans/concept-scoped-pipeline.md` | Clarified that concept-scoped `affected_concepts` enables scoped repaint but does not replace the canonical speaker-annotation reload after compute completion, and that IPA preview cells are mode-aware for concept-window / edited-only runs. |
| `docs/reports/2026-04-29-calendar-day-merged-pr-doc-refresh.md` | Marked its comments-file row-index follow-up note as historical cutoff evidence superseded by PR #201. |
| `.hermes/handoffs/parse-back-end/2026-04-26-mcp-adapter-architecture-audit.md` | Added a supersession note for historical MCP count figures so the active handoff no longer presents the 2026-04-26 50/54-tool surface as current. |
| `docs/reports/2026-04-30-calendar-day-merged-pr-doc-refresh.md` | Added this audit report. |

## Coordinator sign-off

- Calendar-day merged PR coverage: **18/18 local-day merged PRs accounted for** (#199-#213 plus #215/#216/#217, with #200 included because local merge time was after midnight and #214 excluded because it is this open docs PR).
- Rolling 21-hour merged PR coverage: **15/15 rolling-window PRs explicitly cited** (#202-#213 plus #215/#216/#217).
- Open PRs kept pending, not shipped: **yes** — final freshness check found only this docs PR (#214) open; PR #212/#213/#215/#216/#217 are documented as shipped only after merge/rebase evidence.
- Contract fidelity: **current docs treat `commentsCsv`, bracket/bare-row import, trace-field preservation, save-time concept-id enforcement, identity-only concept matching, strict `Annotated`/`Complete` badges, BND header-chip progress, full-mode IPA concept-window fallback, post-compute canonical disk reload, run-mode-aware IPA preview gating, Razhan provider-side `fa` token normalization, Razhan ORTH default prompt/model-init logging, ASR-ME paper citation, and `csv_only_reimport` / `revert_csv_reimport` as shipped behavior only where merged PR evidence supports it**.
- Validation completed before push: `git diff --check` passed; `python3 -m json.tool config/ai_config.example.json` passed; changed Markdown relative-link scan checked **64** relative links across changed Markdown files, found **0** missing links, and ignored only the known placeholder `docs/pr-assets/foo.png`.
