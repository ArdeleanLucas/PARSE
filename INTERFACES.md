# INTERFACES.md — Source Explorer Module Contract

All modules attach to `window.SourceExplorer`. Communication is via CustomEvents on `document`.

---

## Global Namespace

```js
window.SourceExplorer = {
  // Data stores (loaded by HTML shell on page load)
  sourceIndex: null,      // parsed source_index.json
  transcripts: {},        // parsed coarse_transcripts/<Speaker>.json, keyed by speaker ID
  suggestions: null,      // parsed ai_suggestions.json
  decisions: {},          // current decisions state (read/write, persisted to localStorage)

  // Module references (set by each module's init())
  modules: {
    panel: null,          // source-explorer.js
    waveform: null,       // waveform-controller.js
    transcript: null,     // transcript-panel.js
    suggestions: null,    // suggestions-panel.js
    spectrogram: null,    // spectrogram-worker.js (wrapper)
    regions: null,        // region-manager.js
    fullscreen: null,     // fullscreen-mode.js
  }
};
```

---

## Events (CustomEvent on `document`)

All events use `detail` for payload. All timestamps are in seconds (float).

### Panel Lifecycle

```js
// Open source explorer for a speaker + concept
// Fired by: source-explorer.js (when 🔍 button clicked)
// Listened by: waveform-controller, transcript-panel, suggestions-panel, region-manager
"se:panel-open" → { speaker: string, conceptId: string, sourceWav: string, lexiconStartSec: number }

// Close source explorer
// Fired by: source-explorer.js (singleton close, or user collapse)
// Listened by: all modules (cleanup)
"se:panel-close" → { speaker: string }
```

### Audio Navigation

```js
// Request the waveform to seek to a timestamp
// Fired by: transcript-panel (click), suggestions-panel (click), navigation buttons
// Listened by: waveform-controller
"se:seek" → { timeSec: number, createRegion?: boolean, regionDurationSec?: number }

// Playback position update (fires continuously during playback)
// Fired by: waveform-controller
// Listened by: transcript-panel (highlight current), spectrogram (cursor)
"se:playback-position" → { timeSec: number }

// Playback state change
// Fired by: waveform-controller
// Listened by: UI buttons
"se:playback-state" → { playing: boolean }
```

### Region Management

```js
// Region created or updated (drag handles on waveform)
// Fired by: waveform-controller (RegionsPlugin)
// Listened by: region-manager, spectrogram (re-render for region window)
"se:region-updated" → { startSec: number, endSec: number }

// Region assigned to current concept
// Fired by: region-manager (when "Assign" button clicked)
// Listened by: source-explorer.js (update form row indicator)
"se:region-assigned" → { speaker: string, conceptId: string, startSec: number, endSec: number, sourceWav: string, aiSuggestionUsed?: number, aiSuggestionConfidence?: string, aiSuggestionScore?: number }
```

### Suggestions & Prior

```js
// AI suggestion clicked
// Fired by: suggestions-panel
// Listened by: (triggers se:seek internally, but also logged)
"se:suggestion-click" → { suggestionIndex: number, segmentStartSec: number, segmentEndSec: number }

// Positional prior reference speakers changed
// Fired by: suggestions-panel (speaker selector checkboxes)
// Listened by: suggestions-panel (self, re-rank)
"se:priors-changed" → { selectedSpeakers: string[] }
```

### Transcript

```js
// Transcript segment clicked
// Fired by: transcript-panel
// Listened by: (triggers se:seek internally)
"se:transcript-click" → { segmentIndex: number, startSec: number }
```

### Fullscreen

```js
// Toggle fullscreen mode
// Fired by: fullscreen-mode.js (button or Escape)
// Listened by: source-explorer.js (reparent panel into overlay)
"se:fullscreen-toggle" → { active: boolean }

// Navigate to next/prev missing concept (within fullscreen)
// Fired by: fullscreen-mode.js (prev/next buttons)
// Listened by: source-explorer.js (close current, open next)
"se:navigate-concept" → { direction: "prev" | "next", missingOnly: boolean }
```

---

## Module Init Pattern

Each module exports a single `init` function. The HTML shell calls them in order.

```js
// Each module file structure:
(function() {
  'use strict';

  const SE = window.SourceExplorer;

  function init(containerEl) {
    // containerEl = the DOM element this module renders into
    // Set up event listeners, render initial UI
    // Return a public API object
  }

  function destroy() {
    // Remove event listeners, clean up resources
  }

  // Register module
  SE.modules.moduleName = { init, destroy };
})();
```

---

## DOM Contract

