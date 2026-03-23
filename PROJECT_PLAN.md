# PARSE — Phonetic Analysis & Review Source Explorer

**Version:** 4.0
**Date:** 2026-03-23
**Status:** Architecture Redesign — Timestamp-Centric Model
**License:** MIT
**Repo:** `TarahAssistant/PARSE`

**Changelog:**
- v4.0 — Major architecture redesign: timestamps as core data model, 4-tier Praat-compatible annotations, TextGrid/ELAN/CSV import/export, video sync infrastructure, project config abstraction, AI provider abstraction, onboarding flow, SIL language codes
- v3.0 — Build complete (14 files), environment inventory, Audio_Working pipeline
- v2.0 — Wavesurfer backend fix, timeline recalibration, fuzzy matching tightening

---

## 1. Vision

PARSE is a browser-based phonetic review tool for linguists working with audio recordings of word lists, interviews, or elicitation sessions. It replaces the Praat/Audacity ↔ spreadsheet workflow with an integrated environment for:

- Browsing full source recordings with waveform + spectrogram + transcript
- AI-assisted location of target words in long recordings
- Precise time-stamped segmentation with IPA, orthography, and concept annotations
- Praat TextGrid / ELAN XML interoperability
- Video synchronization for recordings with accompanying video
- Batch export of annotated segments for further analysis

**Design principles:**
- **Timestamps are the bible** — every annotation is anchored to precise start/end times in the source audio. All downstream operations (Praat export, video clips, segment extraction) derive from timestamps.
- **Local-first** — all audio processing stays on-machine. No data leaves without explicit user action.
- **AI-optional** — core functionality works fully offline. AI features (fuzzy matching, video sync refinement) enhance the experience but are not required.
- **Cross-platform** — runs on Windows, macOS, Linux. No hardcoded paths.
- **Interoperable** — Praat TextGrid, ELAN XML, and CSV are first-class formats.

---

## 2. Problem Statement

Phonetic fieldwork typically produces long recordings (30–200 min) containing embedded word lists. Extracting, segmenting, and annotating individual lexical items requires:

1. Loading each recording in Praat/Audacity
2. Manually navigating to each word
3. Setting boundaries, transcribing IPA and orthography
4. Exporting segments and annotations separately

For a 10-speaker, 82-concept dataset, this means ~820 manual lookups across ~15 hours of audio. PARSE reduces this to a guided, AI-assisted workflow with persistent annotations and batch export.

### Current thesis dataset

| Speaker | Missing / Total | Source WAVs |
|---------|-----------------|-------------|
| Fail01 | 6 / 82 | Faili_M_1984.wav |
| Fail02 | 71 / 82 | SK_Faili_F_1968.wav |
| Kalh01 | 2 / 82 | Kalh_M_1981.wav |
| Khan01 | 9 / 82 | REC00002.wav + 2 alternates |
| Khan02 | 1 / 82 | khanaqini_F_1967.wav |
| Khan03 | 6 / 82 | C0401_audio.wav + 2 alternates |
| Khan04 | 81 / 82 | Khanaqin_F_2000.wav |
| Mand01 | 0 / 82 | Mandali_M_1900_01.wav |
| Qasr01 | 0 / 82 | Qasrashirin_M_1973.wav |
| Saha01 | 0 / 82 | Sahana_F_1978.wav |

---

## 3. Core Data Model — Timestamp Annotations

### 3.1 The Annotation Layer

Every piece of data in PARSE is anchored to a **time-stamped segment** in a source audio file. This is the primary data structure — not a navigation aid, not metadata. The annotation layer is a Praat TextGrid equivalent stored as JSON internally, with full bidirectional TextGrid import/export.

