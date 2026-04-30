# MC-334 — Razhan SDH language token normalization and citations

## Objective
Fix ORTH/faster-whisper failures for Southern Kurdish annotation metadata (`sdh`) by translating only the provider-side Whisper language token to `fa`, matching the Razhan/DOLMA fine-tuning setup, while preserving `sdh` as PARSE's linguistic metadata.

## Scope
- Add a test-first `_normalize_whisper_language()` helper in `python/ai/providers/local_whisper.py`.
- Wire `transcribe`, `transcribe_window`, and `transcribe_clip` through the helper.
- Change the example ORTH default from `sd` to `fa` and cite Razhan/DOLMA sources.
- Add README and CLI help citations/rationale.

## Out of scope
- No annotation mutation.
- No generic ISO-639-3 mapping.
- No `stt.language: "ku"` config change; flag it as follow-up in the PR only.
- No frontend, Vitest, TypeScript, browser, screenshot, parse-run, or live dev-server validation.

## Validation
- RED/GREEN: `PYTHONPATH=python python3 -m pytest python/test_local_whisper_language_normalize.py -q`
- Full scoped pytest: `PYTHONPATH=python python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults'`
- Ruff: `uvx ruff check python/ --select E9,F63,F7,F82`
- Boot smoke: start `python python/server.py`, wait for listening line, send SIGTERM, confirm clean exit.
- Sanity greps from handoff.
