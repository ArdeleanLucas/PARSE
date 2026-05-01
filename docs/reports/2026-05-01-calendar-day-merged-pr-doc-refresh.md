# PARSE calendar-day merged PR documentation refresh — 2026-05-01

## TL;DR

- Audit window: local calendar day **2026-05-01** from `2026-05-01T00:00:00+02:00` through the drafting/freshness check; UTC lower bound `2026-04-30T22:00:00Z`.
- Grounded repo: `/home/lucas/gh/tarahassistant/PARSE-rebuild`, remote `git@github.com:ArdeleanLucas/PARSE.git`, docs worktree `/home/lucas/gh/worktrees/parse-docs-2026-05-01-calendar-day`, branch `docs/2026-05-01-calendar-day-refresh`, branch-cut `origin/main` `3c7823b62445`.
- Merged PRs in local-day window reviewed: **13/13** — #214 plus #218 through #229.
- Open PARSE PRs at the final freshness check: **#231** (`fix(annotate): navigate concepts with arrow keys from fields`) is open/mergeable but review-blocked and is **not** documented as shipped. Closed-unmerged PR #230 is also not documented as shipped.
- This pass updates active docs for the 2026-05-01 HF ORTH/default-runtime wave, batch/backend cancellation, direct ORTH editor prefill, cooperative ORTH partial-cancel semantics, full-pipeline GPU lifecycle cleanup, stale speaker-lock cleanup, explicit ORTH provider threading, and validation-count drift.

## Grounding evidence

```text
repo: /home/lucas/gh/tarahassistant/PARSE-rebuild
origin: git@github.com:ArdeleanLucas/PARSE.git
worktree: /home/lucas/gh/worktrees/parse-docs-2026-05-01-calendar-day
branch: docs/2026-05-01-calendar-day-refresh
origin/main at branch cut: 3c7823b62445
local audit window lower bound: 2026-05-01T00:00:00+02:00
utc audit window lower bound: 2026-04-30T22:00:00Z
```

Tool-grounded checks used:

- `date -Is` / Python timezone conversion for the local calendar-day window.
- `git fetch origin --quiet --prune` before branch/status decisions.
- `gh pr list --repo ArdeleanLucas/PARSE --state merged --limit 100 --json number,title,mergedAt,url,author,headRefName,baseRefName,mergeCommit`, filtered by local `mergedAt` date.
- `gh pr view <214,218-229> --repo ArdeleanLucas/PARSE --json body,files,commits,mergeCommit,statusCheckRollup,...` for file-level implications.
- `gh pr diff <N> --repo ArdeleanLucas/PARSE --name-only` for changed-file confirmation.
- Code truth checks against `config/ai_config.example.json`, `python/ai/providers/hf_whisper.py`, `python/ai/providers/shared.py`, `python/server_routes/jobs.py`, `python/server_routes/locks.py`, `python/server_routes/annotate.py`, and `src/api/contracts/chat-and-generic-compute.ts`.

## Merged PRs covered by this refresh