```json
{
  "version": 1,
  "project_id": "sk-thesis-2026",
  "speaker": "Fail01",
  "source_audio": "audio/working/Fail01/Faili_M_1984.wav",
  "source_audio_duration_sec": 7200.0,
  "tiers": {
    "ipa": {
      "type": "interval",
      "display_order": 1,
      "intervals": [
        { "start": 506.2, "end": 506.9, "text": "jek" },
        { "start": 541.1, "end": 541.8, "text": "dɪ" }
      ]
    },
    "ortho": {
      "type": "interval",
      "display_order": 2,
      "intervals": [
        { "start": 506.2, "end": 506.9, "text": "یەک" },
        { "start": 541.1, "end": 541.8, "text": "دی" }
      ]
    },
    "concept": {
      "type": "interval",
      "display_order": 3,
      "intervals": [
        { "start": 506.2, "end": 506.9, "text": "1:one" },
        { "start": 541.1, "end": 541.8, "text": "2:two" }
      ]
    },
    "speaker": {
      "type": "interval",
      "display_order": 4,
      "intervals": [
        { "start": 0, "end": 7200.0, "text": "Fail01" }
      ]
    }
  },
  "metadata": {
    "language_code": "sdh",
    "language_name": "Southern Kurdish",
    "contact_languages": ["fa", "ar", "ckb"],
    "created": "2026-03-23T21:00:00Z",
    "modified": "2026-03-23T22:00:00Z"
  }
}
```

### 3.2 Tier Structure (Praat-compatible)

Displayed from top (closest to spectrogram) to bottom:

| Tier | Name | Content | Example |
|------|------|---------|---------|
| 1 (top) | `ipa` | IPA transcription | `jek` |
| 2 | `ortho` | Orthographic form (native script) | `یەک` |
| 3 | `concept` | Concept ID + English gloss | `1:one` |
| 4 (bottom) | `speaker` | Speaker ID | `Fail01` |

All four tiers share the same time boundaries for each annotated segment. The speaker tier spans the entire recording as a single interval.

Users can add custom tiers if needed (e.g., `notes`, `morpheme_break`).

### 3.3 File Persistence

Annotations are saved as **JSON files on disk** alongside the project, not in localStorage.

```
<project_root>/
  annotations/
    Fail01.parse.json      ← annotation file per speaker
    Fail02.parse.json
    ...
```

Autosave on every edit. Manual "Save" button also available. localStorage used only as a crash-recovery backup.

### 3.4 Annotation Workflow

1. User opens a speaker in PARSE
2. Waveform + spectrogram + coarse transcript load
3. AI suggestions highlight candidate timestamps for each concept
4. User clicks a suggestion → region created at that timestamp
5. User adjusts region boundaries by dragging handles
6. User enters/confirms IPA, orthography, concept in the annotation fields
7. **Timestamp + all tier data saved atomically** — the segment exists only when saved
8. Repeat for all concepts × speakers

---

## 4. Project Configuration

### 4.1 `project.json`

Every PARSE project has a configuration file at its root. This decouples PARSE from any specific data layout.

```json
{
  "parse_version": "1.0",
  "project_id": "sk-thesis-2026",
  "project_name": "Southern Kurdish Bayesian Phylogenetics",
  "language": {
    "code": "sdh",
    "name": "Southern Kurdish",
    "script": "Arabic",
    "contact_languages": ["fa", "ar", "ckb"]
  },
  "paths": {
    "audio_original": "audio/original",
    "audio_working": "audio/working",
    "annotations": "annotations",
    "exports": "exports",
    "peaks": "peaks",
    "transcripts": "transcripts"
  },
  "concepts": {
    "source": "concepts.csv",
    "id_column": "concept_id",
    "label_column": "english",
    "total": 82
  },
  "speakers": {
    "Fail01": {
      "source_files": [
        {
          "filename": "Faili_M_1984.wav",
          "is_primary": true,
          "lexicon_start_sec": 506
        }
      ],
      "video_files": [],
      "has_csv_timestamps": true,
      "notes": ""
    },
    "Khan01": {
      "source_files": [
        {
          "filename": "REC00002.wav",
          "is_primary": true,
          "lexicon_start_sec": 1270
        },
        {
          "filename": "2023043001.wav",
          "is_primary": false,
          "lexicon_start_sec": 1034
        }
      ],
      "video_files": [
        {
          "filename": "Khan01_session.mp4",
          "fps": 60,
          "sync_status": "unsynced"
        }
      ],
      "has_csv_timestamps": true
    }
  },
  "ai": {
    "enabled": false,
    "provider": null,
    "model": null
  },
  "server": {
    "port": 8766,
    "host": "0.0.0.0"
  }
}
```

