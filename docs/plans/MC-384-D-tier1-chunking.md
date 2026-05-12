# MC-384-D — Tier-1 chunked ORTH transcription

## Objective
Prevent long-file ORTH Tier-1 OOMs by splitting the provider transcription call into adjacent duration chunks inside the ORTH subprocess path, while preserving Tier-2 forced alignment over the merged segment list.

## Scope
- `python/server_routes/annotate.py`
  - Add audio slice temp-WAV helper.
  - Add chunk error classifier.
  - Add full-mode chunked Tier-1 transcribe loop with cancellation checks between chunks, per-chunk error recording, temp cleanup, and `chunks` result metadata.
- `scripts/parse-run.sh`
  - Add `PARSE_ORTH_DEFAULT_CHUNK_MINUTES` default/documentation.
- `python/test_compute_speaker_ortho_chunking.py`
  - Add deterministic tests for short-path, long-path spans, timestamp merging, OOM/provider errors, cancellation, Tier-2 merged input, temp cleanup, env-var behavior, and Khan01-shape chunk count/performance/memory sanity.

## Dependency checks
- MC-384-A is required for `workers.audio_chunking` primitives.
- MC-384-C is required for `_compute_speaker_ortho_in_subprocess` and subprocess entry wiring.
- Both must be present on `origin/main` before implementation.

## Rules
- Do not run browser, screenshots, live runtime, or parse-run.
- Use pytest and ruff only.
- Preserve memory preflight and Tier-2 behavior.
- Default chunk size is `10` minutes; `0` disables chunking.
- Adjacent chunks only; no overlap.
- Clean all temp WAVs in `finally`.
- PR title: `[MC-384-D] feat(annotate): Tier-1 chunked ORTH transcribe for long files`.

## Completion criteria
- New chunking tests pass.
- Existing backend gate passes: `PYTHONPATH=python python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults'`.
- `uvx ruff check python/ --select E9,F63,F7,F82` clean.
- PR opened against `ArdeleanLucas/PARSE:main` with base verified as `main`.