| PR | Merged local | Merge | Area | Documentation consequence |
|---:|---|---|---|---|
| [#214](https://github.com/ArdeleanLucas/PARSE/pull/214) | `2026-05-01T00:48:29+02:00` | `7bdd439` | 2026-04-30 docs refresh | Counted because it merged during the local day. It provides the prior documentation baseline for PRs #199-#217; no new runtime behavior shipped in #214 itself. |
| [#218](https://github.com/ArdeleanLucas/PARSE/pull/218) | `2026-05-01T13:49:33+02:00` | `07abcaf` | ORTH default backend | Active docs now state ORTH defaults to HF Transformers `HFWhisperProvider` on `razhan/whisper-base-sdh`; STT remains faster-whisper; legacy ORTH requires `ortho.backend="faster-whisper"` plus a local CT2 directory. |
| [#219](https://github.com/ArdeleanLucas/PARSE/pull/219) | `2026-05-01T14:35:31+02:00` | `1e7defc` | HF ORTH fidelity | Docs now describe low-level `WhisperProcessor` + `WhisperForConditionalGeneration.generate()`, 30-second full-file chunks, generated-token logprob confidence, and the high-level-pipeline replacement. |
| [#220](https://github.com/ArdeleanLucas/PARSE/pull/220) | `2026-05-01T14:50:23+02:00` | `ddaefa3` | HF in-memory resampling | Getting Started / AI / architecture docs now note non-16 kHz in-memory clips are resampled to 16 kHz before HF Whisper feature extraction. |
| [#221](https://github.com/ArdeleanLucas/PARSE/pull/221) | `2026-05-01T15:20:05+02:00` | `d419b66` | Frontend batch cancel | User/AGENTS/docs now state Cancel stops frontend polling immediately, marks the current speaker cancelled, skips remaining speakers, and discards late successful poll results. |
| [#222](https://github.com/ArdeleanLucas/PARSE/pull/222) | `2026-05-01T15:41:34+02:00` | `6860ea0` | HF concept-window decode | Docs now state concept-window timing comes from caller-supplied windows and generation avoids `return_timestamps=True`; warning logs include exception class names on per-window failures. |
| [#223](https://github.com/ArdeleanLucas/PARSE/pull/223) | `2026-05-01T16:05:59+02:00` | `37e8b3c` | ORTH editor prefill | User/AGENTS docs now state the ORTHOGRAPHIC editor prefers direct `tiers.ortho` text before falling back to imported/derived `ortho_words`, while save flow still writes reviewed ORTH. |
| [#224](https://github.com/ArdeleanLucas/PARSE/pull/224) | `2026-05-01T16:30:50+02:00` | `6df823c` | Frontend backend-cancel call | API/AGENTS/user docs now include `cancelComputeJob()` and `POST /api/compute/{jobId}/cancel` as the browser batch-cancel backend hook. |
| [#225](https://github.com/ArdeleanLucas/PARSE/pull/225) | `2026-05-01T18:39:49+02:00` | `96c4535` | Cooperative ORTH cancellation | API/architecture/user/README/AGENTS docs now treat the cancel registry and `partial_cancelled` / `cancelled_at_interval` ORTH result metadata as shipped. |
| [#226](https://github.com/ArdeleanLucas/PARSE/pull/226) | `2026-05-01T19:06:36+02:00` | `d5860dd` | HF repetition guards | Config and docs now include `no_repeat_ngram_size`, `repetition_penalty`, deterministic generation flags, and prompt ids as HF-consumed decode-level guard knobs; only `compute_type` and VAD remain HF-ignored legacy keys. |
| [#227](https://github.com/ArdeleanLucas/PARSE/pull/227) | `2026-05-01T19:07:08+02:00` | `4f6f3bb` | Full-pipeline GPU lifecycle | Architecture/user/README/AGENTS docs now state full-pipeline ORTH unloads HF model/processor and clears/synchronizes CUDA cache before IPA, `Aligner.release()` frees wav2vec2 state, and a tunable 4 GiB pre-IPA guard protects long-audio runs. |
| [#228](https://github.com/ArdeleanLucas/PARSE/pull/228) | `2026-05-01T19:25:01+02:00` | `fb6da3b` | Stale speaker lock cleanup | API/architecture/developer/README/AGENTS docs now include startup cleanup and `POST /api/locks/cleanup`, JSON lock metadata, dead-PID / legacy cleanup, live-PID skip/manual-review semantics, `PARSE_STALE_LOCK_AGE_SEC`, and the no-process-kill safety contract. |
| [#229](https://github.com/ArdeleanLucas/PARSE/pull/229) | `2026-05-01T20:17:29+02:00` | `3c7823b` | Explicit ORTH provider lifecycle | Architecture/AGENTS/report now state `_LAST_ORTHO_PROVIDER` is gone; full-pipeline threads ORTH providers explicitly, IPA-only selections do not instantiate ORTH, and cleanup stays in local `try/finally` ownership. |

## Follow-ups not documented as shipped

| Scope | State at audit | Why it matters |
|---|---|---|
| Open PARSE PRs | #231 open at final freshness check (`fix(annotate): navigate concepts with arrow keys from fields`) | Frontend-only arrow-key navigation remains pending/review-blocked; no active doc claims it is shipped. |
| PR #230 | Closed, unmerged | The wav2vec2 IPA language-quality branch is not documented as shipped in active docs; it appears only as non-shipped queue/history context. |
| Frontend helper hygiene | PR #224 shipped `cancelComputeJob()` in the API contracts surface | The docs treat the route/helper as shipped because both client and server exist; any stricter frontend-hygiene change should be a separate implementation PR, not hidden inside this docs refresh. |

## Files refreshed by this documentation pass

| File | Reason |
|---|---|
| `AGENTS.md` | Updated current state, client/server contract table, Safe Work Now, and validation gates for HF ORTH, cancellation, full-pipeline GPU lifecycle, stale locks, provider threading, and test-count drift. |
| `README.md` | Updated first-impression runtime notes for HF ORTH, legacy CT2 opt-in, cooperative compute cancel, partial ORTH output, full-pipeline unload/VRAM guard, and stale-lock cleanup. |
| `config/ai_config.example.json` | Fixed stale HF comment that said decoder knobs were ignored, and added shipped HF repetition guard keys `no_repeat_ngram_size` / `repetition_penalty`. |
| `docs/ai-integration.md` | Refreshed provider table and ORTH config/behavior to the HF default and PR #219/#220/#222/#226 behavior. |
| `docs/api-reference.md` | Added `POST /api/compute/{jobId}/cancel`, `POST /api/locks/cleanup`, cooperative cancel semantics, and stale-lock cleanup contract. |
| `docs/architecture.md` | Added HF provider internals plus the compute cancellation / GPU lifecycle / stale-lock recovery architecture section. |
| `docs/developer-guide.md` | Updated speech stack and runtime-mode notes for HF ORTH, cooperative cancel, and stale-lock cleanup. |
| `docs/getting-started.md` | Replaced stale CT2-only ORTH setup with the current HF-default config and runtime notes, including resampling, guards, and legacy opt-in. |
| `docs/plans/deferred-validation-backlog.md` | Refreshed automated baseline to PR #224 frontend and PR #225/#227/#228/#229 backend validation counts. |
| `docs/user-guide.md` | Updated user-facing ORTH runtime, batch cancel, full-pipeline cleanup, and direct ORTH editor behavior. |
| `docs/reports/2026-05-01-calendar-day-merged-pr-doc-refresh.md` | Added this audit report with per-PR documentation consequences. |

## Coordinator sign-off

- Calendar-day merged PR coverage: **13/13 local-day merged PRs accounted for** (#214 plus #218-#229).
- Open PRs kept pending, not shipped: **yes** — final freshness check found open PR #231 and it remains documented only as pending; closed-unmerged PR #230 is also not documented as shipped.
- Contract fidelity: **current docs treat HF ORTH defaulting, low-level HF generation, resampling, concept-window decoding, repetition guards, frontend/backend cancel, cooperative ORTH partial cancel, direct ORTH editor priority, full-pipeline GPU cleanup, stale-lock cleanup, and explicit provider threading as shipped behavior only where merged PR evidence supports it**.
- Validation completed before commit: `git diff --check` passed; `python3 -m json.tool config/ai_config.example.json` passed; changed-Markdown relative-link scan checked **56** relative links with **0** missing and ignored only the known placeholder `docs/pr-assets/foo.png`; final freshness re-audit found the same **13/13** local-day merged PRs and open PR #231 pending/not shipped.