### 4.2 Language Codes

PARSE uses **SIL ISO 639-3** language codes. On setup, the user selects their target language from SIL's registry. The code is stored in `project.json` and used for:

- Whisper language parameter selection
- AI prompt context ("You are a [language_name] linguistics expert")
- Future: automated cognate lookup from Wiktionary/Wikipedia

Contact languages (languages that may influence the target) are also stored for AI matching context.

### 4.3 Onboarding Flow

New project setup wizard:

1. **Name your project** → `project_id`, `project_name`
2. **Select target language** → SIL code picker with search
3. **Select contact languages** → multi-select from common regional languages
4. **Add audio files** → file browser, drag-drop, or folder select
   - User chooses source directory (originals)
   - User chooses working directory (normalized copies will go here)
   - PARSE normalizes: 16-bit PCM mono, -16 LUFS, 44.1kHz
5. **Add speakers** → name each speaker, assign audio files
6. **Import concepts** → CSV upload or manual entry
7. **Configure AI (optional)** → select provider, enter API key, test connection
8. **Generate data** → peaks, coarse transcripts (if Whisper available), AI suggestions
9. **Done** → project ready for annotation

---

## 5. Audio Format Support

PARSE must handle all common field recording formats without requiring manual conversion.

### 5.1 Supported Input Formats

| Format | Container | Bit Depth | Notes |
|--------|-----------|-----------|-------|
| PCM WAV | RIFF | 16-bit | Standard |
| PCM WAV | RIFF | 24-bit | Common in pro recorders |
| Float WAV | RIFF (tag 3) | 32-bit | Common in DAWs |
| PCM WAV | RF64/BWF | Any | Large files (>4GB) |
| MP3 | MPEG | N/A | Compressed field recordings |
| FLAC | FLAC | Any | Lossless compressed |
| M4A/AAC | MP4 | N/A | Phone recordings |

### 5.2 Audio Processing Pipeline

**Python `soundfile` library** (not `wave`) for reading — handles all formats above natively.

For playback: browser `<audio>` element with MediaElement backend handles all formats natively via range requests. No server-side transcoding needed for playback.

For Whisper STT: working copies normalized to 16-bit PCM mono 44.1kHz -16 LUFS via two-pass ffmpeg `loudnorm`. Originals never modified.

For peaks generation: `soundfile` reads any format, normalizes to float32 internally, outputs peaks JSON.

---

## 6. Import / Export

### 6.1 Praat TextGrid Export

Per speaker, export a TextGrid with 4 tiers matching the annotation structure:

```
File type = "ooTextFile"
Object class = "TextGrid"

xmin = 0
xmax = 7200.0
tiers? <exists>
size = 4
item []:
    item [1]:
        class = "IntervalTier"
        name = "IPA"
        xmin = 0
        xmax = 7200.0
        intervals: size = 82
            intervals [1]:
                xmin = 506.2
                xmax = 506.9
                text = "jek"
            ...
    item [2]:
        class = "IntervalTier"
        name = "Ortho"
        ...
    item [3]:
        class = "IntervalTier"
        name = "Concept"
        ...
    item [4]:
        class = "IntervalTier"
        name = "Speaker"
        ...
```

Output: `exports/<Speaker>.TextGrid`

### 6.2 Praat TextGrid Import

User selects a `.TextGrid` file and a target speaker.

**Options:**
- **Replace speaker** — delete all existing annotations for this speaker, load from TextGrid
- **Create new speaker** — import as a new speaker entry with a user-provided name

PARSE maps TextGrid tiers to internal tiers by name matching (case-insensitive). Unrecognized tiers are imported as custom tiers. Missing tiers are left empty.

### 6.3 ELAN XML Export (.eaf)

