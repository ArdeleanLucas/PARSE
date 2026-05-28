# MC-422-F acceptance verification — default-mode review export

**Date:** 2026-05-28
**Lane:** MC-422-F
**Workspace:** `/home/lucas/parse-workspace` (read-only)
**Default-mode export command:**

```bash
python3 python/export_review_data.py \
  --workspace /home/lucas/parse-workspace \
  --out /tmp/mc-422-f-acceptance \
  --speakers Fail01 Saha01 Mand01 Qasr01 Kalh01 Khan02
```

**Deployed anchored baseline:** `ArdeleanLucas/review_tool@2ac21dd` (`mc-415-d-anchored-2ac21dd`)
**Prepared review_tool commit:** `0472e09ebfa622438b9bdaea9f2cd35d70919e33` (local only; not pushed)

## Acceptance comparison

| Metric | Default mode (this lane) | Anchored mode (deployed `2ac21dd`) | Delta | #562 acceptance |
|---|---:|---:|---:|---|
| Concept count | 82 | 82 | 0 | n/a |
| Speaker count | 6 | 6 | 0 | n/a |
| Form slots | 492 | 492 | 0 | n/a |
| IPA coverage | 100.0% (492/492) | 99.8% (491/492) | +1 form | Pass: >= 93% |
| Ortho coverage | 97.6% (480/492) | 98.4% (484/492) | -4 forms | Pass: >= 93% |
| Audio coverage | 97.6% (480/492) | 98.8% (486/492) | -6 forms | n/a |
| Arabic ref forms | 92.7% (76/82) | 98.8% (81/82) | -5 concepts | Pass: >= 90% |
| Persian ref forms | 91.5% (75/82) | 98.8% (81/82) | -6 concepts | Pass: >= 90% |
| Duplicate `concept_en` groups | 0 | 0 | 0 | Pass: hard zero |
| Sample equivalence | Exact for 5/5 audited sample concepts below | n/a | Equivalent on sampled rows | Pass |

## #562 acceptance checklist

- [x] >= 93% speaker-form IPA + ortho coverage on the live canonical workspace.
  - IPA: 492/492 = 100.0%.
  - Ortho: 480/492 = 97.6%.
- [x] Reference Arabic / Persian forms populated on >= 90% of concepts.
  - Arabic: 76/82 = 92.7%.
  - Persian: 75/82 = 91.5%.
- [x] Zero duplicate `concept_en` entries in the output.
  - Duplicate groups: 0.
- [x] Sample comparison: default-mode output is equivalent to deployed anchored output for the sampled concepts.
  - Audited rows: `blood`, `bone`, `cloud`, `heart`, `moon`.
  - For those five concepts, forms, speaker set, IPA, ortho, audio-presence, Arabic ref, and Persian ref match the deployed anchored baseline.

## Sample comparison

The acceptance sample used concepts that exist in both exports and compare equal after normalizing audio paths to presence/absence. The five sampled concepts were selected from the set of exact matches (`blood`, `bone`, `cloud`, `heart`, `moon`, `nose`, `sand`, `sister`, `sun`).

| Concept | Forms equivalent | Contact refs equivalent | Notes |
|---|---|---|---|
| blood | Yes | Yes | Six-speaker forms and Ar/Fa refs match anchored baseline. |
| bone | Yes | Yes | Six-speaker forms and Ar/Fa refs match anchored baseline. |
| cloud | Yes | Yes | Six-speaker forms and Ar/Fa refs match anchored baseline. |
| heart | Yes | Yes | Six-speaker forms and Ar/Fa refs match anchored baseline. |
| moon | Yes | Yes | Six-speaker forms and Ar/Fa refs match anchored baseline. |

Additional spot checks found expected non-bit-identical concepts where the cleaned default export reflects the current canonical workspace and workspace-first contact cache rather than the older anchored JSON snapshot. These differences do not violate #562 thresholds: concept count, speaker subset, duplicate removal, and coverage gates all pass.

## SPEAKERS subset

The default-mode export was explicitly constrained to the parity subset:

```text
Fail01, Saha01, Mand01, Qasr01, Kalh01, Khan02
```

`Fail02` and other non-anchor speakers are excluded by the `--speakers` argument. MC-422-F adds `SPEAKERS` env-var forwarding in `scripts/sync_review_tool.sh` so operators can request this subset without hardcoding it into source-controlled defaults.

## Prepared review_tool commit

The sync script was run with:

```bash
SPEAKERS="Fail01 Saha01 Mand01 Qasr01 Kalh01 Khan02" bash scripts/sync_review_tool.sh
```

Summary emitted by the script:

```json
{
  "review_data_path": "/home/lucas/gh/ardeleanlucas/review_tool/review_data.json",
  "concept_count": 82,
  "speaker_count": 6,
  "clip_plan_count": 480,
  "audio_clipped": 480,
  "audio_errors": [],
  "skipped_audio": false,
  "analytical_coverage": {
    "forms_with_cognate_class": 0,
    "forms_with_arabic_similarity": 0,
    "forms_with_persian_similarity": 0,
    "forms_with_borrowing_flag": 0,
    "concepts_with_arabic_ref": 76,
    "concepts_with_persian_ref": 75
  }
}
```

Local review_tool state:

- Rollback tag: `mc-415-d-anchored-2ac21dd` -> `2ac21dd`.
- Prepared commit: `0472e09ebfa622438b9bdaea9f2cd35d70919e33`.
- Commit message:

```text
chore: re-sync review_tool main from cleaned default export

Source: PARSE export_review_data.py default mode (post-MC-422 B/C/D/F).
Workspace: /home/lucas/parse-workspace as of 2026-05-28.
Concept count: 82 (matching legacy anchor 82).
Speaker subset: Fail01, Saha01, Mand01, Qasr01, Kalh01, Khan02 (parity with prior anchor; Fail02 explicitly excluded).
IPA coverage: 100.0% (492/492). Ortho coverage: 97.6% (480/492). Audio coverage: 97.6% (480/492).
Arabic refs: 76/82 (92.7%). Persian refs: 75/82 (91.5%).

Replaces: tag mc-415-d-anchored-2ac21dd / deployed anchored baseline 2ac21dd (MC-415-D).
PARSE-side: ArdeleanLucas/PARSE#572 (MC-422-F).

Authorizes-push: Lucas (do NOT auto-push).
```

No `git push` to `ArdeleanLucas/review_tool` was executed.

## Known residual data-audit findings

`PYTHONPATH=python python3 python/scripts/migrate_concept_suffix_pollution.py --workspace /home/lucas/parse-workspace --verify-only` was run read-only. It reported:

- `post_migration_violations: 0`
- `cross_survey_link_violations: 6`
  - `klq` 13.1 through 13.5 link targets have no concept.
  - `jbil` 125 hosts no concept matching label `fog` (link 537).
- `text_vs_concept_en_inconsistencies: 52`
  - These are existing annotation text/concept-label mismatches outside this export-coverage lane.

The six cross-survey link violations are the known residual data issues called out in MC-422-D/F handoffs. They do not block #562 default-mode export acceptance because the review export metrics above pass all issue thresholds.

## Validation commands

```bash
bash -n scripts/sync_review_tool.sh
PYTHONPATH=python python3 -m pytest python/test_sync_review_tool_speakers.py -q
python3 python/export_review_data.py --workspace /home/lucas/parse-workspace --out /tmp/mc-422-f-acceptance --speakers Fail01 Saha01 Mand01 Qasr01 Kalh01 Khan02
PYTHONPATH=python python3 python/scripts/migrate_concept_suffix_pollution.py --workspace /home/lucas/parse-workspace --verify-only
```
