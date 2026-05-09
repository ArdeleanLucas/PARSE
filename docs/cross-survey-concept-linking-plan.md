# Cross-survey concept linking pre-research plan

This is the implementation spec for reconciling overlapping KLQ and JBIL survey items before the backend and frontend PRs ship code. The immediate fieldwork problem is that a speaker import currently ties an elicited form to one survey row, while an overlapping survey row with the same gloss can allocate a separate `concept_id`. That makes sequential review across surveys look like two concepts even when Lucas is reviewing the same comparative item.

The design below is deliberately conservative: preserve the existing five-column `concepts.csv` as the durable concept list, store many-to-many survey links in `survey-overlap.json`, and use a strict normalized-gloss match for automatic linking. Ambiguous cases are previewed for human review instead of being auto-merged.

## 1. Current state

### Frontend API types already expose survey links

`src/api/types.ts:171-181` defines the sidecar shape as `concept_survey_links` plus per-speaker `speaker_choices`:

```ts
export type SurveySettingsMap = Record<string, SurveyDisplaySettings>;
export type ConceptSurveyLinks = Record<string, string>;
export type ConceptSurveyLinksByConcept = Record<string, ConceptSurveyLinks>;
...
  concept_survey_links: ConceptSurveyLinksByConcept;
  speaker_choices: SpeakerSurveyChoices;
```

`src/api/types.ts:190-197` also lets each `ConceptEntry` carry legacy source fields plus a `surveys` map:

```ts
export interface ConceptEntry {
  id: string;
  label: string;
  source_item?: string;
  source_survey?: string;
  custom_order?: number;
  surveys?: ConceptSurveyLinks;
}
```

### Runtime `Concept` objects already carry `surveys`

`src/lib/speakerForm.ts:12-21` carries the same projection into frontend runtime concepts:

```ts
export interface Concept {
  id: number;
  key: string;
  name: string;
  tag: ConceptTag;
  sourceItem?: string;
  sourceSurvey?: string;
  customOrder?: number;
  surveys?: ConceptSurveyLinks;
  variants?: ConceptVariant[];
```

This matters because the new frontend affordance does not need a new concept identity model. It needs a way to add, remove, and choose among entries in `Concept.surveys`.

### The concept registry currently matches by plain label key

`python/concept_registry.py:42-65` loads `concepts.csv` and indexes labels with `concept_label_key(label)`:

```py
registry = ConceptRegistry(label_to_id={}, max_id=0, raw_rows=[])
...
normalized = concept_row_from_item(row)
normalized["id"] = cid
normalized["concept_en"] = label
registry.raw_rows.append(normalized)
registry.label_to_id.setdefault(concept_label_key(label), cid)
```

`python/concept_registry.py:71-83` reuses an existing concept when the plain label key matches, otherwise allocates a new row:

```py
def resolve_or_allocate_concept_id(registry: ConceptRegistry, label: str) -> tuple[str, bool]:
    clean_label = str(label or "").strip()
    key = concept_label_key(clean_label)
...
    existing = registry.label_to_id.get(key)
    if existing:
        return existing, False
```

The linking feature should not replace this registry wholesale. It should add a survey-aware normalized-gloss index beside the existing id/label behavior.

### `survey-overlap.json` is the right persistence target

`python/survey_overlap.py:46-53` defines the sidecar root fields:

```py
def _default_state() -> SurveyOverlapState:
    return {
        "version": 1,
        "color_coding_enabled": False,
        "surveys": {},
        "concept_survey_links": {},
        "speaker_choices": {},
    }
```

`python/survey_overlap.py:78-94` validates `concept_survey_links` as `{ concept_id: { survey_id: source_item } }`:

```py
for concept_id, links in raw.items():
    cid = str(concept_id or "").strip()
...
    for survey_id, source_item in links.items():
        sid = normalize_survey_id(survey_id)
        item = str(source_item or "").strip()
        if sid and item:
            clean_links[sid] = item
```

`python/survey_overlap.py:97-113` validates `speaker_choices` as `{ speaker: { concept_id: survey_id } }`, which is already per-speaker rather than global:

```py
for speaker, choices in raw.items():
    speaker_id = str(speaker or "").strip()
...
    for concept_id, survey_id in choices.items():
        cid = str(concept_id or "").strip()
        sid = normalize_survey_id(survey_id)
```

`python/survey_overlap.py:160-191` already supports merge-style patches and reset flags for the three sidecar sections:

```py
# Patches merge by default; reset_* flags clear a section first so reset plus re-seed can compose in one payload.
def update_survey_overlap_state(project_root: Path, patch: Mapping[str, object]) -> SurveyOverlapState:
...
    if isinstance(patch.get("concept_survey_links"), Mapping):
        incoming_links = _clean_links(patch.get("concept_survey_links"))
        for concept_id, links in incoming_links.items():
            merged["concept_survey_links"].setdefault(concept_id, {}).update(links)
```

`python/survey_overlap.py:194-209` combines legacy `source_item`/`source_survey` from `concepts.csv` with sidecar survey links for frontend config:

```py
legacy_item = row_value(row, "source_item", "survey_item")
legacy_survey = normalize_survey_id(row_value(row, "source_survey"))
if legacy_item and legacy_survey:
    links[legacy_survey] = legacy_item
...
if isinstance(sidecar_links, Mapping):
```

### `concepts.csv` stays a five-column file

`python/concept_source_item.py:11-17` pins the durable concepts header:

```py
CONCEPT_FIELDNAMES: tuple[str, ...] = (
    "id",
    "concept_en",
    "source_item",
    "source_survey",
    "custom_order",
)
```

`python/concept_source_item.py:31-48` already parses KLQ/EXT/JBIL cue names into `(source_item, source_survey, label)`:

```py
Recognized formats:
    KLQ:  ``(1.2)- forehead``       -> ("1.2", "KLQ", "forehead")
    EXT:  ``[5.1]- The boy cut...`` -> ("5.1", "EXT", "The boy cut...")
    JBIL: ``324- we``               -> ("324", "JBIL", "we")
```

`python/concept_source_item.py:93-112` writes only that current header, so the many-to-many survey map belongs in `survey-overlap.json`, not extra CSV columns:

```py
def write_concepts_csv_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
...
        writer = csv.DictWriter(handle, fieldnames=list(CONCEPT_FIELDNAMES))
        writer.writeheader()
```

### Existing import and config endpoints

`python/server.py:1534-1536` routes the concepts import endpoint:

```py
if request_path == "/api/concepts/import":
    self._api_post_concepts_import()
    return
```

`python/server_routes/exports.py:41-47` keeps the route wrapper thin and delegates to the HTTP helper:

```py
def _api_post_concepts_import(self) -> None:
    """Merge source_item/source_survey/custom_order from an uploaded CSV into concepts.csv."""
    try:
        response = _server._app_build_concepts_import_response(...)
```

`python/app/http/project_config_handlers.py:107-114` defines the import helper signature. It currently receives the multipart upload, project root, id normalizer, and upload limit only:

```py
def build_concepts_import_response(
    *,
    headers: Any,
    rfile: BinaryIO,
    project_root: pathlib.Path,
    normalize_concept_id: ConceptIdNormalizer,
```

`python/app/http/project_config_handlers.py:158-214` reports `matched`, `added`, `total`, and `mode` after merging into `concepts.csv`:

```py
matched = 0
added = 0
for up in upload_rows:
...
return JsonResponseSpec(
    status=HTTPStatus.OK,
    payload={"ok": True, "matched": matched, "added": added, "total": len(existing), ...},
)
```

`python/server.py:1403-1404` and `python/server.py:1500-1501` already expose `/api/survey-overlap` for GET/POST:

```py
if request_path == "/api/config": self._api_get_config(); return
if request_path == "/api/survey-overlap": self._api_get_survey_overlap(); return
...
if request_path == "/api/config": self._api_update_config(); return
if request_path == "/api/survey-overlap": self._api_post_survey_overlap(); return
```

`python/server_routes/config.py:22-29` wires those endpoints to `load_survey_overlap_state` and `update_survey_overlap_state`:

```py
def _api_get_survey_overlap(self) -> None:
    self._send_json(_server.HTTPStatus.OK, load_survey_overlap_state(_server._project_root()))
...
    state = update_survey_overlap_state(_server._project_root(), patch)
```

### Frontend survey badge and context menu already exist

`src/components/parse/ConceptSidebar.tsx:38-58` already accepts survey settings, speaker choices, and `onSurveyChoiceChange`:

```tsx
surveySettings?: SurveySettingsMap;
speakerSurveyChoices?: SpeakerSurveyChoices;
surveyColorCodingEnabled?: boolean;
onSurveyChoiceChange?: (speaker: string, conceptKey: string, surveyId: string) => void;
onMergeRequest?: (concept: SidebarConcept) => void;
```

`src/components/parse/ConceptSidebar.tsx:254-272` computes available survey choices and whether the badge can flip:

```tsx
const surveyChoices = surveyChoiceKeysForConcept(surveyConcept);
const nextSurveyId = surveyChoices.length > 1 && resolvedSurvey.surveyId
  ? surveyChoices[(surveyChoices.indexOf(resolvedSurvey.surveyId) + 1) % surveyChoices.length]
  : undefined;
const canFlipSurveyBadge = !!(activeSpeaker && onSurveyChoiceChange && nextSurveyId);
```

`src/components/parse/ConceptSidebar.tsx:331-340` renders a clickable survey badge when `canFlipSurveyBadge` is true:

```tsx
{canFlipSurveyBadge ? (
  <button
    type="button"
    aria-label={`Switch survey for ${concept.name} from ${resolvedSurveyLabel} ${resolvedSurvey.sourceItem} to ${nextSurveyLabel} ${nextSurveySourceItem}`}
    onClick={() => onSurveyChoiceChange(activeSpeaker, surveyConcept.key, nextSurveyId)}
```

`src/components/parse/ConceptSidebar.tsx:397-410` starts the existing context menu with `Merge with...`:

```tsx
{contextMenu && (
  <div
    ref={menuRef}
    role="menu"
...
    Merge with…
```

`src/components/parse/ConceptSidebar.tsx:412-433` already adds duplicate and unmerge actions, so `Change survey ID...` should be a sibling menu item:

```tsx
<button
  type="button"
  role="menuitem"
...
  Duplicate (split into next variant)
...
{contextMenu.concept.mergedKeys && contextMenu.concept.mergedKeys.length > 1 && (
```

`src/ParseUI.tsx:1869-1877` passes the active speaker, survey state, and choice callback into the sidebar:

```tsx
activeSpeaker={activeSpeakerForSidebar}
surveySettings={surveySettings}
speakerSurveyChoices={speakerSurveyChoices}
surveyColorCodingEnabled={surveyColorCodingEnabled}
onSurveyChoiceChange={handleSurveyChoiceChange}
```

## 2. Source-data shape

The real data shows why strict, reviewable matching is needed. KLQ is cue-based and sectioned; JBIL is a flat numeric wordlist with metadata rows before row 1.

### KLQ samples

`/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Qasr01 process/Qasr01.csv:2-9`:

```text
(1.2)- forehead	3:18:56.552	0:00.902	decimal	Cue
(1.3)- eyelid	4:20:07.000	0:00.615	decimal	Cue
(1.4)- eyebrow	3:20:42.000	0:00.605	decimal	Cue
(1.5)- nose	3:21:12.334	0:00.850	decimal	Cue
(1.6)- earlobe	3:21:29.213	0:01.430	decimal	Cue
(1.7)- elbow A	4:20:41.905	0:01.186	decimal	Cue
(1.7)- elbow B	4:22:16.623	0:00.777	decimal	Cue
(1.8)- armpit	3:22:12.425	0:01.185	decimal	Cue
```

`/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Saha01 process/Saha01.csv:2-9`:

```text
(1.2)- forehead	2:19:07.403	0:01.236	decimal	Cue
(1.3)- eyelid	2:19:25.439	0:00.664	decimal	Cue
(1.4)- eyebrow	2:19:36.684	0:00.653	decimal	Cue
(1.6)- earlobe	2:19:52.371	0:01.143	decimal	Cue
(1.8)- armpit	2:20:27.571	0:01.306	decimal	Cue
(1.10)- rib	2:20:00.556	0:00.863	decimal	Cue
(1.11)- the baby is in the uterus	2:21:01.526	0:01.318	decimal	Cue
(1.11)- uterus	2:20:46.774	0:00.711	decimal	Cue
```