Export annotations in ELAN's XML format for users who prefer ELAN over Praat.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ANNOTATION_DOCUMENT>
  <HEADER MEDIA_FILE="" TIME_UNITS="milliseconds">
    <MEDIA_DESCRIPTOR MEDIA_URL="file:///audio/working/Fail01/Faili_M_1984.wav"
                      MIME_TYPE="audio/x-wav"/>
  </HEADER>
  <TIME_ORDER>
    <TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="506200"/>
    <TIME_SLOT TIME_SLOT_ID="ts2" TIME_VALUE="506900"/>
    ...
  </TIME_ORDER>
  <TIER LINGUISTIC_TYPE_REF="default-lt" TIER_ID="IPA">
    <ANNOTATION>
      <ALIGNABLE_ANNOTATION ANNOTATION_ID="a1"
                            TIME_SLOT_REF1="ts1" TIME_SLOT_REF2="ts2">
        <ANNOTATION_VALUE>jek</ANNOTATION_VALUE>
      </ALIGNABLE_ANNOTATION>
    </ANNOTATION>
  </TIER>
  ...
</ANNOTATION_DOCUMENT>
```

### 6.4 CSV Export

Flat table for spreadsheet analysis:

```csv
speaker,concept_id,concept_en,start_sec,end_sec,duration_sec,ipa,ortho,source_file
Fail01,1,one,506.2,506.9,0.7,jek,یەک,Faili_M_1984.wav
Fail01,2,two,541.1,541.8,0.7,dɪ,دی,Faili_M_1984.wav
```

### 6.5 Segment Audio Export

Using annotation timestamps, batch-extract audio clips via ffmpeg:

```
exports/segments/
  Fail01_001_one.wav       (506.2–506.9s from source)
  Fail01_002_two.wav       (541.1–541.8s from source)
  ...
