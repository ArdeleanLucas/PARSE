# INTERFACES.md — PARSE Module Contract v5.0

All modules attach to `window.PARSE`. Communication is via CustomEvents on `document`.

---

## Global Namespace

```js
window.PARSE = {
  // Project config (loaded from project.json on startup)
  project: null,

  // Data stores
  sourceIndex: null,       // source_index.json
  transcripts: {},         // transcripts/<Speaker>.json, keyed by speaker ID
  suggestions: null,       // ai_suggestions.json
  annotations: {},         // annotation data, keyed by speaker ID
  enrichments: null,       // parse-enrichments.json (cognate sets, similarity, borrowing)
  tags: {},                // tag definitions and assignments

  // Current state
  mode: 'annotate',        // 'annotate' | 'compare'
  currentSpeaker: null,
  currentConcept: null,

  // Module references (set by each module's init())
  modules: {
    // Shared
    config: null,          // js/shared/project-config.js
    annotationStore: null, // js/shared/annotation-store.js
    tags: null,            // js/shared/tags.js
    audioPlayer: null,     // js/shared/audio-player.js
    aiClient: null,        // js/shared/ai-client.js
    spectrogram: null,     // js/shared/spectrogram-worker.js

    // Annotate mode
    panel: null,           // js/annotate/parse.js
    waveform: null,        // js/annotate/waveform-controller.js
    transcript: null,      // js/annotate/transcript-panel.js
    suggestions: null,     // js/annotate/suggestions-panel.js
    regions: null,         // js/annotate/region-manager.js
    fullscreen: null,      // js/annotate/fullscreen-mode.js
    annotationPanel: null, // js/annotate/annotation-panel.js
    videoSync: null,       // js/annotate/video-sync-panel.js
    importExport: null,    // js/annotate/import-export.js
    onboarding: null,      // js/annotate/onboarding.js

    // Compare mode
    compare: null,         // js/compare/compare.js
    conceptTable: null,    // js/compare/concept-table.js
    cognateControls: null, // js/compare/cognate-controls.js
    borrowingPanel: null,  // js/compare/borrowing-panel.js
    speakerImport: null,   // js/compare/speaker-import.js
    enrichmentsIO: null,   // js/compare/enrichments.js
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
"parse:export-wordlist" → { speakers: string[], conceptIds: number[] }  // NEW: LingPy TSV export
"parse:io-complete" → { operation, format, success, message? }
```

### Video Sync (Annotate)

```js
"parse:video-sync-start" → { speaker, videoFile, audioFile, fps }
"parse:video-sync-progress" → { speaker, step, progress }
"parse:video-sync-result" → { speaker, offsetSec, driftRate, method, aiVerified, confidence }
"parse:video-sync-locked" → { speaker, videoFile, offsetSec, driftRate, manualAdjustmentSec, fps }
"parse:video-extract-clips" → { speaker: string | "all" }
```

### Compare Mode (NEW in v5.0)

```js
// Compare mode opened
"parse:compare-open" → { speakers: string[], conceptIds: number[] }

// Compare mode closed
"parse:compare-close" → {}

// Speaker added to comparison
"parse:compare-speaker-add" → { speaker, importMode: "raw" | "existing" | "manual" }

// Speaker removed from comparison
"parse:compare-speaker-remove" → { speaker }
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
"parse:cognates-changed" → { conceptId, groups: Record<string, string[]> }
```

### Borrowing (NEW in v5.0)

```js
// Borrowing status changed for a speaker's form
"parse:borrowing-changed" → { conceptId, speaker, status: "confirmed" | "not_borrowing" | "undecided" }

// Borrowing handling decision
"parse:borrowing-handle" → { conceptId, speaker, handling: "missing" | "separate_cognate" }
```

### Enrichments (NEW in v5.0)

```js
// Computation requested
"parse:compute-request" → {
  type: "cognates" | "offset" | "spectrograms",
  speakers: string[],
  conceptIds: number[],
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
"parse:enrichments-updated" → { computedAt, speakers: string[], concepts: number[] }
```

### AI / STT (NEW in v5.0)

```js
// Full-file STT requested for new speaker
"parse:stt-request" → { speaker, sourceWav, language?, model? }

// STT job started
"parse:stt-started" → { jobId, speaker, estimatedDuration? }

// STT progress
"parse:stt-progress" → { jobId, speaker, progress: number, segmentsProcessed: number }

// STT completed
"parse:stt-done" → { jobId, speaker, success: boolean, totalSegments?: number, error?: string }

// Cross-speaker match results available
"parse:match-results" → { speaker, matches: Array<{ conceptId, candidates: Array<{ startSec, endSec, ipa, ortho, confidence }> }> }
```

---

## Module Init Pattern

Each module exports `init` and `destroy`. The HTML shell calls them in order.

```js
(function() {
  'use strict';
  const P = window.PARSE;

  function init(containerEl) {
    // containerEl = the DOM element this module renders into
    // Set up event listeners, render initial UI
    // Return a public API object
  }

  function destroy() {
    // Remove event listeners, clean up resources
  }

  P.modules.moduleName = { init, destroy };
})();
```

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
