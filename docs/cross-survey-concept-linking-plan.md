# Cross-survey concept linking plan

This is the pre-research implementation contract for linking one PARSE concept to multiple survey inventories before backend and frontend implementation. It is docs-only: it changes no runtime behavior.

## 1. Current state

PARSE already has most of the storage and display primitives for multi-survey concepts, but import-time writes still collapse each concept to one primary `source_survey`/`source_item` pair unless a sidecar link is already present.

### Frontend API shape

`src/api/types.ts:171-197` defines the sidecar and concept-entry shape that the UI can already consume:

```ts
export type ConceptSurveyLinks = Record<string, string>;
export type ConceptSurveyLinksByConcept = Record<string, ConceptSurveyLinks>;
export type SpeakerSurveyChoices = Record<string, Record<string, string>>;
```

```ts
  concept_survey_links: ConceptSurveyLinksByConcept;
  speaker_choices: SpeakerSurveyChoices;
}
```

```ts
export interface ConceptEntry {
  id: string;
  label: string;
```

`src/lib/speakerForm.ts:5-24` carries the same `surveys` map into the sidebar's runtime concept model:

```ts
export interface ConceptVariant {
  conceptKey: string;
  conceptEn: string;
  variantLabel: string;
  surveys?: ConceptSurveyLinks;
```

```ts
  sourceSurvey?: string;
  customOrder?: number;
  surveys?: ConceptSurveyLinks;
```

### Concept registry and import allocation

`python/concept_registry.py:12-20` indexes concepts by a case-folded, whitespace-collapsed label key:

```py
@dataclass
class ConceptRegistry:
    label_to_id: dict[str, str]
```

```py
def concept_label_key(label: str) -> str:
    return " ".join(str(label or "").strip().split()).casefold()
```

`python/concept_registry.py:71-83` resolves existing concepts by that key, otherwise allocates a new integer id:

```py
def resolve_or_allocate_concept_id(registry: ConceptRegistry, label: str) -> tuple[str, bool]:
    clean_label = str(label or "").strip()
    key = concept_label_key(clean_label)
```

```py
    registry.raw_rows.append({"id": concept_id, "concept_en": clean_label, "source_item": "", "source_survey": "", "custom_order": ""})
    return concept_id, True
```

The Audition import path already parses cue labels and source metadata, but it does not persist a second survey link when the same gloss appears from a different survey. `python/server_routes/media.py:226-245`:

```py
        cid, _was_allocated = resolve_or_allocate_concept_id(registry, label)
        source_item, source_survey = source_item_from_audition_row(row)
        resolved.append({
```

```py
            'source_item': source_item,
            'source_survey': source_survey,
        })
```

### Survey-overlap sidecar

`python/survey_overlap.py:46-53` defines the durable JSON shape:

```py
def _default_state() -> SurveyOverlapState:
    return {
        "version": 1,
```

```py
        "concept_survey_links": {},
        "speaker_choices": {},
    }
```

`python/survey_overlap.py:78-94` normalizes `concept_survey_links` as `concept_id -> survey_id -> source_item`:

```py
def _clean_links(raw: object) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
```

```py
            if sid and item:
                clean_links[sid] = item
```

`python/survey_overlap.py:183-191` already merges incoming sidecar patches rather than replacing the whole file:

```py
    if isinstance(patch.get("concept_survey_links"), Mapping):
        incoming_links = _clean_links(patch.get("concept_survey_links"))
        for concept_id, links in incoming_links.items():
```

`python/survey_overlap.py:194-209` makes legacy `source_survey/source_item` and sidecar links appear as one map to the frontend:

```py
    legacy_item = row_value(row, "source_item", "survey_item")
    legacy_survey = normalize_survey_id(row_value(row, "source_survey"))
    if legacy_item and legacy_survey:
```

```py
            if sid and item:
                links[sid] = item
```

`python/app/services/workspace_config.py:45-50` and `:67-70` load the sidecar into `/api/config` concepts:

```py
    survey_state = load_survey_overlap_state(project_root)
    used_survey_ids: set[str] = set()
```

```py
        links = concept_survey_links_for_row(row, survey_state)
        if links:
            entry["surveys"] = links
```

### concepts.csv writer and CSV import endpoint

`python/concept_source_item.py:11-17` pins `concepts.csv` to the five-column durable schema:

```py
CONCEPT_FIELDNAMES: tuple[str, ...] = (
    "id",
    "concept_en",
```

```py
    "source_survey",
    "custom_order",
)
```

`python/concept_source_item.py:31-48` already recognizes KLQ, EXT, and JBIL cue-name formats:

```py
def parse_cue_name(cue: str) -> tuple[str | None, str | None, str]:
    """Return ``(source_item, source_survey, label)`` for an Audition cue name.
```

```py
        if match:
            return match.group(1), survey, match.group(2).strip()
```

`python/concept_source_item.py:93-112` writes the normalized five-column rows:

```py
def write_concepts_csv_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
```

```py
        writer = csv.DictWriter(handle, fieldnames=list(CONCEPT_FIELDNAMES))
        writer.writeheader()
```

The concepts-import route is `POST /api/concepts/import`. `python/server.py:1534-1536` dispatches it:

```py
        if request_path == "/api/concepts/import":
            self._api_post_concepts_import()
            return
```

`python/app/http/project_config_handlers.py:93-103` says the multipart file field is `csv`:

```py
def _read_csv_text(form: cgi.FieldStorage) -> tuple[str, str]:
    csv_item = form["csv"] if "csv" in form else None
```

`python/app/http/project_config_handlers.py:158-214` currently reports exact-label/id matches and additions only:

```py
    matched = 0
    added = 0
    for up in upload_rows:
```

```py
            "matched": matched,
            "added": added,
            "total": len(existing),
```

`src/api/contracts/enrichments-tags-notes-imports.ts:24-41` is the existing frontend caller:

```ts
export async function importConceptsCsv(
  file: File,
  mode: "merge" | "replace" = "merge",
```

```ts
    response = await fetch("/api/concepts/import", { method: "POST", body: form });
```

Note for implementation: new API clients must go through `src/api/client.ts` / `src/api/contracts/*`; this existing helper is pre-rule debt and should be touched only if the implementation PR owns that cleanup.

### ConceptSidebar affordances

`src/components/parse/ConceptSidebar.tsx:52-57` already accepts settings, speaker choices, and a per-speaker choice callback:

```tsx
  surveySettings?: SurveySettingsMap;
  speakerSurveyChoices?: SpeakerSurveyChoices;
  surveyColorCodingEnabled?: boolean;
  onSurveyChoiceChange?: (speaker: string, conceptKey: string, surveyId: string) => void;
```

`src/components/parse/ConceptSidebar.tsx:257-272` resolves current and next survey choices:

```tsx
          const resolvedSurvey = resolveConceptSurvey(surveyConcept, activeSpeaker, speakerSurveyChoices, surveySettings);
          const resolvedSurveyLabel = surveyLabelFor(resolvedSurvey.surveyId, surveySettings);
```

```tsx
          const canFlipSurveyBadge = !!(activeSpeaker && onSurveyChoiceChange && nextSurveyId);
```

`src/components/parse/ConceptSidebar.tsx:331-340` renders the clickable badge when there is a next survey:

```tsx
                {canFlipSurveyBadge ? (
                  <button
                    type="button"
```

```tsx
                    {badge}
                  </button>
```

`src/components/parse/ConceptSidebar.tsx:397-434` has the current context menu with merge, duplicate, and unmerge actions:

```tsx
      {contextMenu && (
        <div
          ref={menuRef}
```

```tsx
            Merge with…
          </button>
```

## 2. Source-data shape

The KLQ Audition exports are tab-delimited files with `.csv` suffixes. The JBIL source is a comma CSV wordlist with `JBIL` and `Eng` columns. The examples below are direct source lines from Lucas's local data.

### KLQ-style Audition cue samples

