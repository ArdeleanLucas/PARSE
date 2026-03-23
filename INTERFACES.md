# INTERFACES.md — PARSE Module Contract v4.0

All modules attach to `window.PARSE`. Communication is via CustomEvents on `document`.

---

## Global Namespace

```js
window.PARSE = {
  // Project config (loaded from project.json on startup)
  project: null,          // parsed project.json

  // Data stores (loaded by HTML shell on page load)
  sourceIndex: null,      // parsed source_index.json
  transcripts: {},        // parsed transcripts/<Speaker>.json, keyed by speaker ID
  suggestions: null,      // parsed ai_suggestions.json
  annotations: {},        // loaded annotation data, keyed by speaker ID (from annotations/*.parse.json)

  // Module references (set by each module's init())
  modules: {
    config: null,         // project-config.js
    panel: null,          // parse.js
    waveform: null,       // waveform-controller.js
    transcript: null,     // transcript-panel.js
    suggestions: null,    // suggestions-panel.js
    spectrogram: null,    // spectrogram-worker.js (wrapper)
    regions: null,        // region-manager.js
    fullscreen: null,     // fullscreen-mode.js
    annotationStore: null,// annotation-store.js
    annotationPanel: null,// annotation-panel.js
    videoSync: null,      // video-sync-panel.js
    importExport: null,   // import-export.js
    onboarding: null,     // onboarding.js
  }
};
```

---

## Events (CustomEvent on `document`)

All events use `detail` for payload. All timestamps are in seconds (float).

### Project Lifecycle

```js
// Project config loaded and validated
// Fired by: project-config.js (on startup or after onboarding)
// Listened by: all modules (initialize with project settings)
"parse:project-loaded" → { projectId: string, projectName: string, speakers: string[], language: { code: string, name: string } }

// Project config error (missing file, invalid JSON, etc.)
// Fired by: project-config.js
// Listened by: parse.js (show error / trigger onboarding)
"parse:project-error" → { error: string, showOnboarding: boolean }
```

### Panel Lifecycle

```js
// Open PARSE panel for a speaker + concept
// Fired by: parse.js (when 🔍 button clicked)
// Listened by: waveform-controller, transcript-panel, suggestions-panel, region-manager, annotation-panel
"parse:panel-open" → { speaker: string, conceptId: string, sourceWav: string, lexiconStartSec: number }

// Close PARSE panel
// Fired by: parse.js (singleton close, or user collapse)
// Listened by: all modules (cleanup)
"parse:panel-close" → { speaker: string }
```

### Audio Navigation

```js
// Request the waveform to seek to a timestamp
// Fired by: transcript-panel (click), suggestions-panel (click), navigation buttons
// Listened by: waveform-controller
"parse:seek" → { timeSec: number, createRegion?: boolean, regionDurationSec?: number }

// Playback position update (fires continuously during playback)
// Fired by: waveform-controller
// Listened by: transcript-panel (highlight current), spectrogram (cursor), annotation-panel (field tracking)
"parse:playback-position" → { timeSec: number }

// Playback state change
// Fired by: waveform-controller
// Listened by: UI buttons
"parse:playback-state" → { playing: boolean }
```

### Region Management

```js
// Region created or updated (drag handles on waveform)
// Fired by: waveform-controller (RegionsPlugin)
// Listened by: region-manager, spectrogram (re-render), annotation-panel (update timestamp display)
"parse:region-updated" → { startSec: number, endSec: number }

// Region assigned to current concept (legacy v3 flow — still supported)
// Fired by: region-manager (when "Assign" button clicked)
// Listened by: parse.js (update form row indicator)
"parse:region-assigned" → { speaker: string, conceptId: string, startSec: number, endSec: number, sourceWav: string, aiSuggestionUsed?: number, aiSuggestionConfidence?: string, aiSuggestionScore?: number }
```

### Annotations (NEW in v4.0)

```js
// Annotation saved (user confirmed IPA/ortho/concept for a region)
// Fired by: annotation-panel.js (when "Save Annotation" clicked)
// Listened by: annotation-store.js (persist to disk), parse.js (update UI indicators)
"parse:annotation-save" → {
  speaker: string,
  conceptId: string,
  startSec: number,
  endSec: number,
  ipa: string,
  ortho: string,
  concept: string,         // format: "1:one"
  sourceWav: string,
  aiSuggestionUsed?: number,
  aiSuggestionScore?: number
}

// Annotation deleted
// Fired by: annotation-panel.js (when user removes an annotation)
// Listened by: annotation-store.js (remove from disk), parse.js (update UI)
"parse:annotation-delete" → { speaker: string, conceptId: string, startSec: number }

// Annotation loaded from disk (initial load or after import)
// Fired by: annotation-store.js
// Listened by: annotation-panel.js (populate fields), region-manager (show saved regions)
"parse:annotations-loaded" → { speaker: string, count: number }

// Annotation data changed (any modification to the annotation store)
// Fired by: annotation-store.js (after save, delete, or import)
// Listened by: parse.js (update progress indicators)
"parse:annotations-changed" → { speaker: string, totalAnnotations: number }
```