`/home/lucas/.openclaw/agents/dr-kurd/Audio_Original/Kalh01 process/Kalh01.csv:2-9`:

```text
(1.1)- hair (collective)	1:57:45.000	0:00.773	decimal	Cue
(1.2)- forehead	1:58:06.686	0:00.546	decimal	Cue
(1.3)- eyelid	1:58:27.500	0:00.682	decimal	Cue
(1.4)- eyebrow A	1:58:47.301	0:00.698	decimal	Cue
(1.4)- eyebrow B	1:59:09.899	0:00.600	decimal	Cue
(1.5)- nose	1:59:17.708	0:00.643	decimal	Cue
(1.6)- earlobe	1:59:26.455	0:01.210	decimal	Cue
(1.7)- elbow	1:59:45.408	0:00.755	decimal	Cue
```

`Kalh01.csv:19-26` also shows parenthetical clarifiers and comma-separated alternatives:

```text
(2.1)- father	2:03:02.070	0:00.725	decimal	Cue
(2.2)- mother	2:03:07.061	0:00.786	decimal	Cue
(2.3)- father (vocative)	2:03:20.062	0:00.664	decimal	Cue
(2.4)- mother (vocative)	2:03:26.000	0:00.618	decimal	Cue
(2.5)- sister	2:03:33.500	0:00.580	decimal	Cue
(2.6)- grandfather	2:03:40.617	0:00.882	decimal	Cue
(2.7)- daughter, girl	2:03:59.423	0:00.526	decimal	Cue
(2.8)- baby	2:04:14.752	0:00.679	decimal	Cue
```

### JBIL samples

`/home/lucas/.openclaw/agents/dr-kurd/research/data/jbil_wordlist.csv:20-29`:

```text
1,one,yɛkʰ,,yɛkʰ,yɨk,yæk,yɛk,yɛkʰ
2,two ,du,,du,du,dʊ,du,dʊ
3,three,se,,sɛ,sɛ,se,sɛh,siɛ
4,four,tʃʷɑɽ̥,,tʃʷɑɾ,tʃʷɑɾ,tʃwɑɾ,tʃʊwɑɾ,tʃʰwɑɾ
5,five,piyɛntʃ,,pɛntʃ,pɛndʒ,pæŋdʒ,pɛndʒ,pɛnʒ
6,six,ʂuʂ,,ʃuʃ,ʃɛʃ,sɨs,ʃʊʃ,ʃɯʃ
7,seven,hɑftʰ,,ħɑutʰ,ħɑft,hæfʰt,ħɑft,ħɑft
8,eight,hɛʃt,,hɛʃt,hɛʃt,hæʃt,hɛyʃtʰ,hɛʃt
9,nine,niyɑ,,no,no,nu,nu,no
10,ten,dɛ,,dɑ,dɑ,dɨʔ,dɛh,dɛh
```

`jbil_wordlist.csv:50-63` contains body-part overlaps with KLQ:

```text
31,head,sɛɾ̥,,sɛɾ̥,sɛɾ,sɛɾolˠ,sɛɾ,sɛɾ̥
32,hair,mu,,qɵʃ,qɨʒ,qɨdʒ,-,qɨʒ
33,eye,tʃʰɑw,,tʃʰɑw,tʃɑo,tʃɑw,tʃɑo,tʃʰɛɯ
34,nose,litʰ,,lut,løtʰ,lʉtʰ,-,ɬɯitʰ
35,ear,guʃ,,gwɛtʃʰkɑ,guʃ,gʊʃ,goʃ,guʃ
36,mouth,dɜm,,dʌm,dɑm,dɨm,dɛm,dɛm
37,tooth,dan,,dɨʔgɑn,dɨˈgɑn,dɨgɑn,dɨgan,dɯgɑn
38,tongue,zəmɑn,,zuɑn,zuˈɑn,zʊɑn,zuɑn,zʊɑn
39,neck,mɨl,,mɨl̥,mɨn,mɪl,mɨl,mɨlˠ
40,throat,qoɽkʼ,,qʰɔɾi,qoɾɨg,qɔrɜg,qorɯq,qoɾkʰ
41,arm,qol,,bɑl,bɑl,bɑlˠ,bal,bɑl
42,hand,dɛst,,dɘs,dɛs,dɛs,dɛs,dɛs
43,elbow,ɑnɨʃk,,qoɾɑnisk̚,-,ɑɾɨndʒ,-,qʊeʕɦ
```