```

Lossless extraction (`-c copy` where possible, `-acodec pcm_s16le` otherwise).

---

## 7. AI Integration

### 7.1 Provider Abstraction

AI features are optional. When enabled, PARSE supports multiple providers through a unified interface:

```json
{
  "ai": {
    "enabled": true,
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "api_key_env": "PARSE_AI_API_KEY"
  }
}
```

**Supported providers (planned):**

| Provider | Models | Auth |
|----------|--------|------|
| Anthropic | claude-sonnet-4-6 | API key |
| OpenAI | gpt-4o, gpt-4o-mini | API key or OAuth login |
| Local (Ollama) | any | No auth (localhost) |

**Current implementation:** Anthropic Sonnet via API key. OpenAI and local support are architecture-ready but not built yet.

### 7.2 AI-Assisted Fuzzy Matching (Strategy #4)

After strategies 1-3 (exact ortho, Levenshtein, phonetic regex) run offline:

1. Filter: concepts with only low-confidence (< 0.40) or zero matches
2. Batch prompt: send ~20 candidate transcript windows per API call with reference forms
3. AI evaluates: morphological variants, dialectal alternations, Whisper errors
4. Score: `base_score` 0.10–0.39 for AI matches (lower than rule-based by design)
5. Cache: results in `ai_suggestions.json`, never re-computed unless transcripts change

**Offline fallback:** Strategies 1-3 work without any AI provider. Users without API access still get exact, fuzzy, and phonetic matches.

### 7.3 AI-Assisted Video Sync Verification

After automated FFT cross-correlation produces an initial offset + drift estimate:

1. Extract ~5 aligned windows from both audio streams
2. Send to AI: "Do these segments sound aligned? Estimate misalignment if any."
3. AI suggests corrections → applied to sync parameters
4. User confirms in UI

**Offline fallback:** FFT cross-correlation works without AI. Manual fine-tune slider available.

### 7.4 Future AI Features (Architecture-Ready, Not Built)

- **Automated cognate lookup** — given a concept and language code, pull reference forms from Wiktionary/academic sources
- **IPA suggestion** — given an audio segment + orthography, suggest IPA transcription
- **Quality check** — flag suspicious annotations (duration too short, IPA doesn't match ortho pattern)

---

## 8. Video Synchronization

### 8.1 Overview

Some speakers have video recordings alongside audio. Video and audio were recorded on separate devices with separate clocks, so they are not in sync. PARSE provides tools to align them and extract video clips at annotation timestamps.

### 8.2 Sync Data Model

Per speaker per video file:

```json
{
  "video_file": "Khan01_session.mp4",
  "audio_file": "audio/working/Khan01/REC00002.wav",
  "fps": 60,
  "sync": {
    "status": "synced",
    "offset_sec": 14.3,
    "drift_rate": 0.00667,
    "method": "fft_auto",
    "ai_verified": true,
    "locked_at": "2026-03-23T22:00:00Z",
    "manual_adjustment_sec": 0.0
  }
}
```

### 8.3 Sync Pipeline

**Step 1 — Extract video audio**
`ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 44100 -ac 1 temp_video_audio.wav`

**Step 2 — FFT cross-correlation**
Select a ~30s chunk with clear speech (around lexicon start). Cross-correlate the two audio streams to find initial offset. Standard scipy `correlate` + `fftconvolve`.

**Step 3 — Multi-point drift detection**
Repeat cross-correlation at intervals (every 10 min) along the recording. Linear regression on offset vs time → drift rate. For 60fps video, expect small but measurable drift.

**Step 4 — AI verification (optional)**
If AI is enabled, send sample aligned windows to the provider for verification.

**Step 5 — UI confirmation**
Both waveforms displayed stacked. Playback controls for simultaneous listening. Fine-tune slider for manual offset. FPS dropdown for common formats.

**Step 6 — Lock sync**
User confirms → sync parameters saved to project. All annotation timestamps can now be mapped to video time.

### 8.4 Timestamp Mapping

```
video_time(wav_time) = (wav_time × (1 + drift_rate/60)) + offset_sec + manual_adjustment_sec
video_frame(wav_time) = round(video_time(wav_time) × fps)
```

### 8.5 Video Clip Extraction

Given a synced video and annotation timestamps:

```bash
ffmpeg -ss <video_start> -to <video_end> -i video.mp4 -c copy exports/clips/Fail01_001_one.mp4
```

Frame-accurate extraction using the drift-corrected mapping.

### 8.6 FPS Support

User selects video FPS during onboarding or in the video sync panel:

| FPS | Standard |
|-----|----------|
| 24 | Cinema |
| 25 | PAL |
| 29.97 | NTSC |
| 30 | Web |
| 50 | PAL high |
| 59.94 | NTSC high |
| 60 | Common smartphones |

FPS is stored per video file in `project.json`.

### 8.7 UI — Video Sync Panel

Shown only for speakers with video files. Visual elements:

- **Status indicator:** 🔴 No video / 🟡 Syncing / 🟢 Synced
- **Video file selector** — browse or drag-drop
- **FPS dropdown** — auto-detected from metadata if possible, user override available
- **"Auto-sync" button** — runs FFT + drift detection + optional AI verification
- **Dual waveform display** — WAV audio + video audio, stacked, aligned
- **Playback controls** — play both streams simultaneously for verification
- **Offset fine-tune slider** — ±5s range, 10ms precision
- **"Lock sync" button** — saves parameters
- **"Extract all clips" button** — batch export video clips for all annotated segments

---

## 9. UI Architecture

### 9.1 Panel Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ PARSE — Speaker: Fail01  |  Concept: 1/82 "one"  |  🟢 AI Ready  │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│ ┌── AI Suggestions ────────────────────────────────────────────┐  │
│ │ Positional prior: [☑ Mand01] [☑ Qasr01] [☐ Fail02⚠]       │  │
│ │ 🤖 1. ~337s HIGH 0.92 (exact) — "...یەک"             [▶]   │  │
│ │ 🤖 2. ~892s MED 0.61 (fuzzy) — "...جەک..."           [▶]   │  │
│ │ 🧠 3. ~1204s LOW 0.28 (llm) — "...یەکەم..."          [▶]   │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌── Transcript (virtualized) ──────────────────────────────────┐  │
│ │ 335.0s │ نیشن نەتنیشن هەیشنم یەک                            │  │
│ │ 350.0s │ دو سە چوار                              ← current  │  │
│ │ [🔍 Search...]                                                │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌── Waveform ──────────────────────────────────────────────────┐  │
│ │ ▁▂▃█▇▅▃▁▁▁▂▅██▇▃▁▁▂▃▅▇█▇▅▃▁▁▁▂▃██▇▅▃▂▁▁▁▂▃▅▇█▇▅▃▁       │  │
│ │      [========]  ← draggable region                           │  │
│ │  335s    340s    345s    350s    355s    360s                  │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌── Spectrogram (≤30s, on-demand) ─────────────────────────────┐  │
│ │ 5kHz ─┬──────────────────────────────────────────────────── │  │
│ │       │ [Web Worker FFT — narrow-band/wide-band toggle]      │  │
│ │ 0Hz ──┴──────────────────────────────────────────────────── │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌── Annotation ────────────────────────────────────────────────┐  │
│ │ Region: 337.2s → 338.1s (0.9s)                               │  │
│ │ IPA:     [  jek          ]                                    │  │
│ │ Ortho:   [  یەک          ]                                    │  │
│ │ Concept: [  1:one         ]                                   │  │
│ │ [✓ Save Annotation]  [▶ Play Region]  [🔄 Loop]              │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ◄◄ -30s  ◄ -5s   ▶ Play   +5s ►  +30s ►►   [⛶ Fullscreen]     │
└────────────────────────────────────────────────────────────────────┘
```

