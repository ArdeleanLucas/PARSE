# INTERFACES.md — PARSE Module Contract v5.1 (Post-build audit)

All modules attach to `window.PARSE`. Communication is via CustomEvents on `document`.

---

## Global Namespace

```js
window.PARSE = {
  // Project config + loaded assets
  project: null,
  sourceIndex: null,
  transcripts: {},
  suggestions: null,
  annotations: {},

  // Compare enrichments cache (normalized by js/compare/enrichments.js)
  enrichments: {
    computed_at: null,
    config: {},
    cognate_sets: {},
    similarity: {},
    borrowing_flags: {},
    manual_overrides: {
      cognate_sets: {},
      borrowing_flags: {},
      accepted_concepts: {},
    },
    history: [],
  },

  // Tag state (normalized by js/shared/tags.js)
  tags: {
    tags: [],                      // [{ id, name, color }]
    assignments: {},               // { [conceptId]: string[] }
    included: {},                  // { [conceptId]: boolean } (false entries persisted)
    filter: { tagId: null, showUntagged: false },
  },

  // Current app mode and selection
  mode: 'annotate',               // 'annotate' | 'compare'
  currentSpeaker: null,
  currentConcept: null,

  // Compare UI/session snapshot (set by js/compare/compare.js + concept-table.js)
  compareState: {
    availableSpeakers: [],
    selectedSpeakers: [],
    concepts: [],
    filteredConcepts: [],
    selectedConceptId: '',
    tagFilter: { tagId: null, showUntagged: true },
  },

  // Module references (set by each module's init())
  modules: {
    // Shared
    config: null,
    annotationStore: null,
    tags: null,                   // js/shared/tags.js
    audioPlayer: null,            // js/shared/audio-player.js
    aiClient: null,               // js/shared/ai-client.js
    spectrogram: null,

    // Annotate mode
    panel: null,
    waveform: null,
    transcript: null,
    suggestions: null,
    regions: null,
    fullscreen: null,
    annotationPanel: null,
    videoSync: null,
    importExport: null,
    onboarding: null,

    // Compare mode
    compare: null,                // js/compare/compare.js
    conceptTable: null,           // js/compare/concept-table.js
    cognateControls: null,        // js/compare/cognate-controls.js
    borrowingPanel: null,         // js/compare/borrowing-panel.js
    speakerImport: null,          // [PLANNED] js/compare/speaker-import.js
    enrichmentsIO: null,          // js/compare/enrichments.js
  }
};
```

---

## Events (CustomEvent on `document`)

All events use `detail` for payload. All timestamps are in seconds (float).

### Project Lifecycle

```js
// Project config loaded and validated
"parse:project-loaded" → { projectId, projectName, speakers: string[], language: { code, name } }

// Project config error
"parse:project-error" → { error: string, showOnboarding: boolean }
```

### Panel Lifecycle (Annotate)

```js
// Open panel for a speaker + concept
"parse:panel-open" → { speaker, conceptId, sourceWav, lexiconStartSec }

// Close panel
"parse:panel-close" → { speaker }
```

### Audio Navigation

```js
// Seek waveform to timestamp
"parse:seek" → { timeSec, createRegion?: boolean, regionDurationSec?: number }

// Playback position update (continuous during playback)
"parse:playback-position" → { timeSec }

// Playback state change
"parse:playback-state" → { playing: boolean }
```

### Audio Player (Shared — used in both modes)

```js
// Play a specific audio region from a WAV file
"parse:audio-play" → { sourceWav, startSec, endSec, speaker?, conceptId? }

// Audio playback completed
"parse:audio-done" → { sourceWav, speaker?, conceptId? }
```

### Region Management (Annotate)

```js
// Region created or updated
"parse:region-updated" → { startSec, endSec }

// Region assigned to concept
"parse:region-assigned" → { speaker, conceptId, startSec, endSec, sourceWav, aiSuggestionUsed?, aiSuggestionScore? }
```