Concrete overlaps:

- KLQ `(1.5)- nose` and JBIL `34,nose` should auto-link to the same concept under strict normalization.
- KLQ `(1.7)- elbow A/B` and JBIL `43,elbow` should auto-link after stripping a trailing single-letter variant suffix.
- KLQ `(1.1)- hair (collective)` and JBIL `32,hair` should **not** auto-link under v1 strict rules; it should be a fuzzy preview candidate.
- KLQ `(2.7)- daughter, girl` should **not** auto-link to either `daughter` or `girl` via comma token splitting in v1; treat it as the whole gloss and put token-level matching in future work.

## 3. Matching algorithm

### Canonical v1 key

Backend should add one shared helper, e.g. `normalize_cross_survey_gloss(label: str) -> str`, under a backend concept-linking module rather than duplicating regexes in route handlers.

Rules, in order:

1. Trim input.
2. Strip one leading KLQ-style prefix: `^\(\s*\d+(?:\.\d+)*\s*\)\s*[-–—]?\s*`.
3. Strip one leading JBIL-style numeric prefix only when present in an import/cue-like label string: `^\d+\s*[-–—]\s*`. For structured JBIL CSV rows, use the `Eng` cell directly and store the numeric row as `source_item`.
4. Strip one trailing variant suffix matching `\s+[A-Z]$`, so `elbow A`, `elbow B`, and `eyebrow B` map to the base form.
5. Lowercase and collapse internal whitespace.
6. Keep parenthetical clarifiers.
7. Keep comma-separated alternatives as one canonical string.

Example output:

- `(1.5)- nose` -> `nose`
- `34- nose` -> `nose`
- `(1.7)- elbow B` -> `elbow`
- `(1.1)- hair (collective)` -> `hair (collective)`
- `(2.3)- father (vocative)` -> `father (vocative)`
- `(2.7)- daughter, girl` -> `daughter, girl`

### Rejected v1 alternatives

**Parenthetical clarifiers.** Strict keeps them because the data shows semantically meaningful pairs like `father` vs `father (vocative)` and `mother` vs `mother (vocative)` (`Kalh01.csv:19-22`). Fuzzy stripping would merge too aggressively. The safer default is to compute a secondary fuzzy-preview key with trailing parentheticals removed and expose those as review candidates, not write them automatically.

**Comma-separated alternatives.** Do not split and match any token in v1. `daughter, girl` is an elicitation-specific combined gloss; splitting would let it silently match whichever survey has only `daughter` or only `girl`. Record whole-string strict failures as fuzzy-preview candidates and leave token-level matching for a later reviewed migration.

**IPA/form-based matching.** Do not use speaker forms or IPA for v1 linking. The problem is source concept identity, not form identity; forms vary by dialect and would make imports order-dependent.

## 4. API contract

### 4a. Import-time auto-linking

Existing path: `POST /api/concepts/import` (`python/server.py:1534-1536`, wrapper in `python/server_routes/exports.py:41-47`). Request shape remains unchanged:

- `multipart/form-data`
- `csv`: required uploaded CSV file
- `mode`: optional `merge` or `replace`

Behavior change:

1. Parse each incoming row with the existing `id`, `concept_en`, `source_item`, `source_survey`, and `custom_order` semantics.
2. Build a normalized-gloss index over existing concept rows using the v1 canonical key from section 3.
3. For each incoming row with non-empty `source_survey` and `source_item`:
   - If an exact id or label match finds an existing row, keep current update behavior and also ensure `concept_survey_links[concept_id][survey_id] = source_item` when the row's normalized survey differs from or supplements the legacy source field.
   - Else if the normalized gloss matches exactly one existing concept, do **not** allocate a new concept id. Add/update `concept_survey_links[existing_id][survey_id] = source_item` in `survey-overlap.json`.
   - Else allocate a new concept row as today.