### 9.2 Global Singleton

Only ONE panel open at a time. Opening a new speaker/concept closes the previous one and destroys the wavesurfer instance. Prevents memory blowout from multiple large audio buffers.

### 9.3 Fullscreen Mode

**[⛶ Full]** toggles a modal overlay filling the viewport. Same controls plus:
- Prev/Next concept navigation
- "Missing only" toggle (skip to next unannotated concept)
- Escape to close

### 9.4 Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Space | Play/pause |
| Left/Right | ±1s |
| Shift+Left/Right | ±5s |
| Ctrl+Left/Right | ±30s |
| Escape | Close panel / exit fullscreen |
| Tab | Next annotation field |
| Enter | Save annotation |

---

## 10. AI Suggestions Pipeline

### 10.1 Reference Form Collection

For each concept, collect reference forms from speakers with **verified** annotations (status = accepted/reviewed/verified):

- Orthographic forms (Kurdish script)
- IPA transcriptions
- Romanized forms

**Self-reinforcing:** As the reviewer verifies more concepts, the reference pool grows, and suggestions improve.

### 10.2 Matching Strategies

All run offline (no AI required):

| Strategy | Method | Score Range |
|----------|--------|-------------|
| 1. Exact ortho | Token-level match against Kurdish reference forms | 0.70–1.00 |
| 2. Fuzzy ortho | Levenshtein ≤1 (≤4 chars), ≤2 (>4 chars) | 0.40–0.69 |
| 3. Phonetic regex | IPA → regex, match romanized tokens | 0.20–0.39 |
| 4. LLM-assisted | Sonnet/GPT evaluates transcript windows (optional) | 0.10–0.39 |

### 10.3 Positional Re-Ranking (Client-Side)

Selected reference speakers provide expected timestamps per concept. Proximity boost:
- Within ±30s of expected position → up to +0.25 boost
- Beyond ±120s → no boost
- Linear decay between
- Changing reference speakers instantly re-ranks (no API calls)

### 10.4 `ai_suggestions.json` Schema

```json
{
  "positional_anchors": {
    "Mand01": {
      "concept_coverage": 82,
      "timestamps": { "1": 2.3, "2": 35.7 }
    }
  },
  "suggestions": {
    "1": {
      "concept_en": "one",
      "reference_forms": ["jek", "yek", "یەک"],
      "speakers": {
        "Fail02": [
          {
            "source_wav": "audio/working/Fail02/SK_Faili_F_1968.wav",
            "segment_start_sec": 337.2,
            "segment_end_sec": 340.2,
            "transcript_text": "نیشن نەتنیشن هەیشنم یەک",
            "matched_token": "یەک",
            "confidence": "high",
            "confidence_score": 0.92,
            "method": "exact_ortho_match"
          }
        ]
      }
    }
  }
}
```