### Annotations

```js
// Annotation saved
"parse:annotation-save" → { speaker, conceptId, startSec, endSec, ipa, ortho, concept, sourceWav, aiSuggestionUsed?, aiSuggestionScore? }

// Annotation deleted
"parse:annotation-delete" → { speaker, conceptId, startSec }

// Annotations loaded from disk
"parse:annotations-loaded" → { speaker, count }

// Annotation data changed
"parse:annotations-changed" → { speaker, totalAnnotations }
```

### Tags (NEW in v5.0)

```js
// Tag created
"parse:tag-created" → { tagId, name, color? }

// Tag deleted
"parse:tag-deleted" → { tagId }

// Items tagged
"parse:items-tagged" → { tagId, conceptIds: number[], action: "add" | "remove" }

// Tag filter changed (sidebar filter)
"parse:tag-filter" → { tagId: string | null, showUntagged: boolean }

// Include-in-analysis toggle
"parse:analysis-toggle" → { conceptId, included: boolean }
```

### Suggestions & Prior (Annotate)

```js
// AI suggestion clicked
"parse:suggestion-click" → { suggestionIndex, segmentStartSec, segmentEndSec }

// Positional prior reference speakers changed
"parse:priors-changed" → { selectedSpeakers: string[] }
```

### Transcript (Annotate)

```js
"parse:transcript-click" → { segmentIndex, startSec }
```

### Fullscreen (Annotate)

```js
"parse:fullscreen-toggle" → { active: boolean }
"parse:navigate-concept" → { direction: "prev" | "next", missingOnly: boolean }
```

### Import / Export

```js
"parse:import-textgrid" → { file: File, targetSpeaker, mode: "replace" | "new", newSpeakerName? }
"parse:export-textgrid" → { speaker }
"parse:export-elan" → { speaker }
"parse:export-csv" → { speaker: string | "all" }
"parse:export-segments" → { speaker: string | "all" }
"parse:export-wordlist" → { speakers: string[], conceptIds: number[] }  // [PLANNED] LingPy TSV export event not emitted in current JS
"parse:io-complete" → { operation, format, success, message? }
```

### Video Sync (Annotate)

```js
"parse:video-sync-start" → { speaker, videoFile, audioFile, fps }
"parse:video-sync-progress" → { speaker, step, progress }
"parse:video-sync-result" → { speaker, offsetSec, driftRate, method, aiVerified, confidence }
"parse:video-sync-locked" → { speaker, videoFile, offsetSec, driftRate, manualAdjustmentSec, fps }
"parse:video-extract-clips" → { speaker: string | "all" }  // [PLANNED] not emitted in current JS
```

### Compare Mode (NEW in v5.0)

```js
// Compare mode opened
"parse:compare-open" → { speakers: string[], conceptIds: Array<number | string> }

// Compare mode closed
"parse:compare-close" → {}

// Speaker added to comparison
"parse:compare-speaker-add" → { speaker, importMode: "raw" | "existing" | "manual" }

// Speaker removed from comparison
"parse:compare-speaker-remove" → { speaker }

// Current compare speaker list changed
"parse:compare-speakers-changed" → { speakers: string[] }

// Canonical concept selection event used by compare submodules
"parse:compare-concept-select" → { conceptId: number | string | null, conceptLabel: string, speakers: string[] }

// Compatibility + high-level concept selection broadcast
"parse:compare-concept-selected" → {
  conceptId: string | null,
  conceptLabel?: string,
  speakers?: string[]
}
```

### Cognate Controls (NEW in v5.0)

```js
// Cognate grouping accepted (keep precomputed sets)
"parse:cognate-accept" → { conceptId }

// Cognate group split initiated
"parse:cognate-split-start" → { conceptId }

// Speaker reassigned during split
"parse:cognate-split-assign" → { conceptId, speaker, fromGroup: string, toGroup: string }

// Cognate split confirmed
"parse:cognate-split-done" → { conceptId, groups: Record<string, string[]> }

// All merged into one cognate set
"parse:cognate-merge" → { conceptId }

// Single speaker's cognate class cycled
"parse:cognate-cycle" → { conceptId, speaker, newGroup: string }

// Cognate sets changed (any modification)
"parse:cognates-changed" → {
  conceptId,
  groups: Record<string, string[]>,
  source?: string // set by enrichments.js
}
```