4. If more than one existing concept has the same normalized-gloss key, do not auto-link; create or leave the row according to current behavior and include an ambiguity record in the response.
5. In `replace` mode, clear legacy `source_item`/`source_survey`/`custom_order` on existing rows as today, but do **not** wholesale delete sidecar links unless an explicit future request flag is added. Cross-survey links are user-reviewed metadata and should not disappear because a one-survey CSV was reimported.

Response shape extends the current payload:

```json
{
  "ok": true,
  "matched": 12,
  "added": 3,
  "linked": 7,
  "total": 145,
  "mode": "merge",
  "survey_counts": {
    "klq": { "linked_count": 2, "created_count": 1, "matched_count": 12 },
    "jbil": { "linked_count": 5, "created_count": 2, "matched_count": 0 }
  },
  "ambiguous": [
    { "label": "hair", "source_survey": "jbil", "source_item": "32", "candidate_concept_ids": ["1", "132"] }
  ],
  "fuzzy_preview": [
    { "label": "hair", "source_survey": "jbil", "source_item": "32", "candidate_concept_id": "1", "reason": "parenthetical-stripped match: hair (collective)" }
  ]
}
```

Compatibility: existing callers that read `ok`, `matched`, `added`, `total`, and `mode` keep working. `linked`, `survey_counts`, `ambiguous`, and `fuzzy_preview` are additive.

OpenAPI must add the additive response fields for `/api/concepts/import` in `python/external_api/openapi.py`, and `src/api/contracts/enrichments-tags-notes-imports.ts:16-22` must add optional result fields.

### 4b. Manual relabel endpoint

New path: `POST /api/concepts/{conceptId}/survey-links`

Body:

```json
{ "survey_id": "jbil", "source_item": "32" }
```

Semantics:

- Normalize `survey_id` with `survey_overlap.normalize_survey_id`.
- Trim `source_item`.
- Validate `conceptId` exists in `concepts.csv`; return `404` if missing.
- Require both `survey_id` and `source_item`; return `400` if either is empty after normalization.
- Persist by writing `survey-overlap.json` with `concept_survey_links[conceptId][survey_id] = source_item`.
- Do not rewrite `concepts.csv` unless the concept has no legacy `source_survey`/`source_item` and the implementation deliberately decides to backfill the first link. Recommended v1: sidecar-only to keep the operation narrow and reversible.
- Return the updated `ConceptEntry` projection exactly as `/api/config` would expose it for that concept, including `surveys`.

New path: `DELETE /api/concepts/{conceptId}/survey-links`

Body:

```json
{ "survey_id": "jbil", "source_item": "32" }
```

Semantics:

- Normalize `survey_id` and trim `source_item`.
- Validate concept exists.
- If the sidecar has the same survey id and source item, remove that link.
- If `source_item` is omitted or empty in a future-compatible client, remove the link by survey id only. For v1 frontend, send both values so accidental deletes are harder.
- Remove an empty concept id object from `concept_survey_links` after deletion.
- Do not delete legacy `source_item`/`source_survey` stored in `concepts.csv`; if the requested deletion targets the legacy link, return `409` with a message that legacy links require CSV edit/reimport.
- Return the updated `ConceptEntry` projection.

Both manual endpoints must be represented in OpenAPI as `/api/concepts/{conceptId}/survey-links` with `post` and `delete` operations.

## 5. Frontend changes

Parse-front-end should keep this feature inside `ConceptSidebar` and existing API/store seams; no modal and no new global mode.