---

## 11. Server & Hosting

### 11.1 Local Server

`thesis_server.py` — Python HTTP server with:
- HTTP range request support (206 Partial Content) for streaming large audio files
- CORS headers for JS audio decoding
- Serves all project files from project root
- Cross-platform (`pathlib` throughout)
- Configurable port via `project.json`

### 11.2 Development vs Production

- **Dev mode:** Local server with full PARSE features (source audio browsing, AI suggestions, video sync)
- **Export mode:** Static HTML with pre-cut segments only (for sharing/publication via GitHub Pages)

---

## 12. Coarse Transcripts

### 12.1 Generation

Whisper STT on each source recording, generating 3-second windows:

```json
{
  "speaker": "Mand01",
  "source_wav": "audio/working/Mand01/Mandali_M_1900_01.wav",
  "duration_sec": 11924.0,
  "segments": [
    { "start": 0, "end": 3, "text": "سەەە بۊ دەی بەی" },
    { "start": 15, "end": 18, "text": "نیشن نەتنیشن هەیشنم یەک" }
  ]
}
```

### 12.2 Whisper Configuration

- **Model:** `razhan/whisper-base-sdh` (SK fine-tuned) or user-selected
- **Language trick:** `language='sd'` (Sindhi) forces Kurdish-script output
- **Processing:** Local GPU only — no cloud STT
- **Window:** 3s segments every 15s (coarse scan, not full transcription)

---

## 13. Waveform & Spectrogram

### 13.1 Waveform

- **Library:** wavesurfer.js v7, MediaElement backend
- **Peaks:** Pre-generated JSON files (generated by Python `soundfile` + numpy)
- **Loading:** Peaks JSON for instant waveform render; `<audio>` element for streaming playback via range requests
- **Plugins:** RegionsPlugin (draggable segments), TimelinePlugin (time axis)

### 13.2 Spectrogram

- **Computed via Web Worker** (offloads FFT from main thread)
- **Hard cap:** ≤30s window
- **Modes:** Narrow-band (window=2048, formant visibility) / Wide-band (window=256, temporal detail)
- **Rendering:** Greyscale, on-demand (toggle button)

### 13.3 Peaks Generation

Python script using `soundfile`:
- Reads any supported format (16/24/32-bit WAV, RF64, MP3, FLAC, M4A)
- Normalizes to float32 internally
- Computes min/max peaks at ~100 samples/sec
- Outputs wavesurfer PeaksData v2 JSON

---

## 14. Build Status

### ✅ Built (Wave 1-4, commit `897e56f`)

| File | Status | Notes |
|------|--------|-------|
| `python/thesis_server.py` | ✅ Built + reviewed | Needs cross-platform path update |
| `python/generate_source_index.py` | ✅ Built + reviewed | Needs project.json integration |
| `python/generate_peaks.py` | ✅ Built + reviewed | **Needs rewrite: `wave` → `soundfile`** |
| `python/reformat_transcripts.py` | ✅ Built + reviewed | OK as-is |
| `python/generate_ai_suggestions.py` | ✅ Built + reviewed | Needs AI provider abstraction |
| `python/batch_reextract.py` | ✅ Built + reviewed | OK as-is |
| `js/source-explorer.js` | ✅ Built + reviewed | Needs annotation save integration |
| `js/waveform-controller.js` | ✅ Built + reviewed | OK as-is |
| `js/spectrogram-worker.js` | ✅ Built + reviewed | OK as-is |
| `js/transcript-panel.js` | ✅ Built | Needs review |
| `js/suggestions-panel.js` | ✅ Built | Needs review |
| `js/region-manager.js` | ✅ Built | Needs review + annotation layer integration |
| `js/fullscreen-mode.js` | ✅ Built | Needs review |
| `review_tool_dev.html` | ✅ Built | Needs annotation panel HTML |
| `Start Review Tool.bat` | ✅ Built | Add cross-platform launcher |