| Source file:line | Raw cue name | Matching implication |
|---|---|---|
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Kalh01 process/Kalh01.csv:2` | `(1.1)- hair (collective)` | Parenthetical clarifier must not auto-merge into plain `hair`. |
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Qasr01 process/Qasr01.csv:2` | `(1.2)- forehead` | Same gloss appears in other KLQ speakers. |
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Qasr01 process/Qasr01.csv:5` | `(1.5)- nose` | Cross-survey candidate for JBIL `34,nose`. |
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Kalh01 process/Kalh01.csv:5` | `(1.4)- eyebrow A` | Variant suffix `A` should collapse for matching. |
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Kalh01 process/Kalh01.csv:6` | `(1.4)- eyebrow B` | Variant suffix `B` should collapse for matching. |
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Saha01 process/Saha01.csv:12` | `(2.3)- father (vocative)` | Parenthetical `vocative` should remain strict in v1. |
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Saha01 process/Saha01.csv:13` | `(2.4)- mother (vocative)` | Confirms parenthetical pattern repeats across kinship rows. |
| `/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Qasr01 process/Qasr01.csv:17` | `(2.7)- daughter, girl` | Comma alternatives are ambiguous; no any-token auto-link in v1. |

### JBIL wordlist samples

| Source file:line | Row | Cross-survey note |
|---|---|---|
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:20` | `1,one,...` | Flat numeric source item, not KLQ section numbering. |
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:50` | `31,head,...` | JBIL id `31`, gloss `head`. |
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:51` | `32,hair,...` | Fuzzy candidate for KLQ `hair (collective)`, not strict auto-link. |
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:52` | `33,eye,...` | Plain gloss. |
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:53` | `34,nose,...` | Exact strict match for KLQ `(1.5)- nose` after prefix strip. |
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:89` | `70,girl,...` | Comma-alternative candidate for KLQ `daughter, girl`, not strict auto-link. |
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:90` | `71,daughter,...` | Another comma-alternative candidate for KLQ `daughter, girl`. |
| `/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:138` | `119,stone,...` | Plain gloss useful for control cases. |

Concrete cross-survey examples:

- Strict auto-link: KLQ `(1.5)- nose` -> canonical gloss `nose`; JBIL `34,nose` -> canonical gloss `nose`.
- Fuzzy review only: KLQ `(1.1)- hair (collective)` -> `hair (collective)`; JBIL `32,hair` -> `hair`.
- Fuzzy review only: KLQ `(2.7)- daughter, girl`; JBIL `70,girl` and `71,daughter`.

## 3. Matching algorithm

### Chosen v1 canonicalization

Define a shared backend helper, e.g. `canonical_survey_gloss(raw: str) -> str`, and use the same semantics from import-time linking and migration. Inputs should be concept labels after existing cue parsing when possible; raw cue strings are allowed for safety.

1. Trim outer whitespace.
2. Strip a leading KLQ-style source prefix: `^\s*\(\s*\d+(?:\.\d+)*\s*\)\s*[-–—]?\s*`.
3. If the input is a raw JBIL-style Audition cue (`32- hair`), reuse the existing `parse_cue_name()` behavior rather than adding a second regex.
4. Strip one trailing variant suffix matching `\s+[A-Z]$` after prefix removal (`eyebrow A` -> `eyebrow`).
5. Lowercase with `casefold()` and collapse internal whitespace to one space.
6. Keep all parenthetical clarifiers in the canonical key.
7. Treat comma-separated alternatives as one canonical string.

Pseudocode:

```py
def canonical_survey_gloss(raw: object) -> str:
    text = str(raw or "").strip()
    _source_item, _source_survey, label = parse_cue_name(text)
    text = label.strip()
    text = re.sub(r"^\(\s*\d+(?:\.\d+)*\s*\)\s*[-–—]?\s*", "", text)
    text = re.sub(r"\s+[A-Z]$", "", text)
    return " ".join(text.split()).casefold()
```

### Decision points and rejected alternatives

- **Parenthetical clarifiers:** choose strict auto-linking. Keep `(collective)`, `(vocative)`, and similar clarifiers in the canonical key. Rejected alternative: strip parentheticals and auto-merge; this would merge `hair` with `hair (collective)` and kinship/vocative rows without review. Safer behavior: emit fuzzy candidates where a parenthetical-stripped key matches, and show them in a review queue.
- **Comma alternatives:** choose whole-string matching for v1. Rejected alternative: split on comma and auto-link if any token matches. That would auto-link `daughter, girl` to both JBIL `girl` and `daughter`, creating non-deterministic concept lineage. Safer behavior: include comma token matches in fuzzy candidates only.
- **Numeric source-item matching:** reject. KLQ `(1.5)` and JBIL `34` are different survey coordinate systems; numbers cannot be used across surveys.
- **Overwrite-only import:** reject. The current five-column row can record one legacy survey pair; multi-survey correctness requires `survey-overlap.json` updates, not only `source_survey/source_item` overwrites.

