# MC-341 — Import-overlap pre-commit seam

## Objective

Add a backend pre-commit preview seam for speaker onboarding imports so the frontend can show survey-overlap choices before `/api/onboard/speaker` writes uploaded files or starts the onboarding job.

## Grounded current flow

- HTTP entrypoint: `python/server.py::_dispatch_api_post()` routes `POST /api/onboard/speaker` to `python/server_routes/media.py::_api_post_onboard_speaker()`.
- HTTP upload behavior today: `_api_post_onboard_speaker()` validates multipart form data, normalizes `speaker_id`, requires an audio upload, accepts optional `csv` and `commentsCsv`, writes the upload under `audio/original/<Speaker>/`, creates an `onboard:speaker` job, and launches `_run_onboard_speaker_job()` in a background thread.
- Commit worker: `_run_onboard_speaker_job()` creates the annotation, updates `source_index.json`, registers `project.json`, merges normal `concepts.csv` uploads through `_parse_concepts_csv()` / `_merge_concepts_into_root_csv()`, and handles Audition cue CSV imports through `_resolve_audition_concepts()` and annotation append helpers.
- Survey-overlap support from PR #291: `python/survey_overlap.py` owns `survey-overlap.json`, including `speaker_choices`, `normalize_survey_id()`, and `update_survey_overlap_state()` merge semantics.
- MCP-side tools: `python/ai/tools/speaker_import_tools.py` still delegate first-time onboarding to the HTTP callback path via `server._run_onboard_speaker_job()`; this slice only adds the HTTP pre-commit seam and the worker-side `survey_choices` persistence hook.

## Delivery decision

PR #291 is still open and contains the `survey_overlap.py` sidecar module that this seam depends on, so MC-341 is implemented as a follow-up commit on the existing `feat/mc-338-survey-overlap` PR branch after rebasing that branch onto current `origin/main`. That keeps the new API contract adjacent to the sidecar schema and avoids a duplicate stacked PR carrying PR #291's frontend/backend diff.

## Implementation plan

1. Write RED tests in `python/test_server_onboard_speaker.py` for:
   - `POST /api/onboard/speaker?preview=1` returns overlap concepts and writes no files.
   - Preview rejects malformed uploads with the same validation path as commit.
   - Commit without `survey_choices` remains backward compatible.
   - Commit with `survey_choices` passes choices into the worker and writes `survey-overlap.json` after `concepts.csv` merge.
   - Preview + commit cycle returns N overlaps and persists N chosen surveys.
2. Add focused helpers in `python/server_routes/media.py`:
   - query/body preview detection using `self._request_query_params()` plus optional multipart `preview` field.
   - upload validation that can read multipart bytes without writing in preview mode.
   - overlap preview construction over existing workspace `concepts.csv` plus incoming normal concepts CSV or Audition-derived concepts.
   - survey-choice extraction from multipart JSON field `survey_choices` or nested `survey_choices[Speaker]` payload.
3. Extend `_run_onboard_speaker_job()` with an optional `survey_choices` argument and call `update_survey_overlap_state(project_root, {"speaker_choices": {speaker: choices}})` after the concepts merge/import path has finished.
4. Update `python/external_api/openapi.py` for the preview query flag and optional `survey_choices` multipart field.
5. Validate with targeted onboarding/survey/OpenAPI tests first, then backend gates, ruff, frontend gates if needed, and `git diff --check`.

## Contract for parse-front-end

Preview request:

```http
POST /api/onboard/speaker?preview=1
Content-Type: multipart/form-data

speaker_id=<Speaker>
audio=<file>
csv=<optional concepts/Audition CSV>
commentsCsv=<optional comments CSV>
```

Preview response:

```json
{
  "preview": true,
  "speaker": "Saha01",
  "overlap_concepts": [
    {
      "concept_id": "salt",
      "concept_en": "salt",
      "surveys": { "klq": "3.14", "jbil": "139" },
      "auto_detected": "jbil"
    }
  ]
}
```

Commit request accepts optional multipart field `survey_choices` as JSON:

```json
{
  "Saha01": { "salt": "jbil", "snow": "jbil" }
}
```

A bare per-speaker map is also accepted for the importing speaker:

```json
{ "salt": "jbil", "snow": "jbil" }
```

## Out of scope

- Frontend modal wiring.
- Changing `survey-overlap.json` schema.
- Survey-ID renaming or display-label semantics.
- Heuristics beyond incoming `source_survey` and existing workspace survey links.