### 🔲 New (v4.0 additions)

| Component | Priority | Depends On |
|-----------|----------|------------|
| `project.json` config loader | 🔴 High | Nothing |
| Annotation data model (JSON) | 🔴 High | Nothing |
| Annotation save/load to disk | 🔴 High | Annotation data model |
| Annotation panel UI (IPA/ortho/concept fields) | 🔴 High | Annotation data model |
| Praat TextGrid export | 🔴 High | Annotation data model |
| Praat TextGrid import | 🔴 High | Annotation data model |
| `generate_peaks.py` rewrite (`soundfile`) | 🔴 High | Nothing |
| Onboarding wizard | 🟡 Medium | project.json |
| ELAN XML export | 🟡 Medium | Annotation data model |
| CSV export | 🟡 Medium | Annotation data model |
| AI provider abstraction | 🟡 Medium | project.json |
| Video sync panel UI | 🟡 Medium | project.json |
| FFT cross-correlation (Python) | 🟡 Medium | Nothing |
| Video clip extraction | 🟡 Medium | Video sync |
| Cross-platform launcher (shell + bat) | 🟢 Low | Nothing |
| MIT LICENSE file | 🟢 Low | Nothing |
| README.md | 🟢 Low | Everything else |
| Tests | 🟢 Low | Stable API |

---

## 15. Environment

### GPU
- NVIDIA GeForce RTX 5090 (32GB VRAM)
- CUDA 13.0, WSL + Windows

### Whisper
- `razhan/whisper-base-sdh` — SK fine-tuned, local CUDA
- `language='sd'` trick for Kurdish-script output

### ffmpeg
- Windows: `C:\ProgramData\chocolatey\bin\ffmpeg.exe` v8.0
- Cross-platform: must also work with system `ffmpeg` on macOS/Linux

### Python
- WSL: Python 3.12.3, `soundfile`, `numpy`, `scipy`
- Windows conda: `kurdish_asr` env with torch + CUDA

---

## 16. Risks

| Risk | Mitigation |
|------|------------|
| Annotation files grow large | One file per speaker, not one giant JSON |
| TextGrid format edge cases | Test with real Praat-generated TextGrids |
| Video sync FFT fails on noisy audio | Manual offset slider as fallback |
| AI provider rate limits | Batch calls, cache results, graceful degradation |
| Cross-platform path issues | `pathlib` everywhere, relative paths in project.json |
| localStorage data loss | File-based persistence primary, localStorage as backup only |
| Large WAV + soundfile memory | Stream in chunks for peaks generation |

---

## 17. Definition of Done

PARSE v1.0 is complete when:

- [ ] Project config (`project.json`) drives all paths and settings
- [ ] Annotations save to disk as JSON files per speaker
- [ ] 4-tier structure: IPA, Ortho, Concept, Speaker
- [ ] Annotations editable in UI (IPA, ortho, concept fields per region)
- [ ] Praat TextGrid export produces valid files openable in Praat
- [ ] Praat TextGrid import works (replace speaker / create new)
- [ ] ELAN XML export produces valid .eaf files
- [ ] CSV export with all annotation data
- [ ] Segment audio export via ffmpeg
- [ ] `generate_peaks.py` uses `soundfile` (handles all formats)
- [ ] AI suggestions work with provider abstraction (Sonnet now, OpenAI ready)
- [ ] AI is optional — core features work fully offline
- [ ] Video sync panel with FFT auto-sync + manual fine-tune
- [ ] Video clip extraction from synced timestamps
- [ ] FPS selection for video sync (24–60fps)
- [ ] SIL language codes in project config
- [ ] All paths relative — works on Windows, macOS, Linux
- [ ] MIT LICENSE file in repo
- [ ] All existing features from v3.0 still work (waveform, spectrogram, transcript, regions, fullscreen)
