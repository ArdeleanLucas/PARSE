# MC-425 clarifier-collapse acceptance report

**Date:** 2026-05-28  
**Workspace:** `/home/lucas/parse-workspace`  
**Lane:** MC-425-B — live run for #561 Option 2  
**Dependency:** MC-425-A / PR #575 merged into `origin/main` as `7b159b501f991b89965af133aada33500a201043`.

## Summary

MC-425-B ran MC-425-A's migration against the live workspace after a dry-run and after stopping the active PARSE launcher/server listeners to avoid concurrent writes.

| Step | Result |
| --- | --- |
| Dry-run | `565 -> 563` concept rows; 2 clarifier merge-map entries; 2 groups collapsed; 0 backups |
| Real run | `565 -> 563` concept rows; 2 clarifier merge-map entries; 2 groups collapsed; 8 backups |
| Idempotence run | `563 -> 563` concept rows; 0 merge-map entries; 0 groups collapsed; 0 backups |
| Hard post-migration invariant | `verify_post_migration` violations dropped from 2 pre-run to 0 post-run |
| Same-slot clarifier sibling groups | 2 pre-run, 0 post-run |
| Literal singleton paren rows | 41 pre-run, 38 post-run; preserved intentionally per MC-425-A because singleton clarifier rows are not duplicate sibling groups |

The two collapsed same-slot groups were both `hair` groups:

1. `JBIL` item `32`: `250 -> 249`
2. `KLQ` item `1.1`: `599 -> 1`

This differs from the handoff's illustrative "hair triple" shorthand: current live data has two survey/item slots, so MC-425-A correctly collapses them per slot rather than across surveys.

## Commands and outputs

### Dry-run

```bash
python3 python/scripts/migrate_concept_suffix_pollution.py \
  --workspace /home/lucas/parse-workspace --dry-run
```

```text
Migration DRY-RUN
  concepts.csv rows: 565 -> 563
  merge_map entries: 0
  clarifier merge_map entries: 2
  clarifier merge_map:
    250 -> 249
    599 -> 1
  clarifier groups collapsed: 2
  clarifier notes updated: 2
  annotation files rewritten: 5
  intervals re-keyed: 15
  interval text fields stripped: 0
  speaker concept_tags re-keyed: 5
  parse-tags.json entries re-keyed: 1
  survey-overlap.json entries re-keyed: 4
  backups: 0
```

### Semantic spot-check of planned merge map

```text
MAP 250 -> 249
  id=249 concept_en='hair (men)' survey='JBIL' item='32'
  id=250 concept_en='hair (women)' survey='JBIL' item='32'

MAP 599 -> 1
  id=1 concept_en='hair' survey='KLQ' item='1.1'
  id=599 concept_en='hair (collective)' survey='KLQ' item='1.1'
```

Both planned rewrites are within the same `(source_survey, source_item, strip_clarifier(concept_en))` slot.

### Real run

Before applying, active PARSE launcher/Vite/backend writer processes were stopped. The backend listener on `:8866` was terminated before the committed run.

```bash
python3 python/scripts/migrate_concept_suffix_pollution.py \
  --workspace /home/lucas/parse-workspace
```

```text
Migration COMPLETE
  concepts.csv rows: 565 -> 563
  merge_map entries: 0
  clarifier merge_map entries: 2
  clarifier merge_map:
    250 -> 249
    599 -> 1
  clarifier groups collapsed: 2
  clarifier notes updated: 2
  annotation files rewritten: 5
  intervals re-keyed: 15
  interval text fields stripped: 0
  speaker concept_tags re-keyed: 5
  parse-tags.json entries re-keyed: 1
  survey-overlap.json entries re-keyed: 4
  backups: 8
```

MC-425-A's verifier also printed existing workspace audit findings. A pre/post backup comparison proved the six cross-survey link violations were unchanged by this migration; see [Verifier notes](#verifier-notes).

## Backups

The real run created these eight rollback files:

```text
/home/lucas/parse-workspace/annotations/Fail01.parse.json.bak-20260528T183919Z-pre-clarifier-collapse
/home/lucas/parse-workspace/annotations/Kalh01.parse.json.bak-20260528T183919Z-pre-clarifier-collapse
/home/lucas/parse-workspace/annotations/Khan01.parse.json.bak-20260528T183919Z-pre-clarifier-collapse
/home/lucas/parse-workspace/annotations/Khan02.parse.json.bak-20260528T183919Z-pre-clarifier-collapse
/home/lucas/parse-workspace/annotations/Khan03.parse.json.bak-20260528T183919Z-pre-clarifier-collapse
/home/lucas/parse-workspace/concepts.csv.bak-20260528T183919Z-pre-clarifier-collapse
/home/lucas/parse-workspace/parse-tags.json.bak-20260528T183919Z-pre-clarifier-collapse
/home/lucas/parse-workspace/survey-overlap.json.bak-20260528T183919Z-pre-clarifier-collapse
```

Hashes:

```text
pre concepts.csv:  41319c7f3c93033716231053cb2f8a976fa706cf27f0400db74c10eae334d897
post concepts.csv: d3c7fda164c03aa09690133f92ea87a809d3ce1bc9405048bfefb4bad7fa68ff
post notes JSON:   44b1f365d384b08409d1b43545aa6f51e22961ac73644509fd1a5abbc90281ee
```

## Sample collapsed rows

### 1. KLQ item 1.1 — canonical `hair` (`id=1`)

**Before:**

