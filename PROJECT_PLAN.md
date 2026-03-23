# Source Explorer — Detailed Build Plan

**Version:** 2.0  
**Date:** 2026-03-23  
**Status:** Planning  
**Author:** Dr-Kurd Agent  
**Changelog:** v2.0 — incorporated sub-agent review feedback (wavesurfer backend fix, timeline recalibration, schema gaps, fuzzy matching tightening, UX improvements)

---

## 1. Problem Statement

The current Review Tool (RT) v4.3 plays pre-cut `.wav` segments per concept × speaker. This works for clean data but fails for:

1. **Multi-iteration segments** — file contains several repetitions of the word; reviewer needs to pick the cleanest one (e.g., Fail01 "one", Khan03 "one" with 3+ repetitions)
2. **Bad cuts** — segment straddles two iterations with no complete word (e.g., Khan01 "one" — half of iteration 1 + half of iteration 2)
3. **Missing data** — speaker has `?` for a concept, but the word may exist somewhere in the source recording and was just missed by the pipeline (e.g., Fail02: 71/82 missing, Khan04: 81/82 missing)
4. **Noisy ortho transcriptions** — Whisper repetition artefacts like "ژ ژ ژ ژ ژ" make text unreliable
5. **Context switching** — manually opening Audacity/Praat per speaker per concept is extremely time-consuming

### Missing data scale

| Speaker | Missing / Total | Source WAVs available |
|---------|-----------------|----------------------|
| Fail01  | 6 / 82          | Faili_M_1984.wav |
| Fail02  | 71 / 82         | SK_Faili_F_1968.wav |
| Kalh01  | 2 / 82          | Kalh_M_1981.wav |
| Khan01  | 9 / 82          | REC00002.wav (primary), 2023043001.wav, 20230502_khanaqini_01_02.wav |
| Khan02  | 1 / 82          | khanaqini_F_1967.wav |
| Khan03  | 6 / 82          | C0401_audio.wav, C0402_audio.wav, C0403_audio.wav |
| Khan04  | 81 / 82         | Khanaqin_F_2000.wav |
| Mand01  | 0 / 82          | Mandali_M_1900_01.wav |
| Qasr01  | 0 / 82          | Qasrashirin_M_1973.wav |
| Saha01  | 0 / 82          | Sahana_F_1978.wav |

---

## 2. Goals

1. **Eliminate Praat/Audacity context-switching** — all audio review happens inside the RT
2. **Enable region selection** — reviewer can trim, re-cut, and re-assign segments from within the UI
3. **AI-assisted concept finding** — for missing/broken items, suggest timestamps where the target word likely occurs based on coarse transcript matching
4. **Source audio browsing** — waveform + spectrogram + transcript timeline for full source recordings
5. **Export corrected boundaries** — output JSON of reviewer's trim decisions for batch re-extraction

---

## 3. Architecture

### 3.1 Hosting