### Borrowing (NEW in v5.0)

```js
// Borrowing decision emitted by borrowing panel
"parse:borrowing-decision" → {
  conceptId,
  speakerId: string,
  decision: "borrowed" | "inherited" | "skip",
  sourceLang: string | null
}

// [PLANNED] event consumed by enrichments.js; no current dispatcher in JS
"parse:borrowing-changed" → { conceptId, speaker, status }

// [PLANNED] event consumed by enrichments.js; no current dispatcher in JS
"parse:borrowing-handle" → { conceptId, speaker, handling: "missing" | "separate_cognate" }
```

### Enrichments (NEW in v5.0)

```js
// Computation requested
"parse:compute-request" → {
  type: "cognates" | "offset" | "spectrograms",
  speakers: string[],
  conceptIds: Array<number | string>,
  contactLanguages?: string[],
  lexstatThreshold?: number
}

// Computation started (background)
"parse:compute-started" → { jobId, type, estimatedDuration? }

// Computation progress
"parse:compute-progress" → { jobId, type, progress: number, message? }

// Computation completed
"parse:compute-done" → { jobId, type, success: boolean, error?: string }

// Enrichments updated (data refreshed in memory)
"parse:enrichments-updated" → { computedAt, speakers: string[], concepts: Array<number | string> }

// Enrichments read/write error
"parse:enrichments-error" → { message: string, timestamp: string }
```

### AI / STT (NEW in v5.0)

```js
// Full-file STT requested for new speaker
"parse:stt-request" → { speaker, sourceWav, options?: object }

// STT job started
"parse:stt-started" → { jobId, speaker, estimatedDuration? }

// STT progress
"parse:stt-progress" → { jobId, speaker, progress: number, segmentsProcessed: number }

// STT completed
"parse:stt-done" → { jobId, speaker, success: boolean, totalSegments?: number, error?: string }

// [PLANNED] Cross-speaker match results event not emitted in current JS
"parse:match-results" → { speaker, matches: Array<{ conceptId, candidates: Array<{ startSec, endSec, ipa, ortho, confidence }> }> }
```

---

## Module APIs (implemented)

### `window.PARSE.modules.compare` (`js/compare/compare.js`)

**Exports**

- `init(containerEl?) => Promise<object>`
- `destroy() => void`
- `refresh() => Promise<void>`
- `getSelectedSpeakers() => string[]`

**Dispatches**

- `parse:compare-open`
- `parse:compare-close`
- `parse:compare-speaker-add`
- `parse:compare-speaker-remove`
- `parse:compare-speakers-changed`
- `parse:compare-concept-selected`
- `parse:compare-concept-select` (compat alias)
- `parse:compute-request`
- `parse:compute-started`
- `parse:compute-progress`
- `parse:compute-done`
- `parse:tag-filter`

**Consumes**

- `parse:tag-filter` → updates local compare filter state, rerenders header/table, re-emits `parse:compare-open`
- `parse:compare-concept-selected` → syncs selected concept in compare state
- `parse:compute-request` → starts compute workflow + polling

**Global state writes**

- `P.mode = 'compare'`
- `P.compareState.availableSpeakers`
- `P.compareState.selectedSpeakers`
- `P.compareState.concepts`
- `P.compareState.filteredConcepts`
- `P.compareState.selectedConceptId`
- `P.compareState.tagFilter`

### `window.PARSE.modules.conceptTable` (`js/compare/concept-table.js`)

**Exports**

