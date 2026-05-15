# MC-394-A — Populate cross-survey links from reference lexeme CSV

## Objective
Add a sidecar-only backend/script/MCP path that computes and optionally writes `survey-overlap.json::concept_survey_links` for single-word cross-survey duplicate concepts using a reference lexeme CSV (`source,id,lexeme`).

## Scope
- New shared core in `python/cross_survey_links.py`.
- New dry-run-by-default CLI in `scripts/populate_cross_survey_links.py`.
- New MCP/chat tool module in `python/ai/tools/cross_survey_link_tools.py` wired through `python/ai/chat_tools.py`.
- Regression fixtures/tests under `python/test_fixtures/cross_survey_links_workspace/`, `python/test_cross_survey_links.py`, `python/test_populate_cross_survey_links.py`, and `python/ai/test_cross_survey_link_tools.py`.

## Non-goals
- No `concepts.csv` mutation.
- No annotation/tag/enrichment rewrites.
- No live workspace execution against `/home/lucas/parse-workspace/`.
- No promote-primary behavior; that remains MC-394-B.

## Contract
- `compute_cross_survey_link_patch(workspace, reference_path, single_word_only=True)` returns:
  - `matched`: eligible concepts whose legacy primary matches the reference CSV.
  - `would_add`: concept-id keyed sidecar additions not already present.
  - `conflicts`: legacy primary mismatches or ambiguous reference rows skipped for safety.
  - `skipped_multiword`: concepts skipped when `single_word_only=True` because `concept_en` contains parentheses, commas, or whitespace.
- CLI is dry-run by default; `--apply` writes only `concept_survey_links` via `update_survey_overlap_state` and prints before/after sidecar diff.
- MCP tool name: `populate_cross_survey_links`; schema requires `referencePath` and `dryRun`; workspace root comes from `ParseChatTools.project_root`.

## Test plan
1. Write tests first and confirm RED on unmodified `origin/main`.
2. Targeted tests:
   - `PYTHONPATH=python python3 -m pytest -q python/test_cross_survey_links.py python/test_populate_cross_survey_links.py python/ai/test_cross_survey_link_tools.py`
3. Full backend sweep:
   - `PYTHONPATH=python python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults'`
4. Ruff gate:
   - `uvx ruff check python/ --select E9,F63,F7,F82`

## Completion criteria
- New tests demonstrate RED on `origin/main` and GREEN on branch.
- Backend sweep and ruff are clean.
- PR targets `ArdeleanLucas/PARSE`, base `main`, labels `MC-394` and `feat`.
