# Orphan OpenClaw PARSE cleanup — 2026-05-06

## Why

PR #277 retired only the nested `PARSE-rebuild` subfolder under the old OpenClaw PARSE workspace. A follow-up path audit found two shallower PARSE-related OpenClaw trees still on disk and still referenced by live Hermes profile skills, which meant future agents could be routed back into retired code. This report is the docs-as-evidence record for the workstation cleanup requested in `.hermes/handoffs/parse-coordinator/2026-05-06-orphan-openclaw-parse-cleanup.md`.

References:
- Predecessor: <https://github.com/ArdeleanLucas/PARSE/pull/277>
- Report pattern: <https://github.com/ArdeleanLucas/PARSE/pull/280>
- Canonical PARSE clone: `/home/lucas/gh/tarahassistant/PARSE-rebuild` (`origin = ArdeleanLucas/PARSE`)

## Scope boundary

In scope:
- Archive and delete only the two PARSE-related orphan OpenClaw workspaces.
- Prune only the three stale `/tmp/parse-*` worktrees registered under the orphan clone.
- Patch live Hermes profile skills that emitted the retired paths.

Out of scope and left untouched:
- OpenClaw framework/services/configs: gateway, billing proxy, agents, skills, flows, cron, top-level `openclaw.json*`.
- Non-PARSE workspaces under `~/.openclaw/workspace/`.
- Historical sessions, memory, handoffs, plans, checkpoints, exports, and task logs.
- Renaming `/home/lucas/gh/tarahassistant/PARSE-rebuild`.

## Pre-check evidence

- Canonical repo head matched `origin/main`: `timestamp_utc=2026-05-06T07:39:10Z; canonical_repo=/home/lucas/gh/tarahassistant/PARSE-rebuild; canonical_head=141b1e7abf456ee492d43d2897bc7edd3a7c18e7; canonical_origin_main=141b1e7abf456ee492d43d2897bc7edd3a7c18e7`
- Pre-delete live process blocker scan: `BLOCKER_COUNT 0`
- Pre-delete second blocker scan: `BLOCKER_COUNT 0`
- Default `:8766` API was already absent before this cleanup. The active live PARSE stack was `/home/lucas/bin/parse-run` on alt ports `8866/8867/5174`, with canonical repo cwd for Vite and `/home/lucas/parse-workspace` cwd for the backend.

Live count evidence:

```text
before_8766: unavailable_or_empty
before_8866: speakers=10 concepts=617 sample=Fail01,Fail02,Kalh01,Khan01
mid_before_rm_8766: unavailable_or_empty
mid_before_rm_8866: speakers=10 concepts=617 sample=Fail01,Fail02,Kalh01,Khan01
mid_after_rm_8766: unavailable_or_empty
mid_after_rm_8866: speakers=10 concepts=617 sample=Fail01,Fail02,Kalh01,Khan01
after_8766: unavailable_or_empty
after_8866: speakers=10 concepts=617 sample=Fail01,Fail02,Kalh01,Khan01
```

Khan01 sentinel captured after cleanup from the active alt API:

```text
after_8766: unavailable_or_empty
after_8866: concept_rows=286 ortho_word_rows=184 source_audio=audio/working/Khan01/REC00002.wav duration=8590.524013605442 first_concept_text=one first_concept_start=1271.844 first_concept_end=1272.78 first_ortho_text=کوڕ و کچ. مال و باخ. ئاو و خاک. هاتن و چوون. ئەم زمانە کوردیە. یەک. یێک first_ortho_start=1271.844 first_ortho_end=1272.78
```

Deviation note: the handoff's nominal `:8766` continuity check could not be used because no service was listening on `:8766` at pre-check time. I did not start or stop live PARSE; continuity was verified on the already-running alt stack instead.

## What was archived

Archive path: `/home/lucas/archive/parse-openclaw-orphan-2026-05-06/`

Archive total size at report time: **3.24 GiB** (3478814952 bytes)