- `init(containerEl?) => object`
- `destroy() => void`
- `setConcepts(concepts) => void`
- `setSpeakers(speakers) => void`
- `setData(payload) => void`
- `refresh() => void`
- `getVisibleConceptIds() => Array<number|string>`

**Dispatches**

- `parse:compare-concept-select`
- `parse:compare-concept-selected`
- `parse:audio-play`

**Consumes**

- `parse:enrichments-updated` → rerenders table and cognate badges
- `parse:tag-filter` → rerenders with active filter
- `parse:cognates-changed` → rerenders updated groups
- `parse:compare-speakers-changed` → updates visible speaker columns
- `parse:compare-concept-select` → syncs selected row
- `parse:annotations-changed` → rerenders entries from latest annotations

**Global state writes**

- `P.currentConcept`
- `P.compareState.selectedConceptId`

### `window.PARSE.modules.cognateControls` (`js/compare/cognate-controls.js`)

**Exports**

- `init(containerEl?) => object`
- `destroy() => void`
- `setConcept(conceptId, conceptLabel?) => void`
- `setSpeakers(speakers) => void`

**Dispatches**

- `parse:cognate-accept`
- `parse:cognate-split-start`
- `parse:cognate-split-assign`
- `parse:cognate-split-done`
- `parse:cognate-merge`
- `parse:cognate-cycle`
- `parse:cognates-changed`

**Consumes**

- `parse:compare-concept-select` → sets concept context and speaker list
- `parse:compare-speakers-changed` → re-sanitizes group membership
- `parse:cognates-changed` → updates panel state for current concept
- `parse:enrichments-updated` → reloads groups from enrichments cache

### `window.PARSE.modules.enrichmentsIO` (`js/compare/enrichments.js`)

**Exports**

- `init() => Promise<object>`
- `destroy() => void`
- `read() => Promise<object>`
- `write(reason?) => Promise<object>`
- `flushPending() => boolean`
- `getError() => { message: string, timestamp: string } | null`
- `getCognateGroupsForConcept(conceptId) => Record<string, string[]>`
- `getGroupForSpeaker(conceptId, speaker) => string`
- `setCognateGroups(conceptId, groups, source?) => void`
- `clearManualOverride(conceptId) => boolean`

**Dispatches**

- `parse:enrichments-updated`
- `parse:enrichments-error`
- `parse:cognates-changed`

**Consumes**

- `parse:cognate-accept` → marks concept accepted in `manual_overrides.accepted_concepts`
- `parse:cognate-split-done` → persists split output into manual cognate overrides
- `parse:cognate-merge` → merges all speakers into group `A`
- `parse:cognate-cycle` → cycles a speaker to next group and persists
- `parse:borrowing-changed` → updates `manual_overrides.borrowing_flags` ([PLANNED] producer)
- `parse:borrowing-handle` → updates borrowing handling override ([PLANNED] producer)
- `parse:compare-close` → flushes pending debounced writes

**Global state writes**

- `P.enrichments` (normalized shape)

### `window.PARSE.modules.tags` (`js/shared/tags.js`)

**Exports**

- `init(containerEl?) => object`
- `destroy() => void`
- `getTags() => Array<{ id, name, color }>`
- `createTag(name, color?) => { id, name, color }`
- `deleteTag(tagId) => boolean`
- `renameTag(tagId, name) => { id, name, color } | null`
- `addTagToConcepts(tagId, conceptIds) => number[]`
- `removeTagFromConcepts(tagId, conceptIds) => number[]`
- `getTagsForConcept(conceptId) => Array<{ id, name, color }>`
- `isIncluded(conceptId) => boolean`
- `setIncluded(conceptId, included) => boolean`
- `setFilter(tagId, showUntagged?) => { tagId, showUntagged }`
- `setShowUntagged(showUntagged) => { tagId, showUntagged }`
- `getFilter() => { tagId, showUntagged }`
- `matchesFilter(conceptId) => boolean`

**Dispatches**