Fuzzy candidate generation should be deterministic and non-writing. Candidate classes:

- `parenthetical_stripped_match`: `hair (collective)` vs `hair`.
- `comma_token_match`: `daughter, girl` vs `girl` or `daughter`.
- `variant_suffix_match`: exact after suffix strip, already accepted for auto-link unless other ambiguity exists.

## 4. API contract

### 4a. Import-time auto-linking in `POST /api/concepts/import`

Path and request remain unchanged:

- Method/path: `POST /api/concepts/import`.
- Content type: `multipart/form-data`.
- Fields:
  - `csv`: uploaded UTF-8 CSV file, current required field name.
  - `mode`: optional `merge` or `replace`, default `merge`.
- Supported row fields remain `id`, `concept_en`, `source_item`, `source_survey`, `custom_order`.

New behavior:

1. Build the existing id index as today.
2. Build a gloss index using `canonical_survey_gloss(existing_row["concept_en"])`.
3. For each uploaded row, resolve in this order:
   - exact normalized id match, if supplied;
   - exact canonical gloss match;
   - allocate/create only if no id or gloss match exists.
4. If the incoming row has non-empty `source_survey` and `source_item`, normalize `source_survey` with the existing `normalize_survey_id()` and update `survey-overlap.json`:

```json
{
  "concept_survey_links": {
    "<concept_id>": {
      "<survey_id>": "<source_item>"
    }
  }
}
```

5. When a row links to an existing concept via canonical gloss, do **not** allocate a second concept id. Preserve the existing row's primary `source_survey/source_item` unless those columns are empty; put additional survey coordinates into the sidecar.
6. Created concepts keep the current five-column row behavior and should also seed `concept_survey_links[concept_id][survey_id]` when survey metadata exists, so the UI has one uniform read path.
7. `replace` mode may still clear legacy `source_*` columns as it does today, but it must not delete `survey-overlap.json` links unless the request explicitly adds a future reset flag. This avoids destructive cross-survey unlinking during CSV refreshes.

Response: keep current fields and add a deterministic per-survey summary.

```ts
interface ImportConceptsResultV2 {
  ok: true;
  matched: number;        // backward-compatible existing exact/id/gloss matched count
  added: number;          // backward-compatible created concept count
  total: number;
  mode: "merge" | "replace";
  link_summary: Record<string, {
    linked_count: number;   // existing concept got this survey link
    created_count: number;  // new concept seeded this survey link
    updated_count: number;  // existing sidecar link changed source_item
    skipped_count: number;  // row had no usable source_survey/source_item
  }>;
  fuzzy_candidates: Array<{
    incoming_label: string;
    candidate_concept_id: string;
    candidate_label: string;
    reason: "parenthetical_stripped_match" | "comma_token_match";
  }>;
}
```

`fuzzy_candidates` are informational only and never write links automatically.

### 4b. Manual relabel endpoint

Add a concept-scoped endpoint for deliberate user edits:

- `POST /api/concepts/{conceptId}/survey-links`
- `DELETE /api/concepts/{conceptId}/survey-links`

Request body:

```ts
interface ConceptSurveyLinkMutation {
  survey_id: string;
  source_item: string;
}
```

POST semantics:

- Normalize `survey_id` with the existing survey id normalizer.
- Require non-empty `survey_id` and `source_item`.
- Require `conceptId` to exist in `concepts.csv`; otherwise `404`.
- Persist `concept_survey_links[conceptId][survey_id] = source_item` to `survey-overlap.json`.
- Return the updated `ConceptEntry`, including `surveys`.

DELETE semantics:

- Require non-empty `survey_id`; `source_item` may be used as an optimistic guard if present.
- If `source_item` is present and differs from the current link, return `409` rather than deleting a different link.
- Remove `concept_survey_links[conceptId][survey_id]` from `survey-overlap.json`; if the concept's link map becomes empty, remove that sidecar concept key.
- Do not mutate the legacy five-column row unless a future explicit migration requires it.
- Return the updated `ConceptEntry`.

Suggested response shape:

```ts
interface ConceptSurveyLinkResponse {
  ok: true;
  concept: ConceptEntry;
  survey_overlap: SurveyOverlapState;
}
```

