# PARSE Data Persistence & Keying Model

**Audience:** Technical users, corpus managers, power users running their own workspaces, and developers.

**Last updated:** 2026-06-02 (post PR #634 / MC-456-A)

> This is the primary reference for *how data actually lives on disk*, how keys work, why migrations exist, and how to stay safe when managing or moving PARSE workspaces.

PARSE separates **raw per-speaker fieldwork records** from **comparative review decisions** and keeps a stable **identity layer** so that decisions survive UI changes, grouping experiments, and corpus growth.

## Core Files in a Workspace

A PARSE workspace (the directory you point the app or scripts at) typically contains:

| File / Dir                  | Purpose                                      | Keyed by?                          | Mutable?     | Notes |
|-----------------------------|----------------------------------------------|------------------------------------|--------------|-------|
| `concepts.csv`              | Master list of all concept rows (the "concepts table") | `id` (stable primary key)         | Low (append mostly) | Source of truth for identity. `source_item` + `source_survey` are for grouping/display only. |
| `parse-enrichments.json`    | All comparative + review state (flags, cognates, borrowings, merges, canonical choices, notes, etc.) | `Concept.key` (see below)         | High        | The main file affected by keying changes and migrations. |
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
