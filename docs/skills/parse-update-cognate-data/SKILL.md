---
name: parse-update-cognate-data
description: Correctly update cognate (and related per-speaker decision) data in the main PARSE app and verify it persists and displays. Use when cognate states must be set/changed for one or more concepts, or when cognate data looks missing/blank/stale in Compare. Covers the storage shape, the concept-key rule, manual-vs-automatic precedence, legacy-key migration, and end-to-end verification. Data- and language-agnostic.
triggers:
  - "update cognate data in PARSE"
  - "set cognate states / cognate letters for a concept"
  - "cognate decisions not persisting"
  - "cognate data missing or blank in Compare"
  - "cognate letters gone after a migration/restore/import"
  - "repopulate cognate decisions in PARSE"
---

# Update cognate decision data in PARSE (and verify it sticks)

Authoritative reference: **`docs/data-persistence-model.md`** in the PARSE repo. This
skill is the operational runbook for that model. All examples use generic
placeholders (`<conceptKey>`, `<Speaker>`, group `A`/`B`); substitute your own.

## Scope

The main PARSE app's cognate decisions live in **`parse-enrichments.json`** in the
workspace, under:

```
manual_overrides.cognate_sets[<conceptKey>] = { "A": ["<Speaker>", ...], "B": [...], ... }
```

- `<conceptKey>` is a `concepts.csv` `id` (see "Concept key" below).
- Each group is a **single uppercase letter** (`A`, `B`, `C`, …); a speaker listed
  under a letter is in that cognate class for that concept.
- This is the **manual** layer and it **wins** over the top-level (automatic)
  `cognate_sets`. A workspace whose cognates are authored by hand has an **empty
  top-level** `cognate_sets` — never judge "is the data there?" by the top-level block.

(The same key/precedence rules apply to the sibling decision blocks:
`speaker_flags`, `borrowing_flags`, `cognate_decisions`, `discarded_forms`,
`concept_merges`. `canonical_lexemes` is keyed by `bundle:<slug>`, not a concept key.)

This is **not** the review_tool. The review_tool has its own separate file and is
irrelevant here.

## Concept key (get this right or the data is invisible)

`<conceptKey>` is minted exactly like the UI mints `Concept.key`:

- **Singleton concept** (one `concepts.csv` row for the elicitation) → the row's own `id`.
- **Grouped concept** (≥2 rows sharing `(source_survey, source_item)`) → the
  **canonical** key = `min(member_ids)`.

Never key on `source_item` or `source:<survey>:<item>` — those are legacy and either
get auto-promoted (SAFE) or left blank for triage (AMBIGUOUS). To resolve a gloss to
its key: look up the row(s) in `concepts.csv`, apply the rule above.

## Updating the data — two correct paths

Pick ONE; do not hand-merge while the server may also be writing.

**A. Through the app (preferred for a few concepts).** Set the cognate letters in
Compare. The app writes `manual_overrides.cognate_sets[...]` atomically under the
correct key for you. Nothing else to do except the verification below.

**B. Out-of-band write (batch / scripted / external authoring).** When writing the
file directly or via an authoring tool:
1. **Stop the PARSE server first** (the file is written with optimistic concurrency
   — an out-of-band write while the server holds the file can be lost or aborted).
2. Write/merge into `manual_overrides.cognate_sets[<conceptKey>]` using the correct
   key and the `{GROUP:[speakerId]}` shape. Speaker ids must match the annotation
   speaker ids **verbatim** (case/suffix).
3. Write atomically (temp + rename) and keep a timestamped backup of the original.
   Prefer the repo's atomic writer (`canonical_lexemes.save_enrichments_atomic`) or
   mirror its behavior.
4. Preserve unknown top-level keys (notes, `*_applied_at`, hashes) — do not drop them.

## Migrate legacy keys (do this once after any restore/import/upgrade)

```
python3 python/scripts/migrate_concept_key_namespace.py --workspace <WS> --report /tmp/keymig.json   # dry-run
# then add --execute (server stopped) to rewrite
```
- **SAFE** legacy keys are auto-promoted at read time, but `--execute` cleans them on disk.
- **AMBIGUOUS** keys (a legacy key that collided with a real concept id) are **not**
  auto-moved — they read **blank** in the app until you manually re-key them. The
  dry-run report lists each one with its two concepts and affected speakers.

## Verify it persisted AND displays (always do this)

1. **API truth check** — query the backend (default port `8766`, or `$PARSE_PORT`):
   ```
   curl -s http://127.0.0.1:<PORT>/api/enrichments \
     | python3 -c "import sys,json; e=json.load(sys.stdin)['enrichments']; \
        print(e['manual_overrides']['cognate_sets'].get('<conceptKey>'))"
   ```
   Note the response is **wrapped** as `{ "enrichments": { ... } }` — unwrap it.
   - If the API shows the expected groups → the data is correct and served.
   - If the API does **not** → the write didn't land (wrong key? wrong workspace?
     wrong layer — did you write top-level instead of `manual_overrides`?).
2. **Client refresh** — a loaded app holds an in-memory snapshot and does **not**
   poll. After any out-of-band write/migration/restore, **reload the app**. "API has
   it but the screen doesn't" always means a stale client.
3. **Compare cross-check** — `GET /api/compare/bundles` supplies grouping/forms but
   carries **no** cognate letters; the letters come only from `/api/enrichments`.
   Confirm the speaker ids in your groups match the bundle's speakers.

## Failure triage ("file looks right but Compare is blank")

Work in order: (1) stale client → reload; (2) wrong layer → it must be under
`manual_overrides`, not top-level; (3) wrong key → singleton own id vs group
`min(member_ids)`; legacy key still present → migrate (AMBIGUOUS needs manual triage);
(4) speaker id mismatch vs annotations; (5) wrong port/workspace; (6) endpoint shape
(`/api/enrichments` is wrapped; letters aren't in `/api/compare/bundles`). Full
explanation: `docs/data-persistence-model.md` → "Troubleshooting".