| Source tree | Pre-delete size | Tarball | Tarball size | SHA256 |
|---|---:|---|---:|---|
| `/home/lucas/.openclaw/workspace/parse/` | `2.0G	.` | `workspace-parse-2026-05-06.tar.gz` | 783.95 MiB | `960c9a7d694679f56ebfcd5efbb0f3eae5d37081912fa7ce7f8e02462b9dbce6` |
| `/home/lucas/.openclaw/workspace/parse-desktop-core/` | `5.8G	.` | `workspace-parse-desktop-core-2026-05-06.tar.gz` | 2.47 GiB | `bccef4df368cf09d920bf828f455bd86f5094ae3fabd9f4dadf825114ef0be93` |

Integrity:

```text
TARBALL_OK workspace-parse-2026-05-06.tar.gz
TARBALL_OK workspace-parse-desktop-core-2026-05-06.tar.gz
sha256 manifest lines: 94
latest manifest check: `sha256-check-after-late-emitters.txt` completed successfully (all entries OK)
```

Captured provenance includes remotes, heads, log tails, status, untracked-file inventories, worktree lists, diffs, and full tarballs. Notable pre-delete states:

`workspace/parse` status:

```text
?? coarse_transcripts/Fail01_stt.json
?? coarse_transcripts/Fail02_stt.json
?? coarse_transcripts/Kalh01_stt.json
?? coarse_transcripts/Kifr01_stt.json
?? coarse_transcripts/Mand01_stt.json
?? coarse_transcripts/Qasr01_stt.json
?? coarse_transcripts/Saha01_stt.json
?? docs/plans/MC-271-import-copy-lufs-scan.md
?? docs/plans/MC-288-290-chat-xai-stt-model-pipeline.md
?? docs/review_tool_body.txt
?? docs/review_tool_css.txt
?? peaks/Fail01.json
?? peaks/Fail02.json
?? peaks/Kalh01.json
?? peaks/Kifr01.json
?? peaks/Mand01.json
?? peaks/Qasr01.json
?? peaks/Saha01.json
```

`workspace/parse-desktop-core` status:

```text
M config/ai_config.json
 M source_index.json
?? cross_speaker_matches.json
?? exports/wordlist.tsv
?? project.json
```

## Worktrees pruned

The stale worktrees were removed through `git worktree remove --force` / `git worktree prune`, not raw directory deletion.

```text
/tmp/parse-main-audit removed
/tmp/parse-oracle-tags-parity-current removed
/tmp/parse-pr70-review removed
```

Before/after registry snapshots are saved as:
- `/home/lucas/archive/parse-openclaw-orphan-2026-05-06/worktree-list-before-prune.txt`
- `/home/lucas/archive/parse-openclaw-orphan-2026-05-06/worktree-list-after-prune.txt`

## What was deleted

Deletion was performed only after tarball integrity and SHA checks passed.

```text
workspace/parse gone
workspace/parse-desktop-core gone
```

Deleted exact paths:
- `/home/lucas/.openclaw/workspace/parse/`
- `/home/lucas/.openclaw/workspace/parse-desktop-core/`

## Skills patched

Primary handoff requirement — nine live PARSE profile skill files:

| Profile | Skill | Diff lines changed | Remaining retired-path refs |
|---|---|---:|---:|
| `parse-back-end` | `parse-agent-audit` | 58 | 0 |
| `parse-back-end` | `parse-mc-workflow` | 53 | 0 |
| `parse-back-end` | `parse-ai-onboarding` | 9 | 0 |
| `parse-coordinator` | `parse-agent-audit` | 58 | 0 |
| `parse-coordinator` | `parse-mc-workflow` | 57 | 0 |
| `parse-coordinator` | `parse-ai-onboarding` | 9 | 0 |
| `parse-front-end` | `parse-agent-audit` | 58 | 0 |
| `parse-front-end` | `parse-mc-workflow` | 49 | 0 |
| `parse-front-end` | `parse-ai-onboarding` | 9 | 0 |