The HTML shell provides these container elements:

```html
<div id="se-panel" class="se-panel hidden">
  <!-- source-explorer.js manages this wrapper -->
  <div id="se-header"></div>
  <div id="se-priors"></div>           <!-- suggestions-panel: speaker selector -->
  <div id="se-suggestions"></div>      <!-- suggestions-panel: suggestion cards -->
  <div id="se-transcript"></div>       <!-- transcript-panel: virtualized list -->
  <div id="se-waveform"></div>         <!-- waveform-controller: wavesurfer instance -->
  <div id="se-spectrogram"></div>      <!-- spectrogram wrapper -->
  <div id="se-controls"></div>         <!-- nav buttons, region info, assign/export -->
</div>

<div id="se-fullscreen-overlay" class="se-fullscreen hidden">
  <!-- fullscreen-mode.js manages this overlay -->
</div>
```

---

## Data Schemas (for JS consumption)

### source_index.json

```ts
interface SourceIndex {
  speakers: Record<string, {
    source_wavs: Array<{
      filename: string;           // relative URL path
      duration_sec: number;
      file_size_bytes: number;
      bit_depth: number;
      sample_rate: number;
      channels: number;
      lexicon_start_sec: number;
      is_primary: boolean;
    }>;
    peaks_file: string;           // relative URL path to peaks JSON
    transcript_file: string;      // relative URL path to transcript JSON
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
  segments: Array<{
    start: number;    // seconds
    end: number;      // seconds
    text: string;     // Kurdish script (may contain romanized mixed in)
  }>;
}
```

### ai_suggestions.json

```ts
interface AISuggestions {
  positional_anchors: Record<string, {
    concept_coverage: number;
    timestamps: Record<string, number>;   // conceptId → absolute timestamp
  }>;
  suggestions: Record<string, {           // keyed by conceptId
    concept_en: string;
    reference_forms: string[];
    speakers: Record<string, Array<{      // keyed by speaker
      source_wav: string;
      segment_start_sec: number;
      segment_end_sec: number;
      transcript_text: string;
      matched_token: string;
      confidence: "high" | "medium" | "low";
      confidence_score: number;           // 0.0-1.0 (BASE score, no positional boost)
      method: "exact_ortho_match" | "fuzzy_ortho_match" | "romanized_phonetic_match";
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
  data: number[];     // interleaved min/max pairs
}
```

### Decisions (localStorage)

```ts
interface SourceRegion {
  source_wav: string;
  start_sec: number;
  end_sec: number;
  assigned: boolean;
  replaces_segment: boolean;
  ai_suggestion_used?: number;
  ai_suggestion_confidence?: string;
  ai_suggestion_score?: number;
  notes?: string;
}

// Stored at: localStorage.getItem('se-decisions')
// Format: JSON string of Record<conceptId, { source_regions: Record<speaker, SourceRegion> }>
```

---

## Positional Re-Ranking Algorithm (client-side)

Used by `suggestions-panel.js` when the reviewer selects reference speakers.

```
Input:
  - candidate.base_score (from ai_suggestions.json)
  - candidate.segment_start_sec
  - selectedSpeakers[] (from UI checkboxes)
  - positionalAnchors (from ai_suggestions.json)
  - currentConceptId

Algorithm:
  1. For each selected speaker, look up their timestamp for currentConceptId
     (skip speakers without this concept)
  2. Compute median of these timestamps → expectedTimeSec
  3. distance = |candidate.segment_start_sec - expectedTimeSec|
  4. positionalBoost = max(0, 0.25 * (1 - distance / 120))
     // Linear decay: full 0.25 boost at distance=0, zero boost at distance≥120s
  5. finalScore = min(1.0, candidate.base_score + positionalBoost)
  6. Re-derive label: ≥0.80 = "high", 0.50-0.79 = "medium", <0.50 = "low"

If no selected speakers have a timestamp for this concept:
  finalScore = base_score (no boost applied)
```

---

## Spectrogram Web Worker Protocol

Communication between main thread and `spectrogram-worker.js`:

```js
// Main → Worker
{ type: "compute", audioData: Float32Array, sampleRate: number, windowSize: 2048|256, startSec: number, endSec: number }

// Worker → Main
{ type: "result", imageData: Uint8ClampedArray, width: number, height: number, startSec: number, endSec: number }

// Worker → Main (error)
{ type: "error", message: string }
```

The main thread extracts the audio chunk from the `<audio>` element via `AudioContext.decodeAudioData()` for ONLY the selected ≤30s window, then sends the raw PCM to the worker for FFT.
