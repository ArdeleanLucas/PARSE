# MC-332 — Audition parser no-row-left-behind

## Objective

Stop silently dropping valid Audition cue rows during speaker onboarding. Every row with a non-empty `Name` and parseable/importable timing must reach PARSE, including square-bracket section IDs (`[N.M]-`) and bare phrases with no parseable prefix.

## Scope

Backend-only changes:

1. `python/lexeme_notes.py`
   - Accept `[N.M]-` / `[N.M.K]-` bracketed IDs alongside existing `(N.M)-` and plain integer IDs.
   - Preserve existing paren/plain behavior.
   - Treat non-empty no-prefix names as accepted bare rows with `concept_id=""`, verbatim `remainder`, and no variant stripping.

2. `python/server_routes/media.py`
   - Remove the resolver gate that skips rows with empty `audition_prefix`.
   - Synthesize `audition_prefix="row_<import_index>"` for bare rows.
   - Keep concept ids integer-only and `audition_prefix` opaque.

3. Tests/docs
   - Extend `python/test_lexeme_notes.py` for bracket, bare, and malformed-paren rows.
   - Extend `python/test_server_onboard_speaker.py` for no-drop import behavior and integer-only concepts.
   - Update `docs/runtime/audition-csv-import.md` with the widened import contract.

## Out of scope

- No frontend changes.
- No interval shape changes.
- No STT, IPA, BND, forced-align, tagging, or filtering work.
- No browser/preview/parse-run validation.

## Acceptance

- Bracket rows retain their observed prefix in `audition_prefix`.
- Bare or malformed-prefix rows are imported with synthetic `row_<import_index>` audition prefixes.
- `import_index` remains the physical cue-row index.
- `concepts.csv` registry growth is allowed, but ids remain integers.
- Expected field result after merge: Saha01 472→497, Mand01 496→519, other four thesis speakers unchanged.

## Validation plan

1. RED: targeted pytest for the new parser/resolver behavior fails on current main.
2. GREEN: implement minimal parser/resolver changes.
3. Run:
   - `pytest python/test_lexeme_notes.py python/test_server_onboard_speaker.py python/test_audition_row_index_join.py -q`
   - `pytest -q`
   - `npm run check`
   - `npm run build`
   - `git diff --check`
4. Commit with MC-332, push branch, open PR on `ArdeleanLucas/PARSE`.
