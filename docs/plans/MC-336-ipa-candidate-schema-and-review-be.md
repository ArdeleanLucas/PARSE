# MC-336 — IPA candidate schema and review backend surface

## Objective
Ship the backend review surface for wav2vec2 IPA candidates: structured candidate metadata, additive annotation sidecars, review-state routes, and OpenAPI coverage.

## Scope
- Add `Aligner.transcribe_window_structured(audio_16k)` as a thin wrapper over the existing wav2vec2 `transcribe_window` output.
- Preserve wav2vec2 output verbatim in `raw_ipa`; do not normalize, filter, rule-check, map, mask, or canonicalize it.
- Add optional annotation sidecars:
  - `ipa_candidates: dict[str, list[IpaCandidate]]`
  - `ipa_review: dict[str, IpaReviewState]`
- Add review routes:
  - `GET /api/annotations/<speaker>/ipa-candidates`
  - `PUT /api/annotations/<speaker>/ipa-review/<key>`
- Add OpenAPI entries for the two new paths.

## Test-first plan
1. Write RED tests for structured aligner output, annotation sidecar round-trip, review routes, candidate-producing IPA orchestration, and OpenAPI path coverage.
2. Confirm the tests fail on current `origin/main` behavior.
3. Implement the minimal backend code to satisfy those tests while preserving existing route and compute behavior.
4. Run targeted pytest, mandatory ruff, py_compile, and repo gates.
5. Push `feat/ipa-candidate-schema-and-review-be` and open the PR against `main` in `ArdeleanLucas/PARSE`.

## Out of scope
- Logit masks, IPA normalization, IPA rule checks, canonical mapping, inventory filters, second witness models, UI work, or promotion of `timing_basis` onto `AnnotationInterval`.