1. **Badge flip predicate.** `src/components/parse/ConceptSidebar.tsx:266-272` already computes `surveyChoices` and `nextSurveyId`. Broaden the visible affordance so a concept with two or more `survey_links` always shows as interactive when `activeSpeaker` and `onSurveyChoiceChange` exist. The cycle order remains stable sorted survey ids because `surveyChoiceKeysForConcept` returns sorted keys in `src/lib/surveyOverlap.ts:84-86`.
2. **Per-speaker choice only.** Continue calling `onSurveyChoiceChange(activeSpeaker, surveyConcept.key, nextSurveyId)` as in `ConceptSidebar.tsx:331-340`. This writes through the existing `speaker_choices` mechanism; it is not a global survey toggle.
3. **Context menu item.** Add `Change survey ID...` beside `Merge with...`, `Duplicate...`, and `Unmerge` in `ConceptSidebar.tsx:397-433`.
4. **Inline editor.** The menu item opens a small inline editor anchored in or below the context menu. It contains:
   - a `survey_id` select populated from existing `surveySettings` keys plus survey ids already present on the concept;
   - a `source_item` text input;
   - Save and Cancel buttons.
   No modal.
5. **API calls.** Add frontend contract helpers for `POST /api/concepts/{conceptId}/survey-links` and `DELETE /api/concepts/{conceptId}/survey-links`. These helpers must go through `src/api/client.ts`/contract barrels, not component-level bare `fetch`.
6. **State refresh.** After a successful save/delete, reload config so `ConceptEntry.surveys`, `surveySettings`, and grouped concept projections refresh consistently.
7. **Visual cue.** Add subtle underline-on-hover to multi-survey badges so clickable source badges are discoverable without adding visual noise.
8. **Tests.** Update `ConceptSidebar` tests to cover multi-survey hover/clickability, context-menu editor open/save/cancel, and per-speaker `onSurveyChoiceChange` behavior. Update API contract tests for the two new helpers.

## 6. Migration

Already-imported workspaces can contain split concepts that should be reconciled. Add one idempotent endpoint:

`POST /api/concepts/relink-by-gloss`

Request:

```json
{ "apply": false }
```

Response for dry-run:

```json
{
  "ok": true,
  "apply": false,
  "strict_matches": [
    {
      "source_concept_id": "145",
      "target_concept_id": "34",
      "normalized_gloss": "nose",
      "links_to_add": { "jbil": "34" },
      "would_remove_source_concept": true
    }
  ],
  "ambiguous": [],
  "fuzzy_preview": [
    {
      "source_concept_id": "146",
      "target_concept_id": "1",
      "normalized_gloss": "hair",
      "reason": "parenthetical-stripped match: hair (collective)"
    }
  ]
}
```

Apply request:

```json
{ "apply": true }
```

Apply semantics:

1. Build strict normalized-gloss groups across existing `concepts.csv` rows.
2. For each group with one canonical target and one or more source duplicates:
   - Choose the target deterministically: lowest numeric `concept_id`, unless a row has richer legacy `source_survey`/`source_item` metadata and the lower id is metadata-empty. If that exception is too surprising during implementation, keep lowest id and document it in the response.
   - Merge each source row's legacy link and sidecar links into the target concept's `concept_survey_links`.
   - Preserve `speaker_choices` by moving any choices from source ids to the target id when the chosen survey exists on the target after merge.
   - Rewrite annotation files only if source concept ids appear in annotation intervals. This must be explicit in the dry-run report as `annotation_rewrites` and must preserve timestamps exactly.
   - Remove duplicate source rows from `concepts.csv` only after links and annotation references are safely migrated.
3. Fuzzy preview candidates are never applied by `apply: true` in v1; they require manual relabel or a later reviewed migration.
4. The endpoint is idempotent: running dry-run after apply returns no strict matches for already-linked pairs.

Frontend flow: call dry-run first, show a confirmation list, then call `{ "apply": true }`. This is critical for existing Qasr01 workspaces because Lucas needs a reviewable list before PARSE merges source concept identity.

## 7. Test surface and LoC estimate

### Existing tests that already exercise adjacent contracts