- `parse:tag-created`
- `parse:tag-deleted`
- `parse:items-tagged`
- `parse:tag-filter`
- `parse:analysis-toggle`

**Consumes**

- none (`parse:*`)

**Global state writes**

- `P.tags` (normalized tags, assignments, included map, filter)

### `window.PARSE.modules.aiClient` (`js/shared/ai-client.js`)

**Exports**

- `init(options?) => object`
- `destroy() => void`
- `setBaseUrl(baseUrl) => void`
- `requestSTT(speaker, sourceWav, opts?) => Promise<string>`
- `pollSTTStatus(jobId) => Promise<object>`
- `requestIPA(text, language) => Promise<string>`
- `requestSuggestions(speaker, opts?) => Promise<Array|object>`
- `requestCompute(type, speakers, conceptIds, opts?) => Promise<string>`
- `getEnrichments() => Promise<object>`
- `saveEnrichments(data) => Promise<object>`
- `getConfig() => Promise<object>`
- `updateConfig(patch) => Promise<object>`
- `startPolling(jobId, type, intervalMs?) => { key: string, stop: () => void }`
- `stopPolling(jobId, type) => void`

**Dispatches**

- `parse:stt-request`
- `parse:stt-started`
- `parse:stt-progress`
- `parse:stt-done`
- `parse:compute-started`
- `parse:compute-progress`
- `parse:compute-done`

**Consumes**

- none (`parse:*`)

### `window.PARSE.modules.audioPlayer` (`js/shared/audio-player.js`)

**Exports**

- `init() => object`
- `destroy() => void`
- `play(sourceWav, startSec, endSec) => Promise<void>`
- `stop() => void`
- `isPlaying() => boolean`

**Dispatches**

- `parse:audio-done`

**Consumes**

- `parse:audio-play` → plays requested region, emits `parse:audio-done` on completion

---

## DOM Contract

### parse.html (Annotate Mode)

```html
<div id="parse-panel" class="parse-panel hidden">
  <div id="parse-header"></div>
  <div id="parse-priors"></div>
  <div id="parse-suggestions"></div>
  <div id="parse-transcript"></div>
  <div id="parse-waveform"></div>
  <div id="parse-spectrogram"></div>
  <div id="parse-annotation"></div>
  <div id="parse-controls"></div>
</div>
<div id="parse-fullscreen-overlay" class="parse-fullscreen hidden"></div>
<div id="parse-video-sync" class="parse-video-sync hidden"></div>
<div id="parse-io-modal" class="parse-modal hidden"></div>
<div id="parse-onboarding" class="parse-onboarding hidden"></div>
```

### compare.html (Compare Mode)

```html
<div id="compare-container">
  <div id="compare-header">
    <!-- Mode switcher, speaker selector, tag filter, compute button -->
  </div>
  <div id="compare-table">
    <!-- Concept × speaker matrix, rendered by concept-table.js -->
  </div>
  <div id="compare-cognate-panel">
    <!-- Cognate controls: accept/split/merge/cycle -->
  </div>
  <div id="compare-borrowing-panel">
    <!-- Similarity bars, borrowing adjudication -->
  </div>
  <div id="compare-spectrogram">
    <!-- On-demand spectrogram display -->
  </div>
</div>
<div id="compare-speaker-import" class="parse-modal hidden"></div>
<div id="compare-compute-status">
  <!-- Background computation progress indicator -->
</div>
```

---

## Data Schemas (for JS consumption)

### project.json — see PROJECT_PLAN.md §4.1

### Annotation File — see CODING.md "Key Schemas"

### Enrichments — see CODING.md "Key Schemas"

### AI Config — see `config/ai_config.json`

### source_index.json

```ts
interface SourceIndex {
  speakers: Record<string, {
    source_wavs: Array<{
      filename: string;
      duration_sec: number;
      file_size_bytes: number;
      bit_depth: number;
      sample_rate: number;
      channels: number;
      lexicon_start_sec: number;
      is_primary: boolean;
    }>;
    peaks_file: string;
    transcript_file: string;
    has_csv: boolean;
    notes?: string;
  }>;
}
```