Backend may alternatively return the bare `ConceptEntry` if frontend API helpers wrap it; implementation PR must choose one shape and pin it in tests and OpenAPI.

## 5. Frontend changes

All new API calls must go through `src/api/client.ts` and a concrete `src/api/contracts/*` helper; no new component-level bare `fetch()`.

ConceptSidebar scope:

1. Broaden the clickable badge predicate to “concept has at least two survey links and an active speaker/callback exists.” The current `canFlipSurveyBadge` already depends on `nextSurveyId`; implementation should make the multi-survey intent obvious and keep single-survey badges non-clickable.
2. Cycle order is a stable sort of normalized `survey_id`s, matching `surveyChoiceKeysForConcept()` / `Object.keys(...).sort()` behavior from `src/lib/surveyOverlap.ts:84-85`.
3. Keep choices per speaker. The UI must continue to write through the existing `speaker_choices` mechanism for viewing/elicitation choice; this is not a global survey toggle.
4. Add exactly one context-menu item: `Change survey ID…`.
5. The item opens an inline editor inside the existing menu/popover area, not a modal. Fields:
   - `survey_id` select populated from existing configured survey ids plus any survey ids on the concept.
   - `source_item` text input.
   - Save button calls the new POST endpoint.
   - Optional remove affordance calls DELETE for the selected survey id.
6. Add a subtle underline-on-hover class to multi-survey clickable badges so they read as clickable without adding iconography or emoji.

Current test anchors:

- `src/components/parse/ConceptSidebar.test.tsx:335-374` already proves per-speaker survey pills and `onSurveyChoiceChange`.
- `src/components/parse/ConceptSidebar.test.tsx:377-417` already proves clicking the visible survey badge flips to the next survey.
- `src/components/parse/ConceptSidebar.test.tsx:301-332` already proves the context-menu action pattern.

## 6. Migration

Already-imported workspaces can contain split concepts that represent the same cross-survey gloss. Add a dry-run-first endpoint:

- Method/path: `POST /api/concepts/relink-by-gloss`.
- Default request: `{ "apply": false }`.
- Apply request: `{ "apply": true, "accepted_groups": [...] }` after frontend confirmation.
- Matching algorithm: strict `canonical_survey_gloss()` from section 3.
- Fuzzy candidates: report only; never apply automatically.

Dry-run response:

```ts
interface RelinkByGlossDryRunResponse {
  ok: true;
  applied: false;
  algorithm: "canonical_survey_gloss:v1-strict";
  groups: Array<{
    canonical_gloss: string;
    keep_concept_id: string;
    merge_concept_ids: string[];
    labels: Record<string, string>;
    links_by_survey: Record<string, string>;
    source_rows: Array<{ concept_id: string; concept_en: string; source_survey?: string; source_item?: string }>;
  }>;
  fuzzy_candidates: Array<{
    incoming_label: string;
    candidate_label: string;
    reason: "parenthetical_stripped_match" | "comma_token_match";
  }>;
}
```

Apply semantics:

1. Only apply groups the user confirmed in the frontend review list.
2. Choose `keep_concept_id` as the lowest numeric concept id in the strict group unless the dry run marks another id because it already has annotations; the rule must be deterministic and shown in the dry-run report.
3. Move all source links into `survey-overlap.json` under `keep_concept_id`.
4. Rewrite `concepts.csv` so duplicate concept rows in the accepted group are retired or merged into the kept row.
5. Update references from retired concept ids to `keep_concept_id` across workspace data that stores concept ids, especially `annotations/*.parse.json`, legacy `annotations/*.json` where still mirrored, `parse-enrichments.json`, and `parse-tags.json` if present. The implementation must not orphan existing lexeme intervals.
6. Write a backup before mutation, e.g. `backups/relink-by-gloss-<timestamp>/`, and return backup paths.
7. Idempotency requirement: running the same dry run after a successful apply returns no accepted strict groups to apply.

Frontend migration flow:

1. User opens a reconciliation action for the active workspace.
2. FE calls `POST /api/concepts/relink-by-gloss` with `{ apply: false }`.
3. FE shows a confirmation list: kept id, merged ids, labels, survey links, and fuzzy candidates separately.
4. FE calls `{ apply: true, accepted_groups: [...] }` only after user confirmation.
5. FE reloads config and annotations after apply so the sidebar and current lexeme state reflect merged ids.

## 7. Test surface and LoC estimate

### Existing tests to extend

Backend:

- `python/test_app_http_project_config_handlers.py:118-148` verifies `/api/concepts/import` exact-label merge updates `source_item/source_survey` and returns `matched/added/total`.
- `python/test_survey_overlap.py:21-28` verifies missing sidecar defaults.
- `python/test_survey_overlap.py:31-56` verifies normalized survey ids, concept links, and speaker choices.
- `python/test_survey_overlap.py:59-77` verifies sidecar update/persistence.
- `python/test_survey_overlap.py:184-195` verifies speaker choices override legacy fallback.
- `python/test_survey_overlap.py:216-236` verifies `concepts.csv` round-trip keeps canonical survey ids.
- `python/test_server_onboard_speaker.py:313+` already covers survey choices writing the sidecar on onboard commit.

Frontend:

- `src/api/client.test.ts:152-230` pins bare `/api/survey-overlap` GET/POST wire format.
- `src/components/parse/ConceptSidebar.test.tsx:301-332` pins context-menu behavior.
- `src/components/parse/ConceptSidebar.test.tsx:335-417` pins per-speaker survey choice flips and badge clicking.
- `src/stores/configStore.test.ts:65-84` already covers survey sidecar data entering config store state.

### New tests required

Backend:

1. `test_canonical_survey_gloss_strict_rules`: prefix strip, suffix strip, whitespace/casefold, parenthetical retained, comma retained.
2. `test_concepts_import_links_cross_survey_exact_gloss_without_new_id`: existing KLQ `nose` plus incoming JBIL `nose` updates `survey-overlap.json` and does not add a concept row.
3. `test_concepts_import_reports_fuzzy_parenthetical_without_writing`: existing `hair (collective)` plus incoming `hair` returns fuzzy candidate only.
4. `test_concepts_import_reports_comma_token_without_writing`: `daughter, girl` vs `girl` and `daughter` return fuzzy candidates only.
5. `test_manual_survey_link_post_and_delete_persist_sidecar`: endpoint set/update/remove, normalized survey id, 404 missing concept.
6. `test_relink_by_gloss_dry_run_is_non_writing`: report groups and fuzzy candidates; file mtimes/content unchanged.
7. `test_relink_by_gloss_apply_is_idempotent_and_updates_annotations`: accepted group writes backup, sidecar, concepts.csv, and concept-id references.
8. OpenAPI/schema test for `/api/concepts/{conceptId}/survey-links` and `/api/concepts/relink-by-gloss` once OpenAPI is updated.

Frontend:

1. API contract tests for `setConceptSurveyLink`, `deleteConceptSurveyLink`, and `relinkConceptsByGloss` helpers.
2. ConceptSidebar test for `Change survey ID…` opening inline editor and submitting POST helper payload.
3. ConceptSidebar test that clickable badge gets hover underline only when `surveys` has at least two ids.
4. Migration UI test for dry-run list, confirmation, apply call, and config reload.
5. Regression test that per-speaker `speaker_choices` remains distinct from manual global concept survey links.

### LoC estimate

| Area | Files likely touched | Estimated delta |
|---|---|---:|
| Backend canonicalization + import linking | `python/survey_overlap.py`, `python/app/http/project_config_handlers.py`, `python/server.py` or route-domain module | 160-240 LoC |
| Backend manual relabel endpoint | route handler + sidecar helpers + OpenAPI | 120-180 LoC |
| Backend relink migration | new helper/service + route + backup/reference rewrite utilities | 260-420 LoC |
| Backend tests | import, sidecar, endpoint, migration tests | 260-380 LoC |
| Frontend API helpers/types | `src/api/contracts/*`, `src/api/types.ts`, barrel exports | 60-100 LoC |
| Frontend sidebar inline editor | `ConceptSidebar.tsx` + co-located test | 140-220 LoC |
| Frontend migration review flow | likely existing config/import surface + tests | 180-300 LoC |

Implementation should split into two PRs after this spec is accepted: backend first for contract + persistence, frontend second for UI/API consumption. Expected total implementation delta: roughly 1,180-1,840 LoC including tests, with backend migration breadth as the largest uncertainty.