- `python/test_server_concepts_import.py:113-153` covers `POST /api/concepts/import` merge/add behavior and current `matched`/`added` counters.
- `python/test_server_concepts_import.py:156-173` covers replace mode clearing optional fields.
- `python/test_server_concepts_import.py:176-193` proves `/api/config` surfaces `source_item`, `source_survey`, and `custom_order`.
- `python/test_app_http_project_config_handlers.py:118-177` covers the helper-level import response for merge/replace.
- `python/test_server_project_config_http.py:109-123` covers wrapper error mapping for `_api_post_concepts_import`.
- `python/test_external_api_surface.py:70-103` includes `/api/concepts/import` in OpenAPI route coverage, and `python/test_external_api_surface.py:132-148` covers `/api/survey-overlap` read/write contract.
- `python/test_survey_overlap.py` already covers sidecar normalization/update/projection behavior and should receive targeted additions for manual set/delete semantics.

### New backend tests

1. `python/test_cross_survey_concept_linking.py` or additions to `python/test_app_http_project_config_handlers.py`:
   - normalized gloss strips KLQ prefixes, JBIL label prefixes, and trailing single-letter variants;
   - parentheticals remain strict;
   - comma alternatives remain strict;
   - exact normalized match links incoming JBIL `nose` to existing KLQ `nose` without allocating a new id;
   - ambiguous normalized match returns `ambiguous` and does not auto-link;
   - response includes `linked`, `survey_counts[*].linked_count`, and `survey_counts[*].created_count`.
2. `python/test_server_concept_survey_links.py`:
   - `POST /api/concepts/{conceptId}/survey-links` persists a sidecar link and returns updated concept entry;
   - `DELETE /api/concepts/{conceptId}/survey-links` removes only the matching sidecar link;
   - missing concept returns `404`; malformed body returns `400`; attempted legacy-link delete returns `409`.
3. `python/test_concepts_relink_by_gloss.py`:
   - dry-run reports strict duplicates without writes;
   - apply merges links and speaker choices idempotently;
   - fuzzy parenthetical match is preview-only;
   - annotation rewrite path preserves `start`/`end` and only changes `concept_id` when source ids are actually referenced.
4. `python/test_external_api_surface.py`:
   - OpenAPI includes `/api/concepts/{conceptId}/survey-links` and `/api/concepts/relink-by-gloss` with request/response shapes.

### New frontend tests

1. `src/components/parse/ConceptSidebar.test.tsx`:
   - multi-survey badges show the hover/click affordance;
   - clicking the badge cycles by sorted survey ids and calls `onSurveyChoiceChange` for the active speaker only;
   - context menu opens `Change survey ID...` and inline editor submit calls the new API callback.
2. `src/api/contracts/*.test.ts` or existing API contract test file:
   - manual set/delete helpers call the correct routes through the API client;
   - import result type accepts optional `linked`, `survey_counts`, `ambiguous`, and `fuzzy_preview` fields.
3. Config reload/store test:
   - after manual relabel save, frontend reloads config and displays the updated `surveys` projection.

### Honest LoC estimate

Backend delta: approximately 430-620 LoC.

- `python/concept_linking.py` or equivalent helper module: 90-130 LoC for normalization, indexing, ambiguity/fuzzy preview structs.
- `python/app/http/project_config_handlers.py`: 80-130 LoC to integrate import-time linking and additive response fields.
- `python/server_routes/exports.py` plus `python/server.py` route dispatch: 45-75 LoC for manual set/delete and relink route wrappers.
- `python/survey_overlap.py`: 40-70 LoC for set/delete helpers if not implemented in route helper code.
- `python/external_api/openapi.py`: 40-70 LoC for the new path contracts and schemas.
- Backend tests: 135-145 LoC across import, manual relabel, migration, and OpenAPI coverage.

Frontend delta: approximately 260-380 LoC.

- API contract/types: 45-70 LoC for result fields and new helpers.
- `src/components/parse/ConceptSidebar.tsx`: 90-140 LoC for context-menu item, inline editor state, and badge cue.
- `src/ParseUI.tsx` or a config store hook seam: 35-60 LoC to call helpers and reload config.
- Frontend tests: 90-110 LoC.

The first backend implementation PR should ship normalization + import-time linking + manual relabel endpoints with OpenAPI/tests. The migration endpoint can be either in that PR if small after helper extraction or a second backend PR; it rewrites concepts and potentially annotations, so it deserves its own review if it exceeds the estimate.
