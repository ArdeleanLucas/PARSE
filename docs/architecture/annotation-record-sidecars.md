# AnnotationRecord Sidecars

## What an AnnotationRecord sidecar is

An `AnnotationRecord` sidecar is a top-level field on the per-speaker annotation record that is deliberately **not** stored inside `tiers`. Tiers remain the TextGrid-shaped interval surface (`ipa`, `ortho`, `concept`, `speaker`, and related interval tiers); sidecars carry PARSE-only review and workflow metadata that has no native Praat/TextGrid slot.

That separation is intentional: a record can round-trip through Praat/TextGrid-oriented data without pretending that confirmation state, review state, or tag membership is a phonetic/orthographic tier. In code, the TypeScript record shape lives in `src/api/types.ts`, while the persistence and normalization path is owned by `python/server_routes/annotate.py` before records are written under `annotations/<Speaker>.json` / `annotations/<Speaker>.parse.json` in the workspace.

Sidecar rules for this codebase:

- Sidecars are keyed by stable concept ids or review ids; do **not** normalize concept ids by trimming, lowercasing, or coercing them into numeric identifiers.
- Sidecars must be additive and optional on read so old annotation records remain loadable.
- Server normalization may defensively drop malformed entries, but must not mutate tier timestamps while doing so.
- TextGrid/Praat export/import should preserve sidecars via the PARSE annotation JSON record, not by trying to encode them inside TextGrid tiers.

## Current sidecars

| Sidecar | Shape | Owner / source of truth | Purpose | Merge-cycle status |
|---|---|---|---|---|
| `confirmed_anchors` | `Record<string, ConfirmedAnchor>` keyed by concept id | `src/api/types.ts`; normalized in `python/server_routes/annotate.py` | User-confirmed lexeme time ranges. These strengthen cross-speaker anchor discovery, re-STT priors, forced-alignment training data, and future audio-similarity discovery without living inside `tiers`. | Already present on `main`. |
| `ipa_review` | `Record<string, IpaReviewState>` keyed by IPA candidate/review id | `src/api/types.ts`; normalized in `python/server_routes/annotate.py` | IPA review status and candidate acceptance metadata. It is review state, not a phonetic interval tier. | Already present on `main`. |
| `concept_tags` | `Record<string, string[]>` keyed by concept id; values are tag ids | Companion FE PR adds the TypeScript field in `src/api/types.ts`; companion BE PR adds persistence/normalization in `python/server_routes/annotate.py` | Per-speaker tag membership for concepts. This replaces project-global tag membership for confirmation state so confirming Saha01 concept `1` does not mark Khan04 concept `1` as confirmed. | New in the 2026-05-04 concept-tag PR cycle. |

`concept_tags` is a sidecar for the same reason `confirmed_anchors` is: the field describes PARSE review state attached to a speaker/concept pair, not an interval tier that belongs in TextGrid. Keeping it top-level also makes the two confirmation axes explicit: `concept_tags[concept_id]` records transcription/tag membership such as `confirmed`, while `confirmed_anchors[concept_id]` records boundary confirmation.