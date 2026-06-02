# PARSE Data Persistence & Keying Model

**Audience:** Technical users, corpus managers, power users running their own workspaces, and developers.

**Last updated:** 2026-06-02 (post PR #634 / MC-456-A; runtime read path + block-map + troubleshooting added in MC-456-B)

> This is the primary reference for *how data actually lives on disk*, how keys work, why migrations exist, and how to stay safe when managing or moving PARSE workspaces.

PARSE separates **raw per-speaker fieldwork records** from **comparative review decisions** and keeps a stable **identity layer** so that decisions survive UI changes, grouping experiments, and corpus growth.

## Core Files in a Workspace

A PARSE workspace (the directory you point the app or scripts at) typically contains:

| File / Dir                  | Purpose                                      | Keyed by?                          | Mutable?     | Notes |
|-----------------------------|----------------------------------------------|------------------------------------|--------------|-------|
| `concepts.csv`              | Master list of all concept rows (the "concepts table") | `id` (stable primary key)         | Low (append mostly) | Source of truth for identity. `source_item` + `source_survey` are for grouping/display only. |
| `parse-enrichments.json`    | All comparative + review state (flags, cognates, borrowings, merges, canonical choices, notes, etc.) | `Concept.key` (see below)         | High        | The main file affected by keying changes and migrations. See **The `parse-enrichments.json` Block Map** below for every block's shape and the manual-vs-automatic precedence. |
| `annotations/<Speaker>.json` (or `.parse.json`) | Per-speaker time-aligned tiers (ipa, ortho, concept, ...) | `concept_id` = raw csv `id`       | High        | The "source recording" of fieldwork. Concept tier uses underlying ids. |
| `parse-tags.json`           | Shared tag vocabulary + per-concept tag assignments | csv `id`s (never source keys)     | Medium      | Already id-namespaced. |
| `survey-overlap.json`, `source_index.json`, peaks, coarse transcripts, etc. | Supporting survey linking, search, visualization | Various                           | Varies      | Not decision state. |
| `audio/...`                 | Source audio and segments                    | Paths in annotations / transcripts| Low         | Referenced, not keyed by concept. |

**Rule of thumb:** If it is a *decision a reviewer or adjudicator made* ( "this speaker's form for 'ice' is cognate A with that other speaker", "flag this as borrowing", "choose variant B as canonical for this lexeme", "these two concepts are the same for my analysis"), it lives in or under `parse-enrichments.json` and is looked up by `Concept.key`.

## The Concept Keying Invariant (the heart of the design)

All decision storage **must** use a single, stable, globally-unique namespace that corresponds to real rows in `concepts.csv`.

- Every row in `concepts.csv` has an `id`. These `id`s are the canonical identities.
- `Concept.key` (what you see in the UI objects and what is used as dict keys in enrichments) is **always** one of these `id`s (for singletons: the row's own `id`; for display groups: the minimum `id` among the members of the group, i.e. `min(member_ids)`).

This matches the backend identity model introduced in #529 (`canonical_id = min(ids)` for merged same-(survey, item, label) rows).

**Why not key on `source_item` (the old way)?**

`source_item` is a *position in one survey's wordlist*. It is not an identity. Different surveys can reuse the same numbers or strings, and even within one survey bare integers (very common in JBIL-style lists) collide with other rows' `id` values. This produced exactly the silent data corruption (flags on "ice" affecting "to jump", etc.) that PR #634 fixed.

**Display grouping vs persistence key**

- The UI still groups rows that share `(source_survey, source_item)` for convenient "one row in the table = one elicitation concept" presentation (including variant letters A/B/C computed from interval order).
- The *persistence key* for that UI concept is the canonical min-id, not the source_item.
- Individual realizations inside a group still carry their original csv `id` in `variants[].conceptKey`.

This is implemented in `src/lib/conceptGrouping.ts` (`canonicalConceptKey`, `groupConceptEntries`) and mirrored in the Python migration logic (`_canonical_key`, `build_remap`).

## The `parse-enrichments.json` Block Map (shapes + precedence)

`parse-enrichments.json` holds two layers in one file: an **automatic** layer (computed by the enrichment / similarity pass) at the top level, and a **manual** layer (human adjudication) under `manual_overrides`. **For any decision type present in both layers, the manual layer wins** — readers resolve `manual_overrides.<block>[key]` first and fall back to the top-level block only if the manual entry is absent.

> **Consequence — a common source of "it looks empty":** in a workspace whose decisions are authored entirely by hand, the **top-level** `cognate_sets` / `borrowing_flags` are empty and all the real data lives under `manual_overrides`. Any report or tool that inspects the *top-level* block (for example, a summary that reports `len(cognate_sets)`) will read **0** even though the manual block is full. Always inspect `manual_overrides` to judge human decisions.

### Top-level (automatic layer + file metadata)

| Key | Shape | Meaning |
|---|---|---|
| `computed_at` | `string \| null` | When the automatic enrichment pass last ran. |
| `config` | `{ contact_languages, speakers_included, concepts_included, lexstat_threshold }` | Parameters of that automatic run. |
| `cognate_sets` | `{ conceptKey: { GROUP: [speakerId, …] } }` | **Auto-computed** cognate sets. Empty when cognates are authored by hand. |
| `similarity` | `{ conceptKey: { speakerId: { langCode: { score, has_reference_data } } } }` | Auto contact-language similarity scores. |
| `borrowing_flags` | `{ conceptKey: { speakerId: <value> } }` | Auto / legacy borrowing flags. |
| `manual_overrides` | object | The human-decision layer (below). |

Other top-level keys may be written by tools or pipelines (notes blocks, `*_applied_at` timestamps, source hashes, …). Treat any key your build does not recognise as **opaque metadata** — do not assume the keys above are the only ones, and preserve unknown keys on rewrite.

### `manual_overrides` (human layer — wins over the automatic layer)

| Block | Shape | Notes |
|---|---|---|
| `cognate_sets` | `{ conceptKey: { GROUP: [speakerId, …] } }` | `GROUP` is a single uppercase letter (`A`, `B`, `C`, …). A speaker listed under a letter is assigned to that cognate class for that concept. The displayed letter for a cell is the group whose speaker list contains that speaker. |
| `cognate_decisions` | `{ conceptKey: { decision: "accepted" \| "split" \| "merge", ts: <epoch_ms> } }` | Adjudication status of a concept's grouping. (Falls back to a legacy top-level `cognate_decisions` if the manual one is absent.) |
| `speaker_flags` | `{ conceptKey: { speakerId: true } }` | Per-speaker review flag; presence / `true` = flagged. |
| `borrowing_flags` | `{ conceptKey: { speakerId: { … } } }` | Per-speaker borrowing annotation (the value is an object describing the call). |
| `discarded_forms` | `{ conceptKey: { speakerId: <reason> } }` | A speaker's form excluded from comparison for that concept; the value is a short free-text reason. |
| `concept_merges` | `{ primaryConceptKey: [absorbedConceptKey, …] }` | Analyst-declared "these concepts are one." **Both** the map keys and the array values are concept keys — migrations re-key both. |
| `canonical_lexemes` | `{ bundleKey: { speakerId: { csv_row_id, survey_id, source_item, bucket_key, variant_label, realization_index, source } } }` | Which realization a speaker selected as canonical. **Keyed by a bundle key (`bundle:<slug>`), not a concept key.** |

### Key namespaces used in this file

- **`conceptKey`** — a `concepts.csv` `id`, minted per the keying invariant above (singleton → its own id; group → `min(member_ids)`). Used by every block except `canonical_lexemes`.
- **`bundleKey`** — `bundle:<slug>`; used only by `canonical_lexemes`.
- **`speakerId`** — the speaker identifier exactly as it appears in the annotations / speaker tier (and in annotation filenames). The inner maps and the `GROUP` membership lists key on this verbatim.
- **`GROUP`** — a single uppercase cognate-class letter, local to one concept.

All **concept-keyed** blocks are subject to the SAFE / AMBIGUOUS legacy-key promotion described below. `canonical_lexemes` (bundle-keyed) and tags (already id-namespaced) are not.

## How Data Flows at Runtime (Load + Promotion)

```mermaid
flowchart TD
    subgraph "On Disk (Workspace)"
        CSV[concepts.csv<br/>ids + source coords]
        ENR[parse-enrichments.json<br/>(may still have old source_item or 'source:...' keys for groups)]
        ANNS[annotations/*.json<br/>concept_id = raw csv ids]
    end

    CSV -->|read| REMAP[build_remap / build_remap_for_workspace<br/>computes old_key → canonical + SAFE vs AMBIGUOUS classification<br/>(cached by concepts.csv mtime in hot paths)]
    
    ENR -->|json load| PAYLOAD[raw dict]
    PAYLOAD -->|promote_safe_legacy_keys| PROMOTED[mutated in-memory dict<br/>SAFE legacy data moved/merged under canonical keys<br/>AMBIGUOUS data left exactly where it was]
    REMAP --> PROMOTED
    PROMOTED -->|scan_legacy_keys| WARNING[if any AMBIGUOUS legacy keys remain:<br/>log clear warning + exact migrator command]

    PROMOTED --> TOOLS[Python tools, exports, compare logic, MCP, AI chat tools, canonical lexemes, etc.<br/>(everything now sees canonical keys)]
    
    CSV -->|groupConceptEntries| INMEM_CONCEPTS[In-memory Concept[] for UI<br/>.key = canonical min id<br/>.variants[].conceptKey = underlying ids]
    INMEM_CONCEPTS --> UI[React Annotate / Compare<br/>decisions written back using .key]

    subgraph "Explicit Migration (when you choose)"
        MIGRATOR[python/scripts/migrate_concept_key_namespace.py --workspace ... [--execute]]
        MIGRATOR -->|uses same build_remap + promote logic| ENR
        MIGRATOR --> BACKUP[timestamped .bak-...-pre-key-namespace of original]
    end

    style PROMOTED fill:#e6ffe6,stroke:#090
    style WARNING fill:#fff3cd
    style MIGRATOR fill:#e6f3ff
```

**Important properties of the load-time promotion (`_promote_safe_legacy_concept_keys` called from `canonical_lexemes.load_enrichments`):**

- Completely automatic and invisible for normal use.
- Only ever promotes **SAFE** (historically unambiguous) legacy keys.
- **Never touches AMBIGUOUS** keys — those  (usually 1–9 per corpus) historical collision slots stay under the old key so the entanglement is not silently re-created or mis-attributed.
- Never writes to disk.
- Never raises — loading must succeed even if the promotion logic has a bug.
- Also rewrites values inside `concept_merges` arrays for promoted keys.
- After promotion, runs `scan_legacy_keys` and emits a warning *only* for remaining AMBIGUOUS entries, telling the user exactly what command to run.

This gives resilience: you can deploy new code that only understands canonical keys, and most of your old decision data will "just work" for the safe cases.

## How the Running App Reads This Data (Request Path)

The file on disk is the source of truth, but a running PARSE instance reaches it through the backend HTTP API. When "the file is correct but the screen is empty," the explanation is almost always on this path — so it is documented explicitly here.

- **Port.** The backend HTTP server listens on a configurable port (default `8766`; override with the `PARSE_PORT` environment variable). A deployment may bind something else — confirm the port the client is actually talking to.
- **No long-lived cache (server side).** The backend reads `parse-enrichments.json` **per request** and runs the in-memory SAFE-key promotion on each read before responding. A fresh API request therefore always reflects the current on-disk bytes.
- **Two endpoints feed the Compare view, and they carry different parts of the model:**
  - `GET /api/enrichments` → the whole enrichments file, **wrapped** as `{ "enrichments": { … } }`. The decision blocks (`manual_overrides.cognate_sets`, etc.) sit one level **inside** the `enrichments` key, not at the top of the response — consumers must unwrap.
  - `GET /api/compare/bundles` → `{ "bundles": [ … ], "identity_warnings": [ … ] }`. Each bundle carries grouping / identity / forms: `bundle_id`, `uid`, `label`, `row_ids` (underlying csv ids), `buckets` / `candidates` / `canonical` (per-speaker realization data), `speaker_choices`, `warnings`. It does **not** carry cognate letters, per-speaker flags, or borrowings.
- **The UI joins the two.** Grouping and forms come from `/api/compare/bundles`; the cognate letter / flag / similarity for each cell come from the enrichments blocks, looked up by concept key. The UI resolves that key as the **selected realization's** concept id (`variants[selectedIdx].conceptKey`, falling back to the group's canonical `key`); for a singleton concept this is simply the row's own csv id. The displayed cognate letter is the `GROUP` whose speaker list contains that speaker (manual layer first, automatic layer as fallback).
- **Clients hold an in-memory snapshot.** A loaded app does not poll the file or the API for changes. Any **out-of-band** rewrite of `parse-enrichments.json` — a migration `--execute`, an external authoring or batch-merge tool, a hand edit, or a restore-from-backup — is invisible to an already-open client until it reloads. The disk and the API can be entirely correct while a stale tab still shows the pre-write state.

> **Authoring outside the app.** Decision blocks may also be written by tooling that runs outside the PARSE process (batch authoring, import / merge, scripted back-fills). Such tools write the **same blocks under the same keys** and are bound by the same keying invariant; they should target `manual_overrides` for human decisions, and their writes are subject to the stale-client caveat above (reload to see them).

## Troubleshooting: the file is correct but the UI or a report disagrees

When a concept shows blank or wrong in Compare (or a count looks too low) yet the on-disk file looks right, work this list in order:

1. **Stale client snapshot — check this first.** The most common cause after any migration, restore, or out-of-band write. Reload the app fully. To localise the fault, query `GET /api/enrichments` directly: if the API returns the value but the screen does not, it is the client (reload); if the API also lacks it, continue below.
2. **Right layer / precedence.** Human decisions live under `manual_overrides.<block>`; the identically-named top-level block is the *automatic* layer and is often empty. A tool or report that reads the top-level block will under-count. Inspect `manual_overrides`.
3. **Right key.** Singleton → the row's own csv id; group → the canonical `min(member_ids)`. If the data sits under a legacy `source_item` or `source:<survey>:<item>` key, determine whether it is **SAFE** (auto-promoted at read time, so it still shows) or **AMBIGUOUS** (left in place on purpose — run the migrator dry-run; ambiguous keys read blank until manually triaged and re-keyed).
4. **Right speaker id.** The `GROUP` membership lists and the per-speaker maps key on the speaker id exactly as it appears in the annotations. A mismatch (case, suffix, a renamed speaker) reads as "no decision for this speaker."
5. **Right surface / right workspace.** Confirm the client is pointed at the backend port **and** the workspace directory you actually edited. A second instance on another port, or a backend rooted at a different workspace, reads a different file.
6. **Endpoint shape.** Querying the API by hand: `/api/enrichments` nests everything under the `enrichments` key, and cognate letters are **not** in `/api/compare/bundles`.

## The Migration Script (for cleaning the file + handling real ambiguity)

`python/scripts/migrate_concept_key_namespace.py --workspace /path/to/workspace [--execute] [--report report.json]`

- **Dry run (default)**: produces a full machine-readable report. Lists every group that would change key, the SAFE vs AMBIGUOUS classification, and for ambiguous ones the actual data (which speakers, which letters, etc.) that would be left behind.
- **--execute**: performs the on-disk rewrite.
  - First re-reads the file and aborts with a clear message if it changed since the initial load (optimistic concurrency — "stop the PARSE server first").
  - Writes a timestamped backup of the *original bytes*.
  - Applies the same re-keying logic (including `concept_merges` value rewriting).
  - Writes the result using the canonical atomic writer (proper formatting, trailing newline, etc.).
- Idempotent: running it again after a successful execute does nothing.
- The 9 (or N) ambiguous cases are deliberately *not* auto-moved. You get the report, you decide (often by looking at the speaker data in the UI or re-eliciting), then you can manually edit or use future tooling.

The script is the **only** thing that rewrites the on-disk `parse-enrichments.json` for these keys. Everything else (including the load promotion) works in memory.

## How Technical Users Are Informed

1. **The tool itself** — excellent `--help` and module docstring (design principles, exact blocks migrated, safe-vs-ambig contract, "stop the server" operational note, examples).

2. **Runtime warnings** — when you start the server, use MCP tools, run exports, etc., if ambiguous legacy keys are still present you get a clear `WARNING` with count and the exact command.

3. **This document** (and links from it) — the schematic + rationale + "what to do" guidance.

4. **The detailed historical design note** — `docs/reports/2026-06-02-concept-key-namespace-collision.md` (why the old scheme was broken, the full list of collisions for typical corpuses, verification numbers, the multi-phase thinking that led to the final shape).

5. **Executable specs / tests** (for developers and auditors):
   - `src/lib/conceptKeyNamespace.test.ts` (the "every key is a real csv id and they are unique" guard, with real collision examples).
   - `python/migration/test_concept_key_namespace.py` (promote vs ambig, merge cases, scan, cache behavior, end-to-end load promotion).

6. **Your corpus-specific notes** — e.g. `SK_SOURCE_DATA.md`, workspace READMEs, the various `.bak-*` files with timestamps tell the story of previous cleanups.

7. **Code comments + type names** — `canonicalConceptKey`, `build_remap`, `promote_safe_legacy_keys`, `CONCEPT_KEYED_BLOCKS`, the docstrings in `conceptGrouping.ts`.

## Practical Advice

- Treat `concepts.csv` `id` values as immutable identities. Renumbering or reusing ids will require manual or scripted repair of annotations and enrichments.
- Before a big upgrade or when handing a workspace to someone else, run the migrator in dry-run and keep the report.
- The load-time promotion means you can usually continue working even if you haven't run the migrator yet — but you should run it (on a backup first) to clean the file and deal with any ambiguous historical slots.
- For automated pipelines over many workspaces: the Python functions (`build_remap`, `promote_safe_legacy_keys`, `scan_legacy_keys`, `migrate`) are importable. You can call them directly and decide policy for the ambiguous cases.

## Related Reading

- The full story of this particular keying fix: `docs/reports/2026-06-02-concept-key-namespace-collision.md`
- Broader architecture: `docs/architecture.md`
- Developer onboarding: `docs/developer-guide.md`
- Other migration / hygiene scripts live in `python/migration/` (see also `concept_suffix_pollution.py` for the pattern this one follows).

If something in your data looks wrong after an upgrade, the first things to check are:
1. Did `concepts.csv` change in a way that affects ids or grouping?
2. Are there still legacy keys in `parse-enrichments.json`? (run the migrator dry-run)
3. Run the namespace invariant test or the migration tests against your data.

This model (stable id-based keys + display grouping separate + safe load-time promotion + explicit honest migration for collisions) is intended to make future evolution of the UI grouping or concept identity rules much less painful.