- **Dev RT** — local Python server on `C:\Users\Lucas\Thesis\`, port 8766
- **Final RT** — GitHub Pages (gh-pages branch), uses only pre-cut corrected segments
- Source Explorer features are **dev-only** (require local server for source WAV access)

### 3.2 File Layout

```
C:\Users\Lucas\Thesis\
├── Audio_Original/                        ← source WAVs (served via HTTP range requests)
│   ├── Fail01/Faili_M_1984.wav           (varies, 30-200 min each)
│   ├── Fail02/SK_Faili_F_1968.wav
│   ├── Kalh01/Kalh_M_1981.wav
│   ├── Khan01_missing/REC00002.wav       (primary for Khan01)
│   ├── Khan02_missing/khanaqini_F_1967.wav
│   ├── Khan03_missing/C0401_audio.wav    (+ C0402, C0403)
│   ├── Khan04_missing/Khanaqin_F_2000.wav
│   ├── Mand01/Mandali_M_1900_01.wav
│   ├── Qasr01/Qasrashirin_M_1973.wav
│   └── Saha01/Sahana_F_1978.wav
│
├── Audio_Processed/                       ← pre-cut segments (existing)
│   ├── Fail01_process/segments/*.wav
│   ├── ...
│
├── peaks/                                 ← pre-generated waveform peaks (NEW)
│   ├── Fail01.json
│   ├── Fail02.json
│   ├── ...
│   └── Saha01.json
│
├── source_index.json                      ← speaker→WAV mapping, offsets, metadata
├── coarse_transcripts/                    ← per-speaker transcript JSONs
│   ├── Fail01.json
│   ├── ...
│   └── Saha01.json
├── ai_suggestions.json                    ← pre-computed concept→speaker candidates
├── review_data.json                       ← existing (v4)
├── review_tool_dev.html                   ← dev version with source explorer
├── review_tool.html                       ← production version (no source explorer)
├── thesis_server.py                       ← range-request-capable server (NEW)
└── Start Review Tool.bat                  ← upgraded server script
```

### 3.3 Data Files to Generate

#### `source_index.json`

Maps each speaker to their source WAV(s), metadata, and peaks file.

```json
{
  "speakers": {
    "Fail01": {
      "source_wavs": [
        {
          "filename": "Audio_Original/Fail01/Faili_M_1984.wav",
          "duration_sec": 7200.0,
          "file_size_bytes": 635000000,
          "bit_depth": 16,
          "sample_rate": 44100,
          "channels": 1,
          "lexicon_start_sec": 506,
          "is_primary": true
        }
      ],
      "peaks_file": "peaks/Fail01.json",
      "transcript_file": "coarse_transcripts/Fail01.json",
      "has_csv": true,
      "notes": "offset_sec and lexicon_start_sec are identical for this speaker"
    },
    "Khan01": {
      "source_wavs": [
        {
          "filename": "Audio_Original/Khan01_missing/REC00002.wav",
          "duration_sec": 8580.0,
          "file_size_bytes": 757000000,
          "bit_depth": 16,
          "sample_rate": 44100,
          "channels": 1,
          "lexicon_start_sec": 1270,
          "is_primary": true
        },
        {
          "filename": "Audio_Original/Khan01_missing/2023043001.wav",
          "duration_sec": 5220.0,
          "file_size_bytes": 461000000,
          "bit_depth": 16,
          "sample_rate": 44100,
          "channels": 1,
          "lexicon_start_sec": 1034,
          "is_primary": false
        }
      ],
      "peaks_file": "peaks/Khan01_REC00002.json",
      "transcript_file": "coarse_transcripts/Khan01_REC00002.json",
      "has_csv": true
    },
    "Khan03": {
      "source_wavs": [
        {
          "filename": "Audio_Original/Khan03_missing/C0401_audio.wav",
          "duration_sec": 6241.0,
          "file_size_bytes": 551000000,
          "bit_depth": 16,
          "sample_rate": 44100,
          "channels": 1,
          "lexicon_start_sec": 465,
          "is_primary": true
        }
      ],
      "peaks_file": "peaks/Khan03.json",
      "transcript_file": "coarse_transcripts/Khan03.json",
      "has_csv": false,
      "notes": "No CSV — positional prior unavailable. Use Khan01/Khan02 JBIL sequence as reference."
    }
  }
}
```

**Schema notes:**
- `lexicon_start_sec` = where the JBIL word list begins in the recording. For most speakers this equals the previously tracked "offset_sec" (merged into single field for clarity).
- `bit_depth`, `sample_rate`, `channels` — populated by `ffprobe` during data prep. Any 24-bit or 32-bit float files must be transcoded to 16-bit PCM before use (browser `decodeAudioData()` may silently fail on non-16-bit WAVs).
- `file_size_bytes` — used by client to warn about long decode times before loading.

#### `peaks/<Speaker>.json`

Pre-generated waveform peaks for wavesurfer.js MediaElement backend. Generated by Python script using `wave` + `numpy` (or `audiowaveform` CLI).

```json
{
  "version": 2,
  "channels": 1,
  "sample_rate": 44100,
  "samples_per_pixel": 441,
  "bits": 16,
  "length": 16326,
  "data": [0.0, 0.12, -0.05, 0.34, ...]
}
```

**Why peaks are needed:** wavesurfer.js v7's default WebAudio backend fetches the *entire* file via `fetch()` + `decodeAudioData()`. For 500MB+ WAVs, this is unusable. The MediaElement backend (`<audio>` element) supports native browser range requests for seeking/playback, but cannot render waveforms from the raw PCM. Pre-generated peaks solve this: the waveform renders from the lightweight peaks JSON while playback uses the `<audio>` element with range requests.

**Generation:** ~100 samples/sec (samples_per_pixel=441 at 44.1kHz). A 2-hour recording = ~720K peak values ≈ 2–4MB JSON. Acceptable.

#### `coarse_transcripts/<Speaker>.json`

Reformatted from `alignment/*_coarse.json`. Simplified schema:

```json
{
  "speaker": "Mand01",
  "source_wav": "Audio_Original/Mand01/Mandali_M_1900_01.wav",
  "duration_sec": 11924.0,
  "segments": [
    {"start": 0, "end": 3, "text": "سەەە بۊ دەی بەی ەسە جەمش مەێن"},
    {"start": 15, "end": 18, "text": "نیشن نەتنیشن هەیشنم یەک"},
    ...
  ]
}
```

Each segment has `start` (seconds), `end` (seconds), `text` (Kurdish script, romanized by Whisper turbo).

`duration_sec` at top level = total recording duration (from `ffprobe`), so the client doesn't have to infer it from the last segment's `end` time.

Current coarse transcripts: **11 files**, total ~800 segments per speaker (3-second windows every 15 seconds).

#### `ai_suggestions.json`

Pre-computed fuzzy matches for every concept × speaker combination.

```json
{
  "suggestions": {
    "1": {
      "concept_en": "one",
      "reference_forms": ["jek", "yek", "jak", "yak", "یەک"],
      "speakers": {
        "Fail02": [
          {
            "source_wav": "Audio_Original/Fail02/SK_Faili_F_1968.wav",
            "segment_start_sec": 337.2,
            "segment_end_sec": 340.2,
            "transcript_text": "نیشن نەتنیشن هەیشنم یەک",
            "matched_token": "یەک",
            "confidence": "high",
            "confidence_score": 0.92,
            "method": "exact_ortho_match",
            "note": "timestamp is segment start, not word start — word occurs within 3s window"
          },
          {
            "source_wav": "Audio_Original/Fail02/SK_Faili_F_1968.wav",
            "segment_start_sec": 892.1,
            "segment_end_sec": 895.1,
            "transcript_text": "ئە ئەجەک دو سە",
            "matched_token": "جەک",
            "confidence": "medium",
            "confidence_score": 0.61,
            "method": "fuzzy_ortho_match"
          }
        ],
        "Khan04": [ ... ]
      }
    }
  }
}
```

**Matching strategy (for pre-computation):**

Pre-computation generates **base match scores only** (no positional weighting). Positional re-ranking is applied **client-side** based on the reviewer's selected reference speakers.

1. **Exact orthographic match** — tokenize coarse transcript on whitespace/diacritics, check each token independently against Kurdish reference forms (handles script mixing where Whisper outputs both Arabic-script and romanized forms in the same segment)
2. **Fuzzy orthographic match** — Levenshtein distance **≤1 for words ≤4 chars**, **≤2 for words >4 chars** (tighter than v1 — prevents near-random matches on short Kurdish words like `یەک`)
3. **Romanized phonetic match** — normalize IPA from other speakers (e.g., `jek` → regex `[jy][aæeɛ][kgq]`) and match against romanized transcript tokens

**Base confidence scoring (pre-computed, no positional weighting):**
   - `base_score` 0.70–1.0 = exact ortho match
   - `base_score` 0.40–0.69 = fuzzy ortho match
   - `base_score` 0.20–0.39 = phonetic-only match
   - Below 0.20 = not included in suggestions

**Positional re-ranking (client-side):**
   - Applied on top of `base_score` using reviewer-selected reference speakers
   - For each concept, the client computes the **median expected timestamp** from selected speakers' known positions (from `positional_anchors`)
   - Proximity boost: Gaussian-like weight — candidates within ±30s of expected position get up to +0.25 boost; candidates >120s away get no boost
   - Final `confidence_score` = `base_score` + positional boost (capped at 1.0)
   - Labels derived from final score: `high` (≥0.80), `medium` (0.50–0.79), `low` (0.20–0.49)
   - Changing reference speakers instantly re-ranks without reloading

**Positional anchor data (in `ai_suggestions.json`):**

```json
{
  "positional_anchors": {
    "Mand01": {
      "concept_coverage": 82,
      "timestamps": {
        "1": 2.3,
        "2": 35.7,
        "3": 68.1,
        ...
      }
    },
    "Fail02": {
      "concept_coverage": 11,
      "timestamps": {
        "1": 337.2,
        "44": 892.1
      }
    }
  }
}
```

Each speaker's `timestamps` maps concept ID → absolute timestamp in their source recording where that concept was elicited. Derived from CSV segment data + lexicon_start_sec. Speakers with very low coverage (Fail02: 11/82, Khan04: 1/82) are available but shown as dimmed/low-confidence in the UI selector.

**Important:** `segment_start_sec` is the coarse transcript segment start, NOT the precise word onset. The matched token occurs somewhere within the 3-second window. The reviewer must listen and fine-tune the region.

---

## 4. UI Design

### 4.1 Source Explorer Panel

Added as a **collapsible panel** per form row in the main RT. Activated by a 🔍 button next to each speaker row.

**Global singleton enforcement:** Only ONE source explorer panel can be open at a time. Opening a new one automatically closes (and destroys the wavesurfer instance of) the previous one. This prevents memory blowout from multiple large audio buffers.

**Full-width layout:** The source explorer panel breaks out of the form column width and renders at **100% viewport width** (minus padding). This ensures the waveform and spectrogram have enough horizontal resolution, even on 1366px laptops.

```
┌────────────────────────────────────────────────────────────────────────┐
│ Fail02 — Concept "one" (#1)                     [?] Missing           │
│                                                                        │
│ 🔍 Source Explorer                            ▼ Collapse    [⛶ Full]  │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ Source: SK_Faili_F_1968.wav (87 min, 153MB)   Lexicon starts: 335s │ │
│ │                                                                    │ │
│ │ Positional prior: [☑ Mand01] [☑ Qasr01] [☑ Saha01] [☑ Khan02]   │ │
│ │                   [☑ Kalh01] [☑ Fail01] [☐ Fail02⚠] [☐ Khan04⚠] │ │
│ │                                                                    │ │
│ │ ┌── AI Suggestions ──────────────────────────────────────────────┐ │ │
│ │ │ 🤖 1. ~337s — "...هەیشنم یەک" — HIGH 0.92 (exact)       [▶]  │ │ │
│ │ │ 🤖 2. ~892s — "...ئەجەک دو سە" — MED 0.61 (fuzzy)      [▶]  │ │ │
│ │ │ 🤖 3. ~1204s — "...یەکەم..." — LOW 0.35 (partial)       [▶]  │ │ │
│ │ └────────────────────────────────────────────────────────────────┘ │ │
│ │                                                                    │ │
│ │ ┌── Transcript Timeline (virtualized, ~20 visible) ─────────────┐ │ │
│ │ │ 335.0s │ نیشن نەتنیشن هەیشنم یەک                              │ │ │
│ │ │ 350.0s │ دو سە چوار                                  ← current │ │ │
│ │ │ 365.0s │ پێنج شەش حەوت                                         │ │ │
│ │ │ 380.0s │ هەشت نۆ دە                                            │ │ │
│ │ │ [🔍 Search transcript...]                                       │ │ │
│ │ └────────────────────────────────────────────────────────────────┘ │ │
│ │                                                                    │ │
│ │ ┌── Waveform (from pre-generated peaks) ─────────────────────────┐ │ │
│ │ │ ▁▂▃█▇▅▃▁▁▁▂▅██▇▃▁▁▂▃▅▇█▇▅▃▁▁▁▂▃██▇▅▃▂▁▁▁▂▃▅▇█▇▅▃▁▁      │ │ │
│ │ │      [========]  ← draggable region                             │ │ │
│ │ │  335s    340s    345s    350s    355s    360s    365s           │ │ │
│ │ └────────────────────────────────────────────────────────────────┘ │ │
│ │                                                                    │ │
│ │ ┌── Spectrogram (on-demand, ≤30s window) ────────────────────────┐ │ │
│ │ │  5000 Hz ─┬─────────────────────────────────────────────────── │ │ │
│ │ │           │ [computed via Web Worker FFT — narrow-band default] │ │ │
│ │ │     0 Hz ─┴─────────────────────────────────────────────────── │ │ │
│ │ │  335s    340s    345s    350s    355s    360s    365s           │ │ │
│ │ └────────────────────────────────────────────────────────────────┘ │ │
│ │                                                                    │ │
│ │ ◄◄ -30s  ◄ -5s   ▶ Play Region   +5s ►  +30s ►►  🔄 Loop       │ │
│ │                                                                    │ │
│ │ Region: 337.2s → 338.1s (0.9s)                                    │ │
│ │ [✓ Assign to this concept]  [Export as WAV clip]                   │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Full-Screen Source Explorer Mode

For heavy investigation sessions (Fail02: 71 missing, Khan04: 81 missing), the inline panel is too cramped. A **[⛶ Full]** button toggles the source explorer into a **modal overlay** that fills the viewport.

- Same controls as inline, but with more space for waveform zoom and transcript browsing
- Overlay closes with Escape or a close button
- Current concept context shown in overlay header
- Prev/Next concept navigation within the overlay (skip to next missing concept)
- Estimated addition: ~1.5 hours on top of base inline implementation

### 4.3 Feature Breakdown

#### A. Waveform Display
- **Library:** [wavesurfer.js](https://wavesurfer-js.org/) v7 (MIT, 27KB gzipped)
- **Backend: MediaElement** (NOT default WebAudio) — uses `<audio>` element for playback, which supports native browser range requests for seeking without downloading the full file
- **Waveform rendering:** From **pre-generated peaks JSON** (`peaks/<Speaker>.json`), NOT from raw PCM decode. This is the accepted pattern for large files with wavesurfer.
- **Plugins:** `RegionsPlugin` (draggable region selection), `TimelinePlugin` (time axis)
- **Initial position:** Jump to `lexicon_start_sec` (or AI suggestion timestamp) on open
- **Zoom:** Mouse wheel on waveform

#### B. Spectrogram Display
- **Computed via Web Worker** to avoid UI freezing
- **Hard-capped to ≤30s window** — spectrogram is computationally expensive; no full-recording rendering
- Narrow-band (window=2048, for formant visibility) or wide-band (window=256, for temporal detail)
- **Toggle:** On-demand only, renders for the currently visible/selected window
- Greyscale to match existing static spectrograms

#### C. Transcript Timeline
- Rendered from `coarse_transcripts/<Speaker>.json`
- **Virtualized list** — only ~20 DOM elements visible at a time, recycled on scroll (prevents sluggishness with 800+ segments)
- Click → seeks waveform to that position
- **Highlight current segment** as audio plays
- **Search within transcript** — type Kurdish text or romanized form, matching segments highlighted and scrolled to

#### D. AI Suggestions
- Loaded from `ai_suggestions.json` for current concept × speaker
- Ranked by `confidence_score` (numeric), displayed with confidence label + score
- Click → seek + create region at `segment_start_sec`
- Reviewer verifies by listening, then adjusts region handles to isolate the word
- **Fetch cancellation:** Uses `AbortController` — if the user rapidly clicks through suggestions, previous pending fetches are cancelled to prevent race conditions

#### D2. Positional Prior — Speaker Selector
- **UI control:** Multi-select dropdown/checkbox list at the top of the Source Explorer panel: "Reference speakers for positional prior"
- Default: all speakers with CSV data and ≥50% concept coverage (typically Mand01, Qasr01, Saha01, Khan02, Kalh01, Fail01)
- Reviewer can toggle individual speakers on/off as positional references
- **How it works:**
  - `ai_suggestions.json` stores all candidates with their **base match score** (ortho/fuzzy/phonetic only — no positional weighting baked in)
  - Each candidate also stores `segment_start_sec` (its raw timestamp in the source recording)
  - The client loads the selected reference speakers' known concept timestamps from `positional_anchors` in `ai_suggestions.json`
  - Client-side re-ranking: for each candidate, compute distance to the **median expected timestamp** across selected reference speakers, apply a Gaussian-like proximity boost (±30s window), produce the final `confidence_score`
  - Changing the speaker selection **instantly re-ranks** suggestions without reloading data
- **Why this matters:** Geographically closer varieties may have more similar elicitation pacing. The reviewer knows which speakers are most relevant for a given target — e.g., Khan02's timing may be a better prior for Khan04 than Saha01's
- **Persistence:** Selected reference speakers saved to localStorage per target speaker

#### E. Navigation Controls
- **Skip buttons:** -30s, -5s, +5s, +30s
- **Jump to next/prev transcript segment** (skips silence)
- **Jump to AI suggestion #N**
- **Keyboard shortcuts:** Space = play/pause, Left/Right = ±1s, Shift+Left/Right = ±5s, Escape = close panel
- **Zoom:** Mouse wheel on waveform zooms in/out

#### F. Region Selection & Assignment
- Draggable start/end handles on the waveform (wavesurfer `RegionsPlugin`)
- **"Play Region"** — plays only the selected portion
- **"Loop Region"** — repeats selected portion
- **"Assign to concept"** — saves `{speaker, concept_id, source_wav, start_sec, end_sec}` into decisions JSON
- **"Export as WAV"** — Web Audio API `OfflineAudioContext` to render region as downloadable file (or save to decisions for batch server-side extraction)
- Supports marking **multiple regions** (for variant A, B selection from different iterations)

### 4.4 Integration with Existing RT

The source explorer is **not a separate page** — it's a panel that expands within the existing form row (or modal overlay). This means:

- All existing review features (accept/flag, cognate sets, notes, phonetic flags) work alongside
- Source explorer state (region, assignment) is saved into the same `decisions` JSON
- On export, source explorer assignments are included

### 4.5 Decisions JSON Schema Extension

```json
{
  "concept_id": "1",
  "status": "reviewed",
  "notes": "Used AI suggestion #1, trimmed to 337.2-338.1s",
  "source_regions": {
    "Fail02": {
      "source_wav": "Audio_Original/Fail02/SK_Faili_F_1968.wav",
      "start_sec": 337.2,
      "end_sec": 338.1,
      "assigned": true,
      "replaces_segment": true,
      "ai_suggestion_used": 1,
      "ai_suggestion_confidence": "high",
      "ai_suggestion_score": 0.92
    },
    "Khan01": {
      "source_wav": "Audio_Original/Khan01_missing/REC00002.wav",
      "start_sec": 1285.4,
      "end_sec": 1286.1,
      "assigned": true,
      "replaces_segment": true,
      "notes": "iteration 2, cleaner than iteration 1"
    }
  }
}
```

---

## 5. Server Requirements

### 5.1 HTTP Range Request Support

The current `Start Review Tool.bat` uses Python's `http.server`. This does NOT support range requests by default, which means:
- Browser must download the entire WAV before seeking (500MB+ per file)
- Unusable for large files

**Fix:** Custom `thesis_server.py` with range request support:
- Extends `SimpleHTTPRequestHandler` to handle `Range` headers (~50 lines)
- Returns 206 Partial Content with correct `Content-Range` headers
- CORS headers for JS audio decoding
- Binds to `0.0.0.0:8766` (accessible via Tailscale too)
- **Windows path handling:** Uses `os.path.join()` throughout (forward-slash URL paths → Windows backslash filesystem paths handled by Python's `pathlib`)

### 5.2 Updated Batch File

```bat
@echo off
echo Starting SK Review Tool server on port 8766...
cd /d "C:\Users\Lucas\Thesis"
python thesis_server.py
```

---

## 6. Build Steps (Ordered)

### Phase 0: WAV Audit (est. 30 min)

0. **Run `ffprobe` on all source WAVs**
   - Verify bit depth (must be 16-bit PCM), sample rate, channels, duration, file size
   - If any files are 24-bit or 32-bit float → transcode to 16-bit PCM with `ffmpeg -i input.wav -acodec pcm_s16le -ar 44100 output_16bit.wav`
   - If any files are multi-channel (>2) → downmix to mono with `ffmpeg -ac 1`
   - Record results in `source_index.json` metadata fields
   - This step MUST complete before anything else — prevents silent failures later

### Phase 1: Data Preparation (est. 2.5 hours)

1. **Generate `source_index.json`**
   - Map each speaker → source WAV path(s), duration, file size, bit depth, channels, sample rate, lexicon start
   - Use verified offsets from `alignment/offsets.json` + memory
   - Special handling for Khan01 (3 WAVs), Khan03 (3 WAVs, no CSV)
   - **Est: 20 min**

2. **Pre-generate peaks JSON files**
   - Python script: read each WAV with `wave` module, compute min/max peaks at ~100 samples/sec (samples_per_pixel = sample_rate / 100)
   - Output to `peaks/<Speaker>.json` in wavesurfer-compatible format
   - ~2–4MB per file for 2-hour recordings
   - **Est: 30 min** (script + run time for all 10 speakers)

3. **Reformat coarse transcripts**
   - Copy and simplify `alignment/*_coarse.json` → `coarse_transcripts/<Speaker>.json`
   - Normalize schema: `{speaker, source_wav, duration_sec, segments: [{start, end, text}]}`
   - For Khan01: merge transcripts from the primary WAV (REC00002.wav)
   - For Khan03: use C0401 turbo transcript (already in `Khan03_turbo/`)
   - **Est: 20 min**

4. **Generate `ai_suggestions.json`**
   - For each concept × speaker:
     - Collect reference forms from other speakers (ortho + IPA) via `review_data.json`
     - Tokenize coarse transcript on whitespace/diacritics (handles script mixing)
     - Match tokens: exact → fuzzy (Levenshtein ≤1 for ≤4 chars, ≤2 for >4 chars) → phonetic regex
     - Apply positional prior where CSV anchors exist (skip for Fail02/Khan04 — insufficient anchors)
     - Score candidates numerically (0.0–1.0), assign label (high/medium/low)
     - Output top 5 candidates per concept × speaker
   - **Est: 1.5 hours** (script development + debugging + validation of ~656K comparisons)

5. **Copy data files to `C:\Users\Lucas\Thesis\`**
   - `source_index.json`, `peaks/`, `coarse_transcripts/`, `ai_suggestions.json`
   - **Est: 5 min**

### Phase 2: Server Upgrade (est. 30 min)

6. **Write `thesis_server.py`** — Range-request-capable HTTP server with CORS
7. **Update `Start Review Tool.bat`** to use new server
8. **Test:** Verify range requests work — seek to middle of Khan02's 3:10:00 recording, confirm no full download

### Phase 3: UI — Waveform & Basic Controls (est. 3.5 hours)

9. **Add wavesurfer.js v7** to the RT (CDN or local copy)
   - Configure **MediaElement backend** with pre-generated peaks
   - Add RegionsPlugin, TimelinePlugin

10. **Add 🔍 button** per form row → opens source explorer panel
    - **Global singleton logic:** Close previous panel + destroy wavesurfer instance before opening new one

11. **Implement waveform loading:**
    - Load source WAV URL from `source_index.json`
    - Load peaks from `peaks/<Speaker>.json`
    - Initialize wavesurfer with `backend: 'MediaElement'` + `peaks` data
    - Initial position = lexicon start time (or segment timestamp if exists)
    - Display file size warning if >200MB

12. **Navigation controls:**
    - Skip buttons: -30s, -5s, +5s, +30s
    - Keyboard: Space, Left/Right, Shift+arrows, Escape
    - **AbortController** for rapid seek cancellation

13. **Region selection:**
    - wavesurfer `RegionsPlugin` — drag to create/adjust region
    - Play Region button, Loop toggle
    - Display region timestamps + duration

### Phase 4: UI — Transcript & AI Suggestions (est. 2.5 hours)

14. **Transcript timeline panel:**
    - Load from `coarse_transcripts/<Speaker>.json`
    - **Virtualized scrollable list** — render only ~20 DOM elements, recycle on scroll
    - Click to seek
    - Highlight current segment during playback
    - Search/filter box (Kurdish text or romanized)

15. **AI suggestions panel:**
    - Load from `ai_suggestions.json` for current concept × speaker
    - Ranked cards with confidence badge + numeric score
    - Click → seek + create region at suggestion timestamp
    - Note: "timestamps are segment starts (~3s window, listen to locate word)"

16. **Spectrogram panel (on-demand):**
    - Computed via **Web Worker** to prevent UI freeze
    - **Hard-capped to ≤30s window**
    - Toggle button, only renders for visible window
    - Greyscale, narrow-band default

### Phase 5: Assignment & Export (est. 1.5 hours)

17. **"Assign to concept" button:**
    - Saves region boundaries + source WAV path + AI suggestion metadata into decisions JSON
    - Visual indicator: form row shows "✓ re-assigned from source"

18. **Export extension:**
    - Export JSON includes `source_regions` per concept (with `ai_suggestion_confidence` field)
    - Separate "Export re-cut list" → JSON of all regions that need re-extraction

19. **Batch re-extraction script (Python):**
    - Reads export JSON
    - Uses ffmpeg to cut new segments from source WAVs
    - Re-generates spectrograms for new segments
    - Updates `review_data.json` with new paths

### Phase 6: Full-Screen Mode (est. 1.5 hours)

20. **[⛶ Full] button** → opens modal overlay with same controls
    - Full viewport width for waveform/spectrogram
    - Prev/Next missing concept navigation within overlay
    - Escape to close

### Phase 7: Polish & Integration (est. 1 hour)

21. **State persistence** — save source explorer state to localStorage
22. **Loading states** — skeleton/spinner while peaks load and audio connects
23. **Error handling** — graceful failure if source WAV missing, if peaks file missing, if bit depth unsupported
24. **Feature detection** — hide source explorer if not running on local server (no source WAVs on gh-pages)

---

## 7. Dependencies

| Dependency | Version | Size | Purpose |
|------------|---------|------|---------|
| wavesurfer.js | v7.x | 27KB gz | Waveform (MediaElement backend), regions, timeline |
| wavesurfer Regions Plugin | v7.x | 5KB gz | Draggable region selection |
| wavesurfer Timeline Plugin | v7.x | 3KB gz | Time axis display |

**Removed from v1:** wavesurfer Spectrogram Plugin — replaced with custom Web Worker FFT (more control over window size cap).

All MIT licensed. Can be loaded from CDN or bundled locally.

**Data prep scripts** require: Python 3.8+ with `wave`, `struct`, `json`, `numpy` (for peaks generation). No server-side dependencies beyond Python stdlib for the HTTP server.

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| WAV files are 24-bit or 32-bit float | `decodeAudioData()` silently fails | **Phase 0:** ffprobe audit, transcode to 16-bit PCM |
| WAV files are multi-channel (>2ch) | `decodeAudioData()` fails beyond stereo | **Phase 0:** ffprobe audit, downmix to mono |
| Large WAV load time via MediaElement | Slow initial seek | Pre-generated peaks for instant waveform; `<audio>` handles range-request seeking natively |
| Client-side spectrogram slow for large windows | UI freezes | **Hard cap ≤30s window**; compute in **Web Worker** |
| Multiple source explorers opened simultaneously | Browser OOM | **Global singleton** — auto-close previous, destroy wavesurfer instance |
| Concurrent fetch collisions from rapid clicking | Waveform thrash, stale audio | **AbortController** cancels pending fetches on new seek |
| Coarse transcripts are low quality (turbo model, 3s windows) | AI suggestions miss targets | Multiple matching strategies; reviewer verifies; script mixing handled by per-token matching |
| Whisper script mixing (Arabic + romanized in same segment) | Exact match misses romanized forms | Tokenize on whitespace, check each token independently |
| Levenshtein too loose on short Kurdish words | False positive matches | **≤1 for words ≤4 chars, ≤2 for >4 chars** |
| Fail02/Khan04 have no positional prior | AI suggestions less accurate | Fall back to transcript-only matching; flag as "no positional prior" |
| Khan03 has no CSV | Positional prior unavailable | Use Khan01/Khan02 JBIL sequence as reference |
| wavesurfer range request support | MediaElement may buffer differently per browser | Test with custom server; verify Chrome + Firefox behavior |
| 800+ transcript segments as DOM elements | Sluggish UI | **Virtualized list** — only ~20 DOM elements rendered |
| Windows path separators in server | Path join failures | Use `pathlib` / `os.path.join()` throughout |
| Waveform too narrow in inline panel | Spectrogram unreadable on small screens | **Full-width panel** (100vw minus padding) + **full-screen mode toggle** |

---

## 9. Future Enhancements (Not in Scope)

- **Video clip integration** — sync video files, extract mouth-view clips per segment
- **Praat TextGrid export** — export region selections as Praat-compatible TextGrids
- **Real-time AI matching** — call LLM to analyze unfound segments (requires agent online)
- **Collaborative annotations** — multiple reviewers, conflict resolution
- **Formant overlay** — LPC analysis on spectrogram (complex, may not be worth the JS cost)

---

## 10. Definition of Done

The source explorer is complete when:

- [ ] All source WAVs audited with `ffprobe` — bit depth, channels, sample rate confirmed 16-bit PCM mono/stereo
- [ ] Pre-generated peaks JSON exists for all 10 speakers' primary source WAVs
- [ ] All 10 speakers' source WAVs load and play in the RT (MediaElement backend + peaks)
- [ ] Waveform displays with seek, zoom, and region selection
- [ ] Transcript timeline shows coarse transcript with virtualized list, clickable to seek
- [ ] AI suggestions appear for at least 80% of missing concepts, with numeric confidence scores
- [ ] Positional prior speaker selector works — toggling reference speakers re-ranks suggestions live
- [ ] Reviewer can select a region and assign it to a concept
- [ ] Assignments persist in decisions JSON (with AI suggestion metadata) and survive page reload
- [ ] Export includes source_regions for batch re-extraction
- [ ] Spectrogram renders on-demand for selected region (≤30s, Web Worker)
- [ ] Skip/navigate controls work (±5s, ±30s, keyboard shortcuts)
- [ ] Local server supports range requests (verify with Khan02's 3:10:00 recording)
- [ ] Only one source explorer panel open at a time (singleton enforcement)
- [ ] Full-screen mode works for extended investigation sessions
- [ ] Feature is hidden when running on gh-pages (no source WAVs available)

---

## 11. Existing Assets Inventory

### Coarse Transcripts (alignment/)

| File | Speaker | Segments | Duration |
|------|---------|----------|----------|
| Fail01_Faili_M_1984_coarse.json | Fail01 | ~420 | ~7,200s |
| Fail02_SK_Faili_F_1968_coarse.json | Fail02 | ~180 | ~3,000s |
| Kalh01_Kalh_M_1981_coarse.json | Kalh01 | ~507 | ~7,600s |
| Khan01_REC00002_coarse.json | Khan01 (primary) | ~387 | ~8,580s |
| Khan01_2023043001_coarse.json | Khan01 (alt) | ~240 | ~5,220s |
| Khan01_20230502_khanaqini_01_02_coarse.json | Khan01 (alt) | ~200 | ~4,320s |
| Khan02_khanaqini_F_1967_coarse.json | Khan02 | ~487 | ~11,382s |
| Khan04_Khanaqin_F_2000_coarse.json | Khan04 | ~260 | ~5,954s |
| Mand01_Mandali_M_1900_01_coarse.json | Mand01 | ~795 | ~11,924s |
| Qasr01_Qasrashirin_M_1973_coarse.json | Qasr01 | ~933 | ~14,000s |
| Saha01_Sahana_F_1978_coarse.json | Saha01 | ~500 | ~7,500s |

Khan03 uses turbo transcript from cluster detection, not coarse alignment.

### Verified Lexicon Start Times

| Speaker | Lexicon starts at | Source WAV |
|---------|-------------------|------------|
| Fail01  | ~506s             | Faili_M_1984.wav |
| Fail02  | ~335s             | SK_Faili_F_1968.wav |
| Kalh01  | ~884s             | Kalh_M_1981.wav |
| Khan01  | ~1270s            | REC00002.wav |
| Khan02  | ~418s             | khanaqini_F_1967.wav |
| Khan03  | ~465s             | C0401_audio.wav |
| Khan04  | ~1192s            | Khanaqin_F_2000.wav |
| Mand01  | ~0s               | Mandali_M_1900_01.wav |
| Qasr01  | ~0s               | Qasrashirin_M_1973.wav |
| Saha01  | ~0s               | Sahana_F_1978.wav |

### Reference Forms per Concept

Available in `review_data.json` — for each concept, up to 10 speakers' ortho + IPA.
Used for AI matching: collect non-missing forms as reference, build search patterns.

---

## 12. Estimated Timeline

| Phase | Task | Estimate |
|-------|------|----------|
| 0 | WAV audit (ffprobe all source files) | 30 min |
| 1 | Data preparation (source_index, peaks, transcripts, AI suggestions) | 2.5 hours |
| 2 | Server upgrade (range requests) | 30 min |
| 3 | Waveform + basic controls (MediaElement + peaks) | 3.5 hours |
| 4 | Transcript timeline + AI suggestions (virtualized) | 2.5 hours |
| 5 | Assignment + export | 1.5 hours |
| 6 | Full-screen mode | 1.5 hours |
| 7 | Polish + integration | 1 hour |
| **Total** | | **~13 hours** |

Spread across **3–4 focused sessions** (3–4 hours each). Not a single marathon.

**Risk buffer:** The wavesurfer MediaElement + peaks integration is the riskiest step. If it doesn't work cleanly, allow an extra 2–3 hours for debugging or switching to a custom `<audio>` + `<canvas>` waveform renderer.