```text
id=1   concept_en='hair'              source_survey='KLQ' source_item='1.1'
id=599 concept_en='hair (collective)' source_survey='KLQ' source_item='1.1'
```

**After:**

```text
id=1 concept_en='hair' source_survey='KLQ' source_item='1.1'
```

**Re-keyed source row:** `599 -> 1`

### 2. JBIL item 32 — canonical `hair` from `hair (men)` (`id=249`)

**Before:**

```text
id=249 concept_en='hair (men)'   source_survey='JBIL' source_item='32'
id=250 concept_en='hair (women)' source_survey='JBIL' source_item='32'
```

**After:**

```text
id=249 concept_en='hair' source_survey='JBIL' source_item='32'
```

**Re-keyed source row:** `250 -> 249`

### 3. Collapsed source row `hair (women)` (`id=250`)

`hair (women)` is preserved in the δ-format note for canonical concept `249` and all references were re-keyed to `249`.

```text
- hair (women) — was concept_id 250
```

### 4. Collapsed source row `hair (collective)` (`id=599`)

`hair (collective)` is preserved in the δ-format note for canonical concept `1` and all references were re-keyed to `1`.

```text
- hair (collective) — was concept_id 599
```

## δ-format notes snippets

MC-425-A stores the compare-note mirror at:

```text
/home/lucas/parse-workspace/parseui-compare-notes-v1.json
```

### Canonical concept `1`

```text
Merged from clarifier rows on 2026-05-28:
- hair — was concept_id 1
- hair (collective) — was concept_id 599
```

### Canonical concept `249`

```text
Merged from clarifier rows on 2026-05-28:
- hair (men) — was concept_id 249
- hair (women) — was concept_id 250
```

## Idempotence proof

A second run after the real migration made no writes and created no new backups.

```text
Migration COMPLETE
  concepts.csv rows: 563 -> 563
  merge_map entries: 0
  clarifier merge_map entries: 0
  clarifier groups collapsed: 0
  clarifier notes updated: 0
  annotation files rewritten: 0
  intervals re-keyed: 0
  interval text fields stripped: 0
  speaker concept_tags re-keyed: 0
  parse-tags.json entries re-keyed: 0
  survey-overlap.json entries re-keyed: 0
  backups: 0
```

Backup-list diff before vs after the idempotence run was empty:

```text
# diff -u /tmp/mc425b-backups-before-second.txt /tmp/mc425b-backups-after-second.txt
# no output
```

The second run exited `1` only because MC-425-A's script returns failure when pre-existing verifier/audit findings are present; the migration counters and backup diff prove the second run was a no-op.

## Verification queries

### Same-slot clarifier sibling groups

```text
pre:  clarifier_merge_map_entries=2 groups=2 map={'250': '249', '599': '1'}
post: clarifier_merge_map_entries=0 groups=0 map={}
```

### Hard post-migration violations

```text
pre:  post_migration_violations=2
post: post_migration_violations=0
```

### Literal paren rows

The handoff asked for "0 rows whose `concept_en` ends with parens". MC-425-A intentionally preserves singleton clarifier rows (PR #575 body: "Preserves singleton clarifier rows: no sibling group means no merge"), so the meaningful Option-2 invariant is zero same-slot sibling merge candidates, not zero literal parentheses.

```text
pre literal parenthetical rows:  41
post literal parenthetical rows: 38
```

Examples intentionally still present because they have no same-slot sibling to merge:

```text
id=61 concept_en=fat (man) survey=KLQ item=4.9
id=91 concept_en=green (grass) survey=KLQ item=5.4
id=167 concept_en=to bathe (wash oneself) survey=KLQ item=6.5
```

## Verifier notes

The real run and idempotence run printed six cross-survey link violations. Reconstructing the pre-run workspace from the MC-425-B backups showed the cross-survey set was identical before and after this migration:

```text
added_cross= []
removed_cross= []
```

The unchanged cross-survey findings are:

```text
link target (klq, 13.1) has no concept
link target (klq, 13.2) has no concept
link target (klq, 13.3) has no concept
link target (klq, 13.4) has no concept
link target (klq, 13.5) has no concept
link target (jbil, 125) hosts no concept matching label 'fog' (links 537)
```

The text-vs-`concept_en` informational audit changed as expected around the hair rows: clarifier text remains in intervals while the canonical concept labels now read `hair`, with the δ-format notes preserving the merged clarifier provenance.

## Regression tests

```text
PYTHONPATH=python python3 -m pytest tests/migration/ -x -q
21 passed in 0.09s
```

```text
PYTHONPATH=python python3 -m pytest python/ -x -q
1758 passed, 6 skipped, 1 warning, 3 subtests passed in 29.17s
```

## Issue closure

#561 was closed after PR #576 existed, with a comment referencing both delivery options:

- Option 1: MC-422-D / PR #570 — clarifier-tolerant validator plus export-time dedup safety net.
- Option 2: MC-425-A / PR #575 — data-model re-merge migration extension with δ-format notes, plus this MC-425-B live-run acceptance report in PR #576.

Closure command output:

```text
✓ Closed issue ArdeleanLucas/PARSE#561 (Clarifier-tolerant concept identity (post-MC-418 follow-up))
```

Verified issue state:

```text
#561 state=CLOSED closedAt=2026-05-28T18:43:26Z
```

Issue URL: <https://github.com/ArdeleanLucas/PARSE/issues/561>

PR URL: <https://github.com/ArdeleanLucas/PARSE/pull/576>
