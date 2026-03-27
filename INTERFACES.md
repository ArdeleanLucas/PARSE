# INTERFACES.md — PARSE Module Contract v5.2 (Post-build audit + MC-246 assistant foundation)

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
    chatToolAdapters: null,       // js/shared/chat-tool-adapters.js (MC-246 foundation)
    chatClient: null,             // js/shared/chat-client.js (MC-246 foundation)
    chatPanel: null,              // js/shared/chat-panel.js (MC-246 foundation)
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

### Chat Assistant Foundation (NEW in MC-246 / PR #5)

```js
// Action events (UI → chat-client)
"parse:chat-send" → {
  text: string,
  context?: {
    mode?: "annotate" | "compare",
    speaker?: string,
    conceptId?: number | string,
    selectedSpeakers?: string[]
  },
  provider?: string,
  model?: string,
  reasoning?: string,
  intent?: string,
  retryOf?: string,
  attempt?: number
}
"parse:chat-cancel-run" → { runId: string }
"parse:chat-retry-run" → { runId: string, context?: object }
"parse:chat-launcher" → { open?: boolean, toggle?: boolean }
"parse:chat-draft" → { text: string }
"parse:chat-clear-history" → {}

// State + lifecycle events (chat-client → UI)
"parse:chat-state" → {
  reason: string,
  state: {
    sessionId: string,
    readOnly: boolean,
    launcher: { isOpen: boolean, unread: number },
    draft: string,
    runOrder: string[],
    runsById: Record<string, ChatRun>,
    lastError?: { message: string, at: string, action?: string }
  },
  runId?: string,
  open?: boolean
}
"parse:chat-run-created" → { runId: string, run: ChatRun }
"parse:chat-run-updated" → { runId: string, reason: string, run: ChatRun }
"parse:chat-run-finished" → { runId: string, status: string, success: boolean, run: ChatRun }
"parse:chat-history-cleared" → {}
"parse:chat-error" → { action: "send" | "cancel" | "retry", runId?: string, message: string }

// ChatRun (normalized)
ChatRun = {
  id: string,
  serverRunId: string | null,          // backend jobId for /api/chat/run
  status: "queued" | "running" | "completed" | "error" | "cancelled",
  userText: string,
  assistantText: string,
  error: string,
  canCancel: boolean,
  canRetry: boolean,
  progress: number | null,
  transcript: ChatTranscriptEntry[],
  origin: {
    mode?: "annotate" | "compare",
    speaker?: string,
    conceptId?: number | string,
    selectedSpeakers?: string[]
  }
}
```

> Scope note: these events/contracts are implemented in `js/shared/chat-*.js` and `python/server.py`, but the dock is not yet wired into `parse.html`/`compare.html` in this PR.

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
- `startChatRun(payload?) => Promise<object>`
- `pollChatRunStatus(runId, opts?) => Promise<object>`
- `cancelChatRun(runId, opts?) => Promise<object>`
- `retryChatRun(runId, opts?) => Promise<object>`
- `extractChatRunId(payload) => string | null`
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

**Chat route probing behavior (MC-246 foundation)**

- `startChatRun()` tries: `/api/chat` → `/api/chat/run` → `/api/chat/start`
- `pollChatRunStatus()` tries: `/api/chat/status` → `/api/chat/run/status` → legacy/id variants
- `cancelChatRun()` tries cancel aliases (`/api/chat/cancel`, `/api/chat/run/cancel`, `/api/chat/{id}/cancel`)
- `retryChatRun()` tries retry aliases (`/api/chat/retry`, `/api/chat/run/retry`, `/api/chat/{id}/retry`)

Canonical server routes implemented today are listed in **Server API Endpoints**.

### `window.PARSE.modules.chatToolAdapters` (`js/shared/chat-tool-adapters.js`)

**Exports**

- `normalizeStatus(rawStatus, fallback?) => string`
- `isDoneStatus(status) => boolean`
- `isActiveStatus(status) => boolean`
- `isErrorStatus(status) => boolean`
- `statusMeta(status) => { status, label, tone }`
- `extractRunId(payload) => string | null`
- `normalizeRunPayload(payload, previousRun?, hint?) => object`
- `mergeTranscriptEntries(existing, incoming) => ChatTranscriptEntry[]`
- `collectTranscriptEntries(payload) => ChatTranscriptEntry[]`
- `formatToolEntry(entry) => { id, title, status, statusLabel, tone, detail, mutating, ... }`