### coarse_transcripts/<Speaker>.json

```ts
interface CoarseTranscript {
  speaker: string;
  source_wav: string;
  duration_sec: number;
  segments: Array<{ start: number; end: number; text: string; }>;
}
```

### ai_suggestions.json

```ts
interface AISuggestions {
  positional_anchors: Record<string, { concept_coverage: number; timestamps: Record<string, number>; }>;
  suggestions: Record<string, {
    concept_en: string;
    reference_forms: string[];
    speakers: Record<string, Array<{
      source_wav: string;
      segment_start_sec: number;
      segment_end_sec: number;
      transcript_text: string;
      matched_token: string;
      confidence: "high" | "medium" | "low";
      confidence_score: number;
      method: "exact_ortho_match" | "fuzzy_ortho_match" | "romanized_phonetic_match" | "llm_assisted_match";
      note?: string;
    }>>;
  }>;
}
```

### peaks/<Speaker>.json

```ts
interface PeaksData {
  version: 2;
  channels: number;
  sample_rate: number;
  samples_per_pixel: number;
  bits: number;
  length: number;
  data: number[];
}
```

---

## Server API Endpoints

| Endpoint | Method | Purpose | Returns |
|----------|--------|---------|---------|
| `POST /api/stt` | POST | Full-file STT | `{ jobId }` |
| `POST /api/stt/status` | POST | Poll STT progress | `{ jobId, progress, status, segments? }` |
| `POST /api/ipa` | POST | Text → IPA | `{ ipa }` |
| `POST /api/suggest` | POST | AI concept suggestions | `{ suggestions[] }` |
| `POST /api/compute/cognates` | POST | LexStat computation | `{ jobId }` |
| `POST /api/compute/offset` | POST | Auto-offset detection | `{ jobId }` |
| `POST /api/compute/spectrograms` | POST | Batch spectrograms | `{ jobId }` |
| `GET /api/enrichments` | GET | Read enrichments | `{ enrichments }` |
| `POST /api/enrichments` | POST | Write enrichments | `{ success }` |
| `GET /api/config` | GET | Read config | `{ config }` |
| `PUT /api/config` | PUT | Update config | `{ success }` |
| `GET /*` | GET | Static files | File content |

All long-running endpoints return immediately with `{ jobId }`. Poll status via `/api/{type}/status`.

---

## Positional Re-Ranking Algorithm (client-side)

Used by `suggestions-panel.js` when the reviewer selects reference speakers.

```
1. For each selected speaker, look up their timestamp for currentConceptId
2. Compute median → expectedTimeSec
3. distance = |candidate.segment_start_sec - expectedTimeSec|
4. positionalBoost = max(0, 0.25 * (1 - distance / 120))
5. finalScore = min(1.0, candidate.base_score + positionalBoost)
6. Re-derive label: ≥0.80 = "high", 0.50-0.79 = "medium", <0.50 = "low"
```

---

## Spectrogram Web Worker Protocol

```js
// Main → Worker
{ type: "compute", audioData: Float32Array, sampleRate, windowSize: 2048|256, startSec, endSec }

// Worker → Main
{ type: "result", imageData: Uint8ClampedArray, width, height, startSec, endSec }

// Worker → Main (error)
{ type: "error", message: string }
```

---

## Migration Notes (v4.0 → v5.0)

1. Move JS files from `js/` to `js/annotate/` (Annotate-specific) or `js/shared/` (shared)
2. Update `<script src>` paths in `parse.html`
3. Add `compare.html` with `js/shared/` + `js/compare/` imports
4. Rename Python files per §14 in PROJECT_PLAN.md
5. Create `python/ai/` and `python/compare/` packages
6. Create `config/` directory with default configs
7. All new modules use `window.PARSE` and `parse:` events

---

## Event Cross-reference (Wave 14 surface)

