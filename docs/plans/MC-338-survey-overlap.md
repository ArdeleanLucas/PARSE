# MC-338 — Survey-overlap schema and Approach A UX

## Objective

Implement survey-overlap support from `.hermes/handoffs/parse-back-end/2026-05-07-survey-overlap-ui.md` in an isolated PARSE worktree, shipping durable backend schema support plus Approach A click-to-toggle UX when the resulting diff stays reviewable.

## Grounded current state

- `concepts.csv` currently has the canonical five-column schema: `id,concept_en,source_item,source_survey,custom_order` (`python/concept_source_item.py`).
- `/api/config` currently projects each concept as `{id,label,source_item?,source_survey?,custom_order?}` (`python/app/services/workspace_config.py`).
- The React concept list sorts by `concept.sourceItem` only (`src/ParseUI.tsx`, `src/lib/surveySort.ts`).
- `src/lib/conceptGrouping.ts` groups variants by `source_item`; raw annotation matching uses stable concept keys rather than emitted UI ids.
- The right drawer is split into `RightPanel`, `SpeakersSection`, and `AnnotateTabContent`; headers are not currently collapsible.
- `AnnotateView` owns the lexeme header and lower lexeme editor/metadata area.

## Schema decision

Use a workspace-root sidecar file named `survey-overlap.json` to avoid widening or destabilizing `concepts.csv` exports.

```json
{
  "version": 1,
  "color_coding_enabled": false,
  "surveys": {
    "klq": { "display_label": "KLQ", "display_color": "indigo" },
    "jbil": { "display_label": "JBIL", "display_color": "amber" }
  },
  "concept_survey_links": {
    "101": { "klq": "3.14", "jbil": "139" }
  },
  "speaker_choices": {
    "Saha01": { "101": "jbil" }
  }
}
```

Compatibility rules:

1. Existing `concepts.csv` rows remain readable and writable without the sidecar.
2. If the sidecar is missing, backend derives a single survey link from `source_survey/source_item` when both exist.
3. New sidecar data augments config output with plural `surveys`, global `survey_settings`, `survey_color_coding_enabled`, and `speaker_survey_choices` while preserving legacy `source_survey/source_item` fields.
4. Canonical `survey_id` values are normalized lowercase in the sidecar. Display labels are presentation-only.
5. CSV export/writers keep canonical ids and do not emit display labels.

## Backend implementation steps

1. Add `python/survey_overlap.py` with:
   - `load_survey_overlap_state(project_root)`
   - `save_survey_overlap_state(project_root, state)`
   - `project_concept_survey_links(row, sidecar)`
   - `resolve_survey_for_speaker(concept_id, speaker, state, fallback)`
   - `resolve_source_item_for_speaker(concept_id, speaker, state, fallback)`
   - stable natural-sort helpers for per-speaker source order.
2. Extend `build_workspace_frontend_config()` to load the sidecar and emit the plural schema + settings.
3. Add update helpers/routes if the frontend needs to persist settings/choices independently of full config writes.
4. Keep `concept_registry` and `concept_source_item` five-column writers unchanged except for tests proving forward/backward reads remain stable.
5. Add pytest coverage for:
   - missing sidecar backward read
   - sidecar forward projection with multi-survey links
   - per-speaker choice resolving sort source item
   - canonical survey ids preserved through CSV writers/export-facing rows

## Frontend implementation steps

1. Extend `ConceptEntry` / `Concept` / sidebar types with plural survey links and resolved per-speaker survey metadata.
2. Add small survey utilities for:
   - survey label/color resolution
   - colorless vs filled chip classes
   - per-speaker choice flipping
   - per-speaker source sort key
3. Add API client helpers for sidecar updates if backend exposes a dedicated endpoint.
4. Add `SurveyValuesSection` between Speakers and Timestamp Tools.
5. Make all drawer section headers collapsible; default expanded except Concept Tags.
6. Add Approach A chip to `ConceptSidebar`, lexeme header, and lower metadata block in `AnnotateView`.
7. Implement import-overlap modal only if current `SpeakerImport`/backend import flow exposes a clean pre-commit hook; otherwise keep backend payload contract documented and leave modal to parse-front-end follow-up.

## Test plan

Backend:

- `PYTHONPATH=python python3 -m pytest python/test_survey_overlap.py python/test_app_services_workspace_config.py python/test_concept_source_item.py python/test_concept_registry.py -q`
- `uvx ruff check python/ --select E9,F63,F7,F82`

Frontend:

- Targeted Vitest for chip render, toggle flip, inline editor save/cancel, master-toggle disable path, and resolved sort.
- Full `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `npm run build`

## Scope split rule

Default is one PR containing backend schema + Approach A frontend. Split frontend to parse-front-end only if import modal wiring or UI surface churn becomes too broad for a single backend-owned review.