**Purpose / contract notes**

- Normalizes heterogeneous backend payloads into the `ChatRun` shape consumed by `chat-client`.
- Marks transcript rows as `mutating` heuristically from tool names (`save|write|update|...`) for reviewer visibility.
- Does **not** grant permissions; this is a UI adapter only.

### `window.PARSE.modules.chatClient` (`js/shared/chat-client.js`)

**Exports**

- `init(options?) => object`
- `destroy() => void`
- `getState() => ChatSessionSnapshot`
- `sendMessage(text, opts?) => Promise<string>`
- `cancelRun(runRef) => Promise<boolean>`
- `retryRun(runRef, opts?) => Promise<string>`
- `setLauncherOpen(isOpen) => void`
- `toggleLauncher() => boolean`
- `setDraft(text) => void`
- `clearHistory() => void`

**Dispatches**

- `parse:chat-state`
- `parse:chat-run-created`
- `parse:chat-run-updated`
- `parse:chat-run-finished`
- `parse:chat-history-cleared`
- `parse:chat-error`

**Consumes**

- `parse:chat-send`
- `parse:chat-cancel-run`
- `parse:chat-retry-run`
- `parse:chat-launcher`
- `parse:chat-draft`
- `parse:chat-clear-history`

**Storage / retention semantics**

- Defaults to `sessionStorage` key `parse.chat.session.v1` (falls back to `localStorage` if needed).
- Snapshot includes `sessionId`, run history, draft, launcher state, and provider/model metadata.
- On every new run, first transcript row is a client-side policy record declaring read-only MVP mode.

### `window.PARSE.modules.chatPanel` (`js/shared/chat-panel.js`)

**Exports**

- `init(options?) => object`
- `destroy() => void`
- `open() => void`
- `close() => void`
- `toggle() => void`
- `isOpen() => boolean`
- `render() => void`

**Dispatches**

- `parse:chat-send`
- `parse:chat-cancel-run`
- `parse:chat-retry-run`
- `parse:chat-launcher`
- `parse:chat-draft`

**Consumes**

- `parse:chat-state`

**DOM contract**

- Injects a fixed-position dock into the provided mount element (default `document.body`).
- Uses `data-parse-chat-dock="1"` root marker and internal `parse-chat-*` classnames.
- No static HTML placeholder required.

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
| `POST /api/chat/session` | POST | Create/get ephemeral chat session | `{ sessionId, messages[], readOnly: true, attachmentsSupported: false, limits, ... }` |
| `GET /api/chat/session/{sessionId}` | GET | Read current chat session snapshot | `{ sessionId, messages[], readOnly: true, attachmentsSupported: false, limits, ... }` |
| `POST /api/chat/run` | POST | Start assistant run (read-only MVP) | `{ jobId, runId, sessionId, status, mode: "read-only", readOnly: true, attachmentsSupported: false, readOnlyNotice, limits }` |
| `POST /api/chat/run/status` | POST | Poll chat run status/result (`jobId` or `runId` accepted in request body) | `{ jobId, runId, status, progress, result?, error?, done, success, mode: "read-only", readOnly: true, attachmentsSupported: false }` |
| `POST /api/compute/cognates` | POST | LexStat computation | `{ jobId }` |
| `POST /api/compute/offset` | POST | Auto-offset detection | `{ jobId }` |
| `POST /api/compute/spectrograms` | POST | Batch spectrograms | `{ jobId }` |
| `GET /api/enrichments` | GET | Read enrichments | `{ enrichments }` |
| `POST /api/enrichments` | POST | Write enrichments | `{ success }` |
| `GET /api/config` | GET | Read config | `{ config }` |
| `PUT /api/config` | PUT | Update config | `{ success, config }` |
| `GET /*` | GET | Static files | File content |

All long-running endpoints return immediately with `{ jobId }`.

- Canonical chat run polling endpoint is currently `POST /api/chat/run/status`.
- `ai-client` probes legacy aliases (`/api/chat`, `/api/chat/status`, `/api/chat/cancel`, etc.) for compatibility; most are intentionally not implemented in this branch.

---

## Assistant Read-Only Boundary (MC-246 / PR #5)

Defense-in-depth layers currently present in code:

1. **Route-level guardrails (`python/server.py`)**
   - `/api/chat/run` rejects attachments/file-like fields, including nested request payload keys such as `attachments`, `attachmentIds`, `files`, `fileIds`, `contextFiles`, and `context_paths`.
   - Requests cannot opt out of read-only mode (`readOnly=false`, non-`read-only` modes, and `attachmentsSupported=true` are rejected).
   - Chat routes expose explicit read-only policy metadata (`mode`, `readOnly`, `attachmentsSupported`, `readOnlyNotice`, `limits`) and `/api/chat/run/status` accepts either `jobId` or `runId`.
2. **Orchestrator policy (`python/ai/chat_orchestrator.py`)**
   - System prompt hard-codes read-only behavior and explicitly forbids mutation claims.
   - Final assistant text is post-guarded so write requests and attachment requests get an explicit read-only/no-attachments notice.
   - Tool execution is bounded by allowlist and max tool rounds.
3. **Tool allowlist + validation (`python/ai/chat_tools.py`)**
   - Only PARSE-native tools are callable (`project_context_read`, `annotation_read`, `stt_start`, `stt_status`, `cognate_compute_preview`, `cross_speaker_match_preview`, `spectrogram_preview`).
   - Tool args are schema-validated; path-based tools are constrained to project-safe roots.
   - Tool results are normalized to include `mode: "read-only"`, `readOnly: true`, and `readOnlyNotice` metadata.
   - Preview tools do not write annotation/enrichment/config files.
4. **Config coercion (`python/ai/provider.py`)**
   - Chat runtime forces OpenAI-only + `read_only=true` + `attachments_supported=false` even if config attempts to disable those constraints.
   - Chat numeric limits are coerced/clamped into sane bounds (`max_tool_rounds`, `max_history_messages`, `max_output_tokens`, `max_tool_result_chars`, `max_user_message_chars`, `max_session_messages`).
5. **UI transparency (`js/shared/chat-client.js`, `js/shared/chat-panel.js`)**
   - Every run is seeded with a read-only policy transcript entry.
   - Panel labels mode as read-only and reminds reviewers that mutating tools are disabled.

This section is the current source of truth for the read-only MVP contract in PR #5.

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

## MC-246 Assistant Foundation Scope Snapshot (for reviewers)

**Included in PR #5 (`feat/mc-246-chat-foundations`)**

- Shared assistant foundation modules:
  - `js/shared/chat-tool-adapters.js`
  - `js/shared/chat-client.js`
  - `js/shared/chat-panel.js`
- Chat helper methods in `js/shared/ai-client.js`
- Backend read-only assistant runtime:
  - `python/server.py` chat session/run routes
  - `python/ai/chat_orchestrator.py`
  - `python/ai/chat_tools.py`
  - `python/ai/provider.py` chat runtime/config normalization
- Chat config block in `config/ai_config.json`

**Intentionally deferred (NOT in this PR yet)**

- Wiring chat scripts/dock into `parse.html` and `compare.html` boot flows
- Backend cancel/retry chat run endpoints (`/api/chat/*/cancel`, `/api/chat/*/retry`)
- Attachment/context file support
- Any mutating assistant tools (annotation/config/enrichment writes)
- Full transcript fidelity from backend `toolTrace` into UI transcript rows

---

## Event Cross-reference (Wave 14 surface + MC-246 foundation)

Chat event rows below are contract-level and implemented in `js/shared/chat-*.js`, but the chat dock is still not bootstrapped in `parse.html` / `compare.html` in this PR.

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
| `parse:chat-send` | `js/shared/chat-panel.js` | `js/shared/chat-client.js` |
| `parse:chat-cancel-run` | `js/shared/chat-panel.js` | `js/shared/chat-client.js` |
| `parse:chat-retry-run` | `js/shared/chat-panel.js` | `js/shared/chat-client.js` |
| `parse:chat-launcher` | `js/shared/chat-panel.js`, `js/shared/chat-panel.js` public helpers, external callers | `js/shared/chat-client.js` |
| `parse:chat-draft` | `js/shared/chat-panel.js` | `js/shared/chat-client.js` |
| `parse:chat-clear-history` | external callers (no UI button yet) | `js/shared/chat-client.js` |
| `parse:chat-state` | `js/shared/chat-client.js` | `js/shared/chat-panel.js` |
| `parse:chat-run-created` | `js/shared/chat-client.js` | - |
| `parse:chat-run-updated` | `js/shared/chat-client.js` | - |
| `parse:chat-run-finished` | `js/shared/chat-client.js` | - |
| `parse:chat-history-cleared` | `js/shared/chat-client.js` | - |
| `parse:chat-error` | `js/shared/chat-client.js` | - |