### Suggestions & Prior

```js
// AI suggestion clicked
// Fired by: suggestions-panel
// Listened by: (triggers parse:seek internally, but also logged)
"parse:suggestion-click" → { suggestionIndex: number, segmentStartSec: number, segmentEndSec: number }

// Positional prior reference speakers changed
// Fired by: suggestions-panel (speaker selector checkboxes)
// Listened by: suggestions-panel (self, re-rank)
"parse:priors-changed" → { selectedSpeakers: string[] }
```

### Transcript

```js
// Transcript segment clicked
// Fired by: transcript-panel
// Listened by: (triggers parse:seek internally)
"parse:transcript-click" → { segmentIndex: number, startSec: number }
```

### Fullscreen

```js
// Toggle fullscreen mode
// Fired by: fullscreen-mode.js (button or Escape)
// Listened by: parse.js (reparent panel into overlay)
"parse:fullscreen-toggle" → { active: boolean }

// Navigate to next/prev concept (within fullscreen)
// Fired by: fullscreen-mode.js (prev/next buttons)
// Listened by: parse.js (close current, open next)
"parse:navigate-concept" → { direction: "prev" | "next", missingOnly: boolean }
```

### Import / Export (NEW in v4.0)

```js
// TextGrid import requested
// Fired by: import-export.js (user selected a .TextGrid file)
// Listened by: annotation-store.js (parse + load)
"parse:import-textgrid" → { file: File, targetSpeaker: string, mode: "replace" | "new", newSpeakerName?: string }

// TextGrid export requested
// Fired by: import-export.js (user clicked export)
// Listened by: annotation-store.js (serialize + trigger download)
"parse:export-textgrid" → { speaker: string }

// ELAN XML export requested
// Fired by: import-export.js
// Listened by: annotation-store.js
"parse:export-elan" → { speaker: string }

// CSV export requested
// Fired by: import-export.js
// Listened by: annotation-store.js
"parse:export-csv" → { speaker: string | "all" }

// Segment audio export requested
// Fired by: import-export.js
// Listened by: annotation-store.js (collect timestamps), server-side (ffmpeg extraction)
"parse:export-segments" → { speaker: string | "all" }

// Import/export completed
// Fired by: annotation-store.js
// Listened by: import-export.js (show success/error)
"parse:io-complete" → { operation: "import" | "export", format: string, success: boolean, message?: string }
```

### Video Sync (NEW in v4.0)

```js
// Video sync initiated
// Fired by: video-sync-panel.js (user clicked "Auto-sync")
// Listened by: video-sync-panel.js (self — show progress)
"parse:video-sync-start" → { speaker: string, videoFile: string, audioFile: string, fps: number }

// Video sync progress update
// Fired by: video-sync-panel.js (during FFT processing)
// Listened by: video-sync-panel.js (update progress bar)
"parse:video-sync-progress" → { speaker: string, step: string, progress: number }

// Video sync completed — offset + drift computed
// Fired by: video-sync-panel.js (after FFT + optional AI verification)
// Listened by: video-sync-panel.js (show results for confirmation)
"parse:video-sync-result" → {
  speaker: string,
  offsetSec: number,
  driftRate: number,
  method: "fft_auto" | "manual",
  aiVerified: boolean,
  confidence: number
}

// Video sync locked by user
// Fired by: video-sync-panel.js (user confirmed sync)
// Listened by: project-config.js (save to project.json)
"parse:video-sync-locked" → {
  speaker: string,
  videoFile: string,
  offsetSec: number,
  driftRate: number,
  manualAdjustmentSec: number,
  fps: number
}

// Video clip extraction requested
// Fired by: video-sync-panel.js or import-export.js
// Listened by: server-side handler
"parse:video-extract-clips" → { speaker: string | "all" }
```

---

## Module Init Pattern

Each module exports a single `init` function. The HTML shell calls them in order.

```js
// Each module file structure:
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

  // Register module
  P.modules.moduleName = { init, destroy };
})();
```

**IMPORTANT:** v4.0 uses `window.PARSE` (not `window.SourceExplorer`). Existing v3 modules must be updated during Wave 9 integration.

---

## DOM Contract

The HTML shell provides these container elements:

```html
<!-- Main panel (parse.js manages visibility) -->
<div id="parse-panel" class="parse-panel hidden">
  <div id="parse-header"></div>
  <div id="parse-priors"></div>           <!-- suggestions-panel: speaker selector -->
  <div id="parse-suggestions"></div>      <!-- suggestions-panel: suggestion cards -->
  <div id="parse-transcript"></div>       <!-- transcript-panel: virtualized list -->
  <div id="parse-waveform"></div>         <!-- waveform-controller: wavesurfer instance -->
  <div id="parse-spectrogram"></div>      <!-- spectrogram wrapper -->
  <div id="parse-annotation"></div>       <!-- annotation-panel: IPA/ortho/concept fields -->
  <div id="parse-controls"></div>         <!-- nav buttons, region info, save/export -->
</div>

<!-- Fullscreen overlay -->
<div id="parse-fullscreen-overlay" class="parse-fullscreen hidden">
  <!-- fullscreen-mode.js manages this overlay -->
</div>

<!-- Video sync panel (shown per-speaker when video exists) -->
<div id="parse-video-sync" class="parse-video-sync hidden">
  <!-- video-sync-panel.js manages this -->
</div>

<!-- Import/Export modal -->
<div id="parse-io-modal" class="parse-modal hidden">
  <!-- import-export.js manages this -->
</div>

<!-- Onboarding wizard (shown when no project.json exists) -->
<div id="parse-onboarding" class="parse-onboarding hidden">
  <!-- onboarding.js manages this -->
</div>
```

---

## Data Schemas (for JS consumption)

### project.json

```ts
interface ProjectConfig {
  parse_version: string;
  project_id: string;
  project_name: string;
  language: {
    code: string;           // SIL ISO 639-3
    name: string;
    script: string;
    contact_languages: string[];
  };
  paths: {
    audio_original: string;
    audio_working: string;
    annotations: string;
    exports: string;
    peaks: string;
    transcripts: string;
  };
  concepts: {
    source: string;         // CSV filename
    id_column: string;
    label_column: string;
    total: number;
  };
  speakers: Record<string, {
    source_files: Array<{
      filename: string;
      is_primary: boolean;
      lexicon_start_sec: number;
    }>;
    video_files: Array<{
      filename: string;
      fps: number;
      sync_status: "unsynced" | "syncing" | "synced";
      sync?: VideoSyncData;
    }>;
    has_csv_timestamps: boolean;
    notes?: string;
  }>;
  ai: {
    enabled: boolean;
    provider: "anthropic" | "openai" | "ollama" | null;
    model: string | null;
    api_key_env?: string;
  };
  server: {
    port: number;
    host: string;
  };
}
```

### Annotation File (`annotations/<Speaker>.parse.json`)

```ts
interface AnnotationFile {
  version: 1;
  project_id: string;
  speaker: string;
  source_audio: string;
  source_audio_duration_sec: number;
  tiers: {
    ipa: IntervalTier;
    ortho: IntervalTier;
    concept: IntervalTier;
    speaker: IntervalTier;
    [customTierName: string]: IntervalTier;  // user-added tiers
  };
  metadata: {
    language_code: string;
    created: string;      // ISO 8601
    modified: string;     // ISO 8601
  };
}

interface IntervalTier {
  type: "interval";
  display_order: number;    // 1 = top (closest to spectrogram)
  intervals: Array<{
    start: number;          // seconds
    end: number;            // seconds
    text: string;
  }>;
}
```

### Video Sync Data

```ts
interface VideoSyncData {
  status: "unsynced" | "syncing" | "synced";
  offset_sec: number;
  drift_rate: number;           // seconds of drift per minute
  method: "fft_auto" | "manual";
  ai_verified: boolean;
  locked_at: string;            // ISO 8601
  manual_adjustment_sec: number;
}
```

### Timestamp → Video Mapping

```
video_time(wav_time) = (wav_time × (1 + drift_rate / 60)) + offset_sec + manual_adjustment_sec
video_frame(wav_time) = round(video_time(wav_time) × fps)
```

### source_index.json

```ts
interface SourceIndex {
  speakers: Record<string, {
    source_wavs: Array<{
      filename: string;           // relative URL path (from audio/working/)
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
    text: string;     // native script (may contain romanized mixed in)
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
  data: number[];     // interleaved min/max pairs
}
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

---

## Migration Notes (v3.0 → v4.0)

Existing v3 modules use `window.SourceExplorer` and `se:` event prefixes. During Wave 9 integration:

1. Replace `window.SourceExplorer` → `window.PARSE` in all JS files
2. Replace `se:` event prefix → `parse:` in all event names
3. Replace `se-` DOM ID prefix → `parse-` in HTML and JS
4. Wire `region-manager.js` "Assign" flow into `annotation-store.js` save
5. Replace localStorage decisions with `annotation-store.js` file persistence
6. Add `annotation-panel.js` rendering into the panel open flow

**Do NOT do this migration during waves 5-7.** New modules use `window.PARSE` and `parse:` events from the start. Old modules get migrated in Wave 9.