Additional live-emitter cleanup found by the post-nine-file scan:

| Target | Skill | Diff lines changed | Remaining retired-path refs |
|---|---|---:|---:|
| `thesis-writer` | `parse-agent-audit` | 58 | 0 |
| `thesis-writer` | `parse-mc-workflow` | 49 | 0 |
| `thesis-writer` | `parse-ai-onboarding` | 9 | 0 |
| `parse-front-end-legacy-home-20260427-135725` | `parse-agent-audit` | 58 | 0 |
| `parse-front-end-legacy-home-20260427-135725` | `parse-mc-workflow` | 49 | 0 |
| `parse-front-end-legacy-home-20260427-135725` | `parse-ai-onboarding` | 9 | 0 |

Late broad validation-scan cleanup:

| Target | File | Diff lines changed | Remaining retired-path refs |
|---|---|---:|---:|
| `global-dogfood` | `/home/lucas/.hermes/skills/dogfood/parse-hermes-path-drift-audit/SKILL.md` | 11 | 0 |
| `parse-front-end-normalize-backup` | `/home/lucas/.hermes/profiles/parse-front-end/normalize-backup-20260427-135725/config.yaml` | 2 | 0 |


Backups and diffs:
- Before backups: `/home/lucas/archive/parse-openclaw-orphan-2026-05-06/skills-before/`
- After diffs: `/home/lucas/archive/parse-openclaw-orphan-2026-05-06/skills-after/`
- Summaries: `skills-patch-summary.json`, `additional-skills-patch-summary.json`, `late-emitter-patch-summary.json`

Final live-emitter scan:

```text
hits: 0
```

The final scan command used the broad validation pattern for `/home/lucas/.openclaw/workspace/parse` and excluded historical `sessions/`, `memory/`, `handoffs/`, `plans/`, `task-log`, `checkpoints/`, and `exports/` paths per the handoff.

## Out-of-scope guard

- `openclaw-gateway.service`: `active`
- `openclaw-billing-proxy.service`: `active`
- Crontab unchanged: `unchanged`

The three OpenClaw cron lines remained present:

```text
* * * * * /home/lucas/.openclaw/workspace/tools/gateway-monitor.sh >> /dev/null 2>&1
0 18 * * * /home/lucas/.openclaw/workspace/tools/path-scanner.sh
0 6 * * * script -q -c 'claude -p "ping" --max-turns 1 --no-session-persistence' /dev/null >> /home/lucas/.openclaw/logs/token-refresh.log 2>&1
```

## Rollback

Workspace rollback:

```bash
mkdir -p /home/lucas/.openclaw/workspace
cd /home/lucas/.openclaw/workspace
tar -xzf /home/lucas/archive/parse-openclaw-orphan-2026-05-06/workspace-parse-2026-05-06.tar.gz
tar -xzf /home/lucas/archive/parse-openclaw-orphan-2026-05-06/workspace-parse-desktop-core-2026-05-06.tar.gz
```

Skill rollback:

```bash
# Example shape; restore the relevant backup file from skills-before/ to its original profile skill path.
cp /home/lucas/archive/parse-openclaw-orphan-2026-05-06/skills-before/<profile>-<skill>.SKILL.md.bak \
   /home/lucas/.hermes/profiles/<profile>/skills/software-development/<skill>/SKILL.md
```

Before any rollback, verify the target service/process is not using a restored retired path; the cleanup intentionally removed recurrence vectors from live skills.

## Sign-off

Coordinator sign-off for this workstation cleanup: **ready for PR review**.

Evidence status:
- Disk deletion: passed.
- Archive integrity: passed.
- Live active PARSE continuity on `8866`: passed (`10` speakers, `617` concepts before/mid/after).
- Default `8766`: unavailable before and after; not caused by cleanup.
- Skill recurrence scan: passed (`0` live-emitter hits).
- OpenClaw framework guard: passed (services active, crontab unchanged).
