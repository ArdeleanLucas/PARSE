# MC-346 — ORTH prompt suppression and lexeme rerun padding

## Objective
Suppress configured ORTH initial prompts by default on short-clip, concept-window, and full-file HF Whisper ORTH paths, while preserving explicit caller opt-in to prompt seeding and adding symmetric lexeme rerun padding.

## Scope
- Backend only.
- Implement the handoff at `.hermes/handoffs/parse-back-end/2026-05-07-orth-prompt-suppression.md`.
- Worktree: `/home/lucas/gh/worktrees/PARSE-rebuild/orth-prompt-suppression-be`.
- Branch: `fix/orth-prompt-suppression-backend`.

## Planned files
- `python/ai/providers/hf_whisper.py`
- `python/ai/providers/local_whisper.py`
- `python/ai/stt_pipeline.py`
- `python/server_routes/lexeme_rerun.py`
- `python/server_routes/annotate.py`
- `python/app/http/lexeme_rerun_handlers.py`
- `python/ai/providers/test_hf_whisper.py`
- `python/app/http/test_lexeme_rerun_handlers.py`
- `python/server_routes/test_lexeme_rerun_shims.py`
- `python/server_routes/test_annotate_concept_window_no_prompt.py`
- `python/server_routes/test_annotate_full_file_ortho_no_prompt.py`

## RED tests required
1. `test_transcribe_clip_initial_prompt_none_suppresses_config`
2. `test_transcribe_clip_initial_prompt_explicit_seeded`
3. `test_transcribe_segments_in_memory_initial_prompt_none_suppresses_config`
4. `test_transcribe_initial_prompt_none_suppresses_config_per_chunk`
5. `test_transcribe_clip_max_new_tokens_forwarded`
6. `test_pad_default_is_0_20`
7. `test_pad_explicit_0_0_no_padding`
8. `test_pad_explicit_0_5_widens`
9. `test_pad_invalid_value_400`
10. `test_pad_clamped_to_zero_at_start`
11. `test_run_ortho_interval_calls_renamed_helper`
12. Concept-window provider calls always pass `initial_prompt=None`.
13. Full-file ORTH provider call passes `initial_prompt=None`.

## Validation gates
- RED: targeted new tests fail against current main behavior before implementation.
- GREEN: same 13 tests pass after implementation.
- Full backend: `PYTHONPATH=python python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults'`.
- Focused backend: `PYTHONPATH=python python3 -m pytest -q python/ai/providers/test_hf_whisper.py python/app/http/test_lexeme_rerun_handlers.py python/server_routes/test_lexeme_rerun_shims.py python/server_routes/test_annotate_concept_window_no_prompt.py python/server_routes/test_annotate_full_file_ortho_no_prompt.py`.
- Static/build: `uvx ruff check python/ --select E9,F63,F7,F82`, `npx vitest run`, `./node_modules/.bin/tsc --noEmit`, `npm run build`, `git diff --check`.

## Completion criteria
- PR opened on `ArdeleanLucas/PARSE` with `--base main`.
- MC-346 referenced in commit and PR body.
- Fresh merge state and CI gate statuses reported.
- Explicitly confirm `transcribe_clip` defaults `initial_prompt=None` and callers must opt in to seed the config prompt.
