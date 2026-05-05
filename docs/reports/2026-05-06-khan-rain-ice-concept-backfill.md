# Khan rain/ice concept backfill — PR #276 unblock

- Date: 2026-05-06 coordinator execution
- Handoff: `.hermes/handoffs/parse-coordinator/2026-05-06-khan-rain-ice-concept-backfill-pr276-unblock.md`
- Unblocks: [PR #276](https://github.com/ArdeleanLucas/PARSE/pull/276)
- Depends on: [PR #277](https://github.com/ArdeleanLucas/PARSE/pull/277), [PR #278](https://github.com/ArdeleanLucas/PARSE/pull/278)

## Why

PR #276 adds live API contract guards for Khan annotation workspace data. Before this backfill, the live API served exactly four Khan concept-tier intervals without `concept_id` because the workspace concept registry lacked source-specific rows for:

- `JBIL` source item `126` (`rain`)
- `KLQ` source item `3.5` (`ice`)

## Live workspace changes

The repo does not track `/home/lucas/parse-workspace/concepts.csv`; this PR records the live workspace mutation and validation evidence.

Backup created before mutation:

```text
/home/lucas/parse-workspace/concepts.csv.bak-pre-rain-ice-backfill-2026-05-05
/home/lucas/parse-workspace/annotations/backups/20260505T221243Z-khan-rain-ice-backfill/
```

Exactly two rows were appended to `/home/lucas/parse-workspace/concepts.csv`:

```csv
616,rain (B),126,JBIL,
617,ice,3.5,KLQ,
```

Unified diff against the pre-backfill backup:

```diff
--- /home/lucas/parse-workspace/concepts.csv.bak-pre-rain-ice-backfill-2026-05-05
+++ /home/lucas/parse-workspace/concepts.csv
@@ -614,3 +614,5 @@
 613,sister A,75,JBIL,
 614,grass A,107,JBIL,
 615,river A,127,JBIL,
+616,rain (B),126,JBIL,
+617,ice,3.5,KLQ,
```

## Re-import path

Staging annotations were generated under:

```text
/tmp/khan-rain-ice-backfill-20260505T221243Z/
```

Only the four missing `concept_id` fields were filled in staging inputs:

| Speaker | Interval | Text | `audition_prefix` | `import_index` | Backfilled `concept_id` |
|---|---:|---|---|---:|---:|
| Khan01 | 127 | rain | 126 | 127 | 616 |
| Khan02 | 50 | ice | 3.5 | 50 | 617 |
| Khan02 | 305 | rain | 126 | 305 | 616 |
| Khan03 | 125 | rain | 126 | 125 | 616 |

The live Khan01/Khan02/Khan03 annotations were then re-imported via `ParseChatTools.execute("import_processed_speaker", ...)` from current `origin/main` (`383cb12`, PR #278 present). The import path wrote both `annotations/<Speaker>.json` and `annotations/<Speaker>.parse.json`; the live WAV copy was idempotent, and staged peaks/transcript copies avoided same-file copy errors.

`concepts.csv` remained byte-stable during all three imports:

```text
ca44d952914b0a2e9f0ff5786862867f15dffb3f166e325fba3c52dfcf942279  /home/lucas/parse-workspace/concepts.csv
```

## Validation evidence

Workspace state after backfill:

```text
concepts.csv splitline count: 618
line delta vs backup: +2
prefix unchanged: true
tail:
  615,river A,127,JBIL,
  616,rain (B),126,JBIL,
  617,ice,3.5,KLQ,
```

Live API probe after re-import:

| Speaker | Concept intervals | Missing `concept_id` | Missing trace fields |
|---|---:|---:|---:|
| Khan01 | 286 | 0 | 0 |
| Khan02 | 503 | 0 | 0 |
| Khan03 | 283 | 0 | 0 |

Sentinel values served by `GET /api/annotations/<speaker>`:

```text
Khan01[127]: text=rain, audition_prefix=126, import_index=127, concept_id=616
Khan02[50]:  text=ice,  audition_prefix=3.5, import_index=50,  concept_id=617
Khan02[305]: text=rain, audition_prefix=126, import_index=305, concept_id=616
Khan03[125]: text=rain, audition_prefix=126, import_index=125, concept_id=616
```

PR #276 live API regression command:

```bash
cd /home/lucas/gh/worktrees/khan-api-contract-tests
PARSE_API_BASE_URL=http://127.0.0.1:8766 \
  npx vitest run --config vitest.integration.ts src/__tests__/apiRegression.test.ts --reporter=verbose
```

Result:

```text
Test Files  1 passed (1)
Tests       27 passed (27)
Khan01 sentinel: pass
Khan02 sentinel: pass
Khan03 sentinel: pass
Saha01 positive control: pass
```

PR #278 tool regression command:

```bash
cd /home/lucas/gh/worktrees/backfill-rain-ice-concepts
PARSE_PORT=18766 BLOCK_LIVE_PROCESS_ISOLATION=1 PYTHONPATH=python \
  python3 -m pytest -xvs python/ai/tools/test_speaker_import_tools.py
```

Result:

```text
15 passed, 1 warning in 0.20s
```

Live continuity after verification:

```text
2026-05-05T22:15:05Z
/api/config ok
/api/annotations/Khan01 ok, 286 concept intervals, 0 missing concept_id
/api/annotations/Khan02 ok, 503 concept intervals, 0 missing concept_id
/api/annotations/Khan03 ok, 283 concept intervals, 0 missing concept_id
```

## Rollback path

If rollback is needed, restore from:

```text
/home/lucas/parse-workspace/concepts.csv.bak-pre-rain-ice-backfill-2026-05-05
/home/lucas/parse-workspace/annotations/backups/20260505T221243Z-khan-rain-ice-backfill/
```

Do not hand-edit live `.parse.json` files; use the preserved backup or the import tool path.