| Event | Dispatched by | Consumed by |
|---|---|---|
| `parse:analysis-toggle` | `js/shared/tags.js` | - |
| `parse:annotations-changed` | `js/shared/annotation-store.js` | `js/compare/borrowing-panel.js`, `js/compare/concept-table.js` |
| `parse:audio-done` | `js/shared/audio-player.js` | - |
| `parse:audio-play` | `js/compare/concept-table.js` | `js/shared/audio-player.js` |
| `parse:borrowing-changed` | `[PLANNED]` | `js/compare/enrichments.js` |
| `parse:borrowing-decision` | `js/compare/borrowing-panel.js` | - |
| `parse:borrowing-handle` | `[PLANNED]` | `js/compare/enrichments.js` |
| `parse:cognate-accept` | `js/compare/cognate-controls.js` | `js/compare/enrichments.js` |
| `parse:cognate-cycle` | `js/compare/cognate-controls.js` | `js/compare/enrichments.js` |
| `parse:cognate-merge` | `js/compare/cognate-controls.js` | `js/compare/enrichments.js` |
| `parse:cognate-split-assign` | `js/compare/cognate-controls.js` | - |
| `parse:cognate-split-done` | `js/compare/cognate-controls.js` | `js/compare/enrichments.js` |
| `parse:cognate-split-start` | `js/compare/cognate-controls.js` | - |
| `parse:cognates-changed` | `js/compare/cognate-controls.js`, `js/compare/enrichments.js` | `js/compare/cognate-controls.js`, `js/compare/concept-table.js` |
| `parse:compare-close` | `js/compare/compare.js` | `js/compare/enrichments.js` |
| `parse:compare-concept-select` | `js/compare/compare.js`, `js/compare/concept-table.js` | `js/compare/cognate-controls.js`, `js/compare/concept-table.js` |
| `parse:compare-concept-selected` | `js/compare/compare.js`, `js/compare/concept-table.js` | `js/compare/borrowing-panel.js`, `js/compare/compare.js` |
| `parse:compare-open` | `js/compare/compare.js` | `js/compare/borrowing-panel.js` |
| `parse:compare-speaker-add` | `js/compare/compare.js` | - |
| `parse:compare-speaker-remove` | `js/compare/compare.js` | - |
| `parse:compare-speakers-changed` | `js/compare/compare.js` | `js/compare/borrowing-panel.js`, `js/compare/cognate-controls.js`, `js/compare/concept-table.js` |
| `parse:compute-done` | `js/compare/compare.js`, `js/shared/ai-client.js` | - |
| `parse:compute-progress` | `js/compare/compare.js`, `js/shared/ai-client.js` | - |
| `parse:compute-request` | `js/compare/compare.js` | `js/compare/compare.js` |
| `parse:compute-started` | `js/compare/compare.js`, `js/shared/ai-client.js` | - |
| `parse:enrichments-error` | `js/compare/enrichments.js` | - |
| `parse:enrichments-updated` | `js/compare/enrichments.js` | `js/compare/borrowing-panel.js`, `js/compare/cognate-controls.js`, `js/compare/concept-table.js` |
| `parse:items-tagged` | `js/shared/tags.js` | - |
| `parse:match-results` | `[PLANNED]` | - |
| `parse:stt-done` | `js/shared/ai-client.js` | - |
| `parse:stt-progress` | `js/shared/ai-client.js` | - |
| `parse:stt-request` | `js/shared/ai-client.js` | - |
| `parse:stt-started` | `js/shared/ai-client.js` | - |
| `parse:tag-created` | `js/shared/tags.js` | - |
| `parse:tag-deleted` | `js/shared/tags.js` | - |
| `parse:tag-filter` | `js/compare/compare.js`, `js/shared/tags.js` | `js/compare/compare.js`, `js/compare/concept-table.js` |
| `parse:video-extract-clips` | `[PLANNED]` | - |
| `parse:export-wordlist` | `[PLANNED]` | - |
