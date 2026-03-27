# PARSE — Phonetic Analysis & Review Source Explorer

**Version:** 5.0
**Date:** 2026-03-26
**Status:** Dual-Mode Architecture — Annotate + Compare
**License:** MIT
**Repo:** `TarahAssistant/PARSE`

**Changelog:**
- v5.0 — Dual-mode architecture: Annotate (segmentation workstation) + Compare (cross-speaker cognate analysis). Tagging/filtering system, "include in analysis" toggles, borrowing adjudication with SIL contact languages, save history, multiple speaker import paths, full BEAST2 pipeline roadmap. Legacy review_tool.html preserved as reference.
- v4.0 — Major architecture redesign: timestamps as core data model, 4-tier Praat-compatible annotations, TextGrid/ELAN/CSV import/export, video sync infrastructure, project config abstraction, AI provider abstraction, onboarding flow, SIL language codes
- v3.0 — Build complete (14 files), environment inventory, Audio_Working pipeline
- v2.0 — Wavesurfer backend fix, timeline recalibration, fuzzy matching tightening

---

## 1. Vision

PARSE is a browser-based phonetic analysis workstation for linguists working with audio recordings of word lists, interviews, or elicitation sessions. It replaces Praat, Audacity, ELAN, and spreadsheet workflows with a single integrated environment.

**Two work modes:**

**Annotate** — Per-speaker segmentation and transcription:
- Browse full source recordings with waveform + spectrogram + transcript
- AI-assisted location of target words in long recordings
- Precise time-stamped segmentation with IPA, orthography, and concept annotations
- Tag and filter concepts for selective analysis
- Praat TextGrid / ELAN XML interoperability
- Video synchronization for recordings with accompanying video

**Compare** — Cross-speaker cognate analysis and phylogenetic data preparation:
- Concept × speaker matrix view (all speakers side by side)
- Cognate set management (accept, split, merge, click-to-cycle)
- Borrowing adjudication with contact language similarity scores
- AI-powered new speaker alignment (full-file STT → repetition detection → cross-speaker matching)
- Auto-offset detection for misaligned imported timestamps
- Export to LingPy wordlist.tsv → LexStat → BEAST2 pipeline

**Design principles:**
- **Timestamps are the bible** — every annotation is anchored to precise start/end times in the source audio. All downstream operations (Praat export, video clips, segment extraction) derive from timestamps.
- **Local-first** — all audio processing stays on-machine. No data leaves without explicit user action.
- **AI-layered** — base layers (faster-whisper STT + IPA) work locally. Optional LLM and language-specific layers can be added. Core functionality works fully offline.
- **Cross-platform** — runs on Windows, macOS, Linux. No hardcoded paths.
- **Interoperable** — Praat TextGrid, ELAN XML, CSV, and LingPy TSV are first-class formats.

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

**Updated:** 2026-03-26 — Complete rewrite for layered AI architecture.

### 7.1 AI Layer Architecture

PARSE uses a **layered** AI architecture. All processing is local-first (GPU). Cloud APIs are optional add-ons.

**Base layers (required for AI features):**

| Layer | Purpose | Implementation | Location |
|-------|---------|----------------|----------|
| **STT** | Full-file speech-to-text with timestamps | faster-whisper | `python/ai/stt_pipeline.py` |
| **IPA** | Orthographic → IPA conversion | epitran / custom model | `python/ai/ipa_transcribe.py` |

**Optional layers:**

| Layer | Purpose | Implementation | Location |
|-------|---------|----------------|----------|
| **LLM** | Concept suggestions, quality checks | OpenAI / Anthropic / local Ollama | `python/ai/suggestions.py` |
| **Language-specific** | Fine-tuned STT for target language | User-provided whisper model | Configured in `config/ai_config.json` |

**Design principle:** AI features are OPTIONAL. Core segmentation, annotation, and comparison work fully offline. AI adds speed and convenience, not gatekeeping.

### 7.2 Provider Abstraction

`python/ai/provider.py` defines an abstract interface that all AI features call:

```python
class AIProvider:
    def transcribe(wav_path, language) -> List[Segment]
    def to_ipa(text, language) -> str
    def suggest_concepts(transcript_windows, reference_forms) -> List[Suggestion]
```

**Implementations:**
- **LocalWhisperProvider** — faster-whisper + CT2 models, local GPU
- **OpenAIProvider** — OpenAI Whisper API + GPT for suggestions
- **HybridProvider** — local STT + cloud LLM (best of both)
- **OllamaProvider** — fully local LLM (no cloud dependency)

Users select provider in `config/ai_config.json`. Application code calls the abstract interface only — never imports a specific provider directly.

### 7.3 AI Configuration

Stored in `config/ai_config.json` (see §14.1 for full schema):

```json
{
  "stt": {
    "provider": "faster-whisper",
    "model_path": "",
    "language": "sd",
    "device": "cuda",
    "compute_type": "float16"
  },
  "ipa": { "provider": "local", "model": "epitran" },
  "llm": { "provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY" },
  "specialized_layers": []
}
```

**Specialized layers** allow users to add language-specific fine-tuned models (e.g., `razhan/whisper-base-sdh` for Southern Kurdish). These stack on top of the base STT layer.

### 7.4 Model Management

`python/ai/model_manager.py` handles:
- Model path resolution (local paths, HuggingFace cache, CT2 directories)
- Model download on first use (if HuggingFace model ID provided)
- Cache validation (CT2 vs safetensors format check)
- GPU/CPU device selection and memory estimation

### 7.5 JS ↔ Python Communication

`js/shared/ai-client.js` communicates with the Python server for AI operations:
- `POST /api/stt` — trigger full-file STT (returns job ID for polling)
- `POST /api/stt/status` — poll STT job progress
- `POST /api/ipa` — convert text to IPA
- `POST /api/suggest` — get concept suggestions
- `POST /api/compute` — trigger cognate computation
- `POST /api/offset-detect` — run auto-offset detection

All AI endpoints return immediately with a job ID. Frontend polls for completion. This enables background processing while user works.

### 7.6 AI-Assisted Features

**In Annotate mode:**
- Coarse transcript scanning (3s windows every 15s for concept location)
- AI concept suggestions (Strategy #4: LLM evaluates candidate windows)
- Video sync verification (FFT + optional AI confirmation)

**In Compare mode:**
- Full-file STT on new speaker import (§12.2)
- Auto-offset detection (§12.3)
- Repetition detection for wordlist identification (§12.4)
- Cross-speaker matching with phonetic variation rules (§12.5)
- Cognate set computation via LexStat (§17.8)

**Offline fallback:** All non-AI features work without any provider configured. Strategies 1-3 (exact match, Levenshtein, phonetic regex) run purely client-side.

### 7.7 Built-In PARSE AI Assistant (MVP System Prompt)

The built-in chat assistant prompt is currently defined in `python/ai/chat_orchestrator.py` (`_build_system_prompt`).

#### Current System Prompt Text (verbatim)

```text
You are the built-in PARSE AI toolbox assistant.

Hard constraints (must follow):
1) READ-ONLY MVP: do not mutate project state. No annotation writes, no config writes, no enrichments writes, no file overwrites.
2) Only use allowlisted PARSE-native tools. Never invent tools and never request shell access.
3) No file/context attachments are supported in this MVP.
4) If asked to apply changes, explicitly state the environment is read-only and provide a preview plan instead.
5) Never imply a write happened unless a tool explicitly reports a persisted write (which is not available in this MVP).
6) Be transparent: if a tool is placeholder/unavailable, say so clearly.

Available tools:
- annotation_read
- cognate_compute_preview
- cross_speaker_match_preview
- project_context_read
- spectrogram_preview
- stt_start
- stt_status

Response style:
- concise, technical, and accurate
- when using tools, summarize what was checked
- keep read-only limitations explicit when relevant
```

#### Available Tool Allowlist (MVP)

- `annotation_read`
- `cognate_compute_preview`
- `cross_speaker_match_preview`
- `project_context_read`
- `spectrogram_preview`
- `stt_start`
- `stt_status`

#### Hard Constraints (MVP)

- Read-only only: no persisted annotation/config/enrichment/file writes.
- Use only allowlisted PARSE-native tools.
- No shell access requests.
- No file/context attachments.
- If asked to change state, provide a preview plan and explicitly state read-only limitations.
- Do not claim any writes occurred.
- Be explicit when tooling is placeholder or unavailable.

**MVP note:** This is the current baseline system prompt. It will be enriched later with additional project-specific context and guidance as the assistant evolves beyond MVP.

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

`python/server.py` — Python HTTP server with:
- HTTP range request support (206 Partial Content) for streaming large audio files
- CORS headers for JS audio decoding
- Serves all project files from project root
- Cross-platform (`pathlib` throughout)
- Configurable port via `project.json`

**API endpoints (served by `server.py`):**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/stt` | POST | Trigger full-file STT (returns job ID) |
| `/api/stt/status` | POST | Poll STT job progress |
| `/api/ipa` | POST | Convert text to IPA |
| `/api/suggest` | POST | Get AI concept suggestions |
| `/api/compute/cognates` | POST | Trigger LexStat cognate computation |
| `/api/compute/offset` | POST | Run auto-offset detection |
| `/api/compute/spectrograms` | POST | Batch spectrogram generation |
| `/api/enrichments` | GET/POST | Read/write enrichments layer |
| `/api/config` | GET/PUT | Read/update project + AI config |
| `/*` | GET | Static file serving (HTML, JS, audio, peaks) |

All long-running endpoints (STT, cognate compute) return immediately with a job ID. Frontend polls for completion via status endpoints. This enables background processing while the user works.

### 11.2 Development vs Production

- **Dev mode:** Local server with full PARSE features (source audio, AI, Compare, video sync)
- **Export mode:** Static HTML with pre-cut segments only (for sharing/publication via GitHub Pages)

---

## 12. Speech-to-Text & Cross-Speaker Matching Pipeline

**Updated:** 2026-03-26 — Complete rewrite based on design session.

### 12.1 STT Configuration

See §7 for the full AI layer architecture and provider abstraction.

**SK-specific config (thesis):**
- Model: `razhan/whisper-base-sdh` (CT2 format at `/mnt/c/Users/Lucas/Thesis/models/razhan-whisper-ct2/`)
- Language trick: `language='sd'` (Sindhi) forces Kurdish-script output
- Performance: ~33.7× realtime on CUDA float16

### 12.2 Full Audio Processing on Speaker Import

When a new speaker is added, the **entire audio file** is processed through STT. This is NOT a sparse coarse scan — it produces complete coverage of the recording.

**Why full coverage matters:**
- The transcription becomes a **searchable index** for finding unsegmented concepts
- In Compare mode, when a concept is missing for a speaker, the full transcription can be searched to find candidate locations
- The STT output is inaccurate but fast — useful for discovery, not final transcription

**Processing time warning:**
- 3-5 hours of audio → 30 min to 1 hour of processing (GPU-dependent)
- UI must warn user before starting: "Processing [filename] (~X hours of audio). This may take [estimated time]. You can continue working while it runs."
- Runs in **background** — user keeps working in Annotate, Compare, or any other mode
- Progress indicator visible but non-blocking
- Results appear incrementally or on completion

**Output format:**
```json
{
  "speaker": "Khan04",
  "source_wav": "audio/working/Khan04/Khanaqin_F_2000.wav",
  "duration_sec": 7200.0,
  "processed_at": "2026-03-26T11:00:00Z",
  "model": "razhan/whisper-base-sdh",
  "segments": [
    { "start": 12.3, "end": 13.1, "ortho": "یەک", "ipa": "jek" },
    { "start": 13.5, "end": 14.2, "ortho": "یەک", "ipa": "jek" },
    { "start": 14.8, "end": 15.5, "ortho": "یەک", "ipa": "jek" },
    { "start": 18.2, "end": 19.0, "ortho": "دوو", "ipa": "duː" }
  ]
}
```

### 12.3 Auto-Offset Detection

When importing data with pre-existing timestamps (CSV + WAV), an AI layer automatically checks whether segment timestamps are consistently offset from the actual audio.

**Why this happens:**
- Third-party audio processing may strip user metadata
- Privacy protection may trim the start of recordings (e.g., +10 minutes offset)
- Different recording setups produce different header/metadata lengths

**Detection method:**
1. Take a sample of known segments (e.g., first 10 with timestamps)
2. For each, check if the expected content exists at the stated timestamp
3. If not, search nearby (±30s, then ±5min, then ±30min) for a match
4. Look for a **consistent shift** across all samples
5. If consistent offset found → apply globally and confirm with user
6. If inconsistent → flag as manual review needed

**This is the FIRST thing checked on import** — before any other processing.

### 12.4 Repetition Detection

In elicitation recordings, speakers typically repeat each concept 2-4 times. PARSE detects this pattern to identify likely wordlist items vs. conversational filler.

**Method:**
- After full STT, group identical or near-identical forms by phonetic similarity
- Flag forms appearing **2-4 times** in close succession (within ~30s window) as likely elicitation items
- Forms appearing only once or appearing throughout the recording are likely conversational

**Output:** Each flagged group becomes a "candidate lexical item" with:
- Representative form (most common variant)
- All occurrence timestamps
- Occurrence count
- Confidence score based on repetition pattern

### 12.5 Cross-Speaker Matching (Compare Mode)

When a baseline speaker is already segmented, PARSE can automatically find matching concepts in a new speaker's recording.

**The chain:**
```
Baseline speaker annotations (known: "yek" = concept 1 at 506.2s)
  + New speaker's full STT transcription
  + Repetition-detected candidate items from new speaker
    → Phonetic variation regex matching
      → Phonetic distance scoring (LexStat)
        → Positional ordering boost
          → Ranked candidates presented in Compare UI
```

**Step 1: Phonetic variation rules**
Not just raw string distance — linguistically informed regex patterns that account for known sound correspondences:
- Initial consonant alternations: j ~ y, k ~ g, q ~ ɢ
- Vowel quality variation: e ~ a ~ ɛ ~ æ
- Final consonant lenition or loss: k ~ g ~ ∅
- Voicing alternations: t ~ d, p ~ b

These rules are **configurable** — users can add their own for their specific language. PARSE ships with defaults for common phonetic processes.

The old review tool used Strategy #3 (phonetic regex) for this — that logic carries forward here.

**Step 2: Phonetic distance scoring**
LexStat / edit distance on IPA forms, ranking candidates by similarity to baseline.

**Step 3: Positional ordering boost**
Concepts in elicitation recordings tend to follow a consistent order. If concept 4 was found at timestamp X, concept 5 should be near X + typical gap. Candidates near the expected position get boosted (same positional prior system from §10.3).

**In the Compare UI:**
- User sees concept "one" row → baseline speaker shows "jek"
- New speaker column shows top candidate: "yak" at 14.2s (confidence: 0.87)
- User clicks → audio plays from that timestamp
- User confirms → segment created, or rejects → next candidate shown

### 12.6 Whisper Configuration (Legacy Reference)

For coarse transcript generation (Annotate mode, not full STT):
- **Window:** 3s segments every 15s (sparse scan for concept location)
- **Model:** User-selected or project default
- **Processing:** Local GPU only — no cloud STT

Full STT (§12.2) is the primary pipeline for new speakers. Coarse scan remains available as a faster alternative when full coverage isn't needed.

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

## 14. File Structure (v5.0)

**Updated:** 2026-03-26

```
parse/
├── parse.html                      ← Annotate mode (existing main app)
├── compare.html                    ← Compare mode (NEW)
├── start_parse.sh                  ← Linux/Mac launcher
├── Start Review Tool.bat           ← Windows launcher
├── LICENSE
├── README.md
├── PROJECT_PLAN.md
│
├── js/
│   ├── shared/                     ← shared across Annotate + Compare
│   │   ├── annotation-store.js     ← localStorage/disk persistence
│   │   ├── project-config.js       ← project.json loader
│   │   ├── tags.js                 ← tagging/filtering system (NEW)
│   │   ├── audio-player.js         ← shared audio playback from WAV regions (NEW)
│   │   ├── ai-client.js            ← JS ↔ Python AI server communication (NEW)
│   │   └── spectrogram-worker.js   ← Web Worker FFT
│   ├── annotate/                   ← Annotate-specific
│   │   ├── parse.js                ← main entry / router
│   │   ├── annotation-panel.js     ← IPA/ortho/concept fields
│   │   ├── region-manager.js       ← waveform region CRUD
│   │   ├── waveform-controller.js  ← WaveSurfer wrapper
│   │   ├── transcript-panel.js     ← coarse transcript display
│   │   ├── suggestions-panel.js    ← AI suggestion rankings
│   │   ├── fullscreen-mode.js      ← fullscreen overlay
│   │   ├── onboarding.js           ← import wizard
│   │   ├── import-export.js        ← CSV/TextGrid/ELAN import/export
│   │   └── video-sync-panel.js     ← video alignment UI
│   └── compare/                    ← Compare-specific (ALL NEW)
│       ├── compare.js              ← main entry
│       ├── concept-table.js        ← concept × speaker matrix layout
│       ├── cognate-controls.js     ← accept/split/merge/click-to-cycle
│       ├── borrowing-panel.js      ← similarity bars, adjudication
│       ├── speaker-import.js       ← new speaker import wizard
│       └── enrichments.js          ← enrichments layer read/write
│
├── python/
│   ├── server.py                   ← HTTP server with range requests
│   ├── peaks.py                    ← waveform peak generation
│   ├── source_index.py             ← source_index.json builder
│   ├── normalize_audio.py          ← audio normalization (ffmpeg)
│   ├── textgrid_io.py              ← Praat TextGrid read/write
│   ├── elan_export.py              ← ELAN XML export
│   ├── csv_export.py               ← CSV export
│   ├── video_sync.py               ← FFT cross-correlation
│   ├── video_clip_extract.py       ← video segment extraction
│   ├── batch_reextract.py          ← batch re-extraction
│   ├── reformat_transcripts.py     ← transcript reformatting
│   │
│   ├── ai/                         ← AI abstraction layer (NEW)
│   │   ├── __init__.py
│   │   ├── provider.py             ← abstract interface (local, OpenAI, etc.)
│   │   ├── stt_pipeline.py         ← faster-whisper full-file STT
│   │   ├── ipa_transcribe.py       ← ortho → IPA conversion model
│   │   ├── model_manager.py        ← model download, cache, path resolution
│   │   └── suggestions.py          ← AI concept suggestions (from generate_ai_suggestions.py)
│   │
│   ├── compare/                    ← Compare pipeline scripts (NEW)
│   │   ├── cognate_compute.py      ← LexStat wrapper, enrichments builder
│   │   ├── cross_speaker_match.py  ← STT + repetition detect + matching
│   │   ├── offset_detect.py        ← auto-offset detection
│   │   └── phonetic_rules.py       ← configurable phonetic variation engine
│   │
│   └── coarse_transcripts.py       ← coarse transcript generation
│
├── config/                         ← user-editable configuration (NEW)
│   ├── ai_config.json              ← model paths, API keys, provider selection
│   ├── phonetic_rules.json         ← phonetic variation rules (j~y, e~a, etc.)
│   └── sil_contact_languages.json  ← contact language definitions
│
├── docs/                           ← development documentation
│   ├── CODING.md
│   ├── INTERFACES.md
│   ├── ONBOARDING_PLAN.md
│   ├── SPEAKERS.md
│   └── BUILD_SESSION.md
│
├── review_tool_dev.html            ← LEGACY (DO NOT TOUCH)
└── tasks/
    └── lessons.md
```

### 14.1 AI Configuration Schema

`config/ai_config.json`:
```json
{
  "stt": {
    "provider": "faster-whisper",
    "model_path": "",
    "language": "sd",
    "device": "cuda",
    "compute_type": "float16"
  },
  "ipa": {
    "provider": "local",
    "model": "epitran"
  },
  "llm": {
    "provider": "openai",
    "model": "gpt-4o",
    "api_key_env": "OPENAI_API_KEY"
  },
  "specialized_layers": [
    {
      "name": "razhan-sk",
      "type": "whisper-finetune",
      "model_path": "/path/to/razhan-whisper-ct2/",
      "language_codes": ["sdh"]
    }
  ]
}
```

### 14.2 AI Provider Abstraction

`python/ai/provider.py` defines an abstract interface:
- `transcribe(wav_path, language) → segments[]` — full-file STT
- `to_ipa(text, language) → ipa_string` — orthographic → IPA
- `suggest_concepts(transcript_windows, reference_forms) → suggestions[]` — AI concept matching

Implementations:
- **LocalWhisperProvider** — faster-whisper + CT2 models
- **OpenAIProvider** — OpenAI Whisper API + GPT for suggestions
- **HybridProvider** — local STT + cloud LLM

Users select in `ai_config.json`. Application code calls the abstract interface only.

### 14.3 Build Status

#### ✅ Existing (needs reorganization into new structure)

| Current Path | New Path | Status |
|------|--------|-------|
| `python/thesis_server.py` | `python/server.py` | ✅ Needs rename |
| `python/generate_source_index.py` | `python/source_index.py` | ✅ Needs rename |
| `python/generate_peaks.py` | `python/peaks.py` | ✅ Needs rewrite (wave→soundfile) |
| `python/generate_ai_suggestions.py` | `python/ai/suggestions.py` | ✅ Move + refactor |
| `python/reformat_transcripts.py` | (keep) | ✅ OK |
| `python/batch_reextract.py` | (keep) | ✅ OK |
| `python/build_coarse_transcripts.py` | `python/coarse_transcripts.py` | ✅ Rename |
| All `js/*.js` files | `js/annotate/*.js` | ✅ Move |
| `js/annotation-store.js` | `js/shared/annotation-store.js` | ✅ Move to shared |
| `js/project-config.js` | `js/shared/project-config.js` | ✅ Move to shared |
| `js/spectrogram-worker.js` | `js/shared/spectrogram-worker.js` | ✅ Move to shared |

#### 🔲 New files to build

| File | Priority | Purpose |
|------|----------|---------|
| `python/ai/__init__.py` | 🔴 | AI package |
| `python/ai/provider.py` | 🔴 | Abstract AI interface |
| `python/ai/stt_pipeline.py` | 🔴 | Full-file STT with faster-whisper |
| `python/ai/ipa_transcribe.py` | 🔴 | Ortho → IPA conversion |
| `python/ai/model_manager.py` | 🟡 | Model download/cache management |
| `python/compare/cognate_compute.py` | 🔴 | LexStat wrapper + enrichments |
| `python/compare/cross_speaker_match.py` | 🔴 | STT + repetition detect + matching |
| `python/compare/offset_detect.py` | 🔴 | Auto-offset detection |
| `python/compare/phonetic_rules.py` | 🔴 | Configurable phonetic variation |
| `config/ai_config.json` | 🔴 | AI model/provider configuration |
| `config/phonetic_rules.json` | 🔴 | Phonetic variation rules |
| `config/sil_contact_languages.json` | 🟡 | Contact language definitions |
| `js/shared/tags.js` | 🔴 | Tagging/filtering system |
| `js/shared/audio-player.js` | 🔴 | Shared audio playback |
| `js/shared/ai-client.js` | 🔴 | JS ↔ Python AI communication |
| `compare.html` | 🔴 | Compare mode entry point |
| `js/compare/compare.js` | 🔴 | Compare main entry |
| `js/compare/concept-table.js` | 🔴 | Concept × speaker matrix |
| `js/compare/cognate-controls.js` | 🔴 | Accept/split/merge/cycle |
| `js/compare/borrowing-panel.js` | 🟡 | Similarity bars, adjudication |
| `js/compare/speaker-import.js` | 🟡 | New speaker import wizard |
| `js/compare/enrichments.js` | 🔴 | Enrichments layer read/write |

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

## 17. Work Modes — Annotate & Compare

**Added:** 2026-03-26 (from design session with Lucas)

PARSE has two primary work modes, navigated via a top-level mode switcher: `Annotate | Compare`

### 17.1 Mode: Annotate (current UI)

The existing single-speaker, concept-by-concept editing workflow. This is the transcription/segmentation workstation.

**What it does:**
- User imports a speaker dataset (WAV + optional timestamps/IPA/ortho)
- User edits segment boundaries, IPA, ortho, concept annotations
- Replaces Audacity/Praat for segmentation work
- AI suggestions help locate concepts in long recordings

**Current status:** Built and functional (`parse.html`). This is the "chunking page" — the initial processing mode.

**Future growth:** Vowel charts, phonetic scripts, speaker-level analysis features. Name "Annotate" is intentionally extensible.

### 17.2 Mode: Compare (to be built)

Cross-speaker, concept-first analysis view. This is where cognate comparison, borrowing adjudication, and phylogenetic data preparation happen.

**Layout:** Table/matrix view (same as old `review_tool.html`):
- **Rows** = concepts
- **Columns** = speakers
- Each cell shows: IPA, ortho, audio play button, spectrogram toggle, cognate badge, similarity bars

**Cognate controls (all four from old tool):**
- ✓ **Accept Grouping** — keep precomputed cognate sets
- ✂ **Split** — interactive mode, click speakers to reassign groups
- ⊕ **Merge All** — collapse into one cognate set
- **Click-to-cycle** — click any speaker's cognate badge to manually reassign class

**Borrowing adjudication:**
- Arabic/Persian similarity bars per speaker row
- Borrowing confirmation: confirmed / not_borrowing
- Handling: code as "missing (?)" or "separate cognate"
- **Onboarding asks users which contact/borrowing languages apply** — uses SIL language codes to select

**Audio in Compare:**
- Plays from the annotated source WAV region set during Annotate (not pre-cut segment files)
- This is a key design difference from the old review tool — PARSE has more power to adjust segments when they're wrong

**Data source:**
- Compare pulls from PARSE's own annotation data (localStorage / annotation JSON files)
- `review_data.json` is legacy reference only — used to understand the old pipeline, not as a live data source
- The old `review_tool.html` at `C:\Users\Lucas\Thesis\review_tool.html` is preserved as-is (sacred, do not modify)

### 17.3 "Include in Analysis" — Item Selection

Users must select which concepts/items go to cognate analysis. Not everything gets compared.

**MVP (v1):** Simple toggle per concept in the Annotate sidebar. Checkbox or switch: "Include in analysis."

**Future (v2):** Chat/voice command from any screen:
- User types: "include items 5, 12, 23-40 in analysis"
- Or speaks: "include item 5 in analysis" (STT → agent processes)
- Agent can process bulk selections regardless of current screen

### 17.4 Tagging & Filtering System

**Tags:** Users can create custom named tag groups (like labels/categories). Examples:
- "cognate" — items selected for cognate analysis
- "borrowing" — suspected loans
- "review" — items needing re-review
- Users give tags custom names

**Filtering:**
- Sidebar filters by tag (show only items with "cognate" tag)
- Essential for users with ~80 selected concepts out of 500+ total items
- Multiple filter modes: show tagged, show untagged, show all

**Bulk tag application:**
- User pastes/imports a concept list (IDs or English glosses) to tag all at once
- Single prompt: "Tag items 1-82 as 'cognate'" or paste a list file
- Supports text file import or direct paste

### 17.5 Speaker Import Options

When adding a new speaker to Compare, multiple import paths:

1. **Raw audio only** — import a WAV file with no additional data. User goes through Annotate first to segment and annotate, then returns to Compare.

2. **Pre-existing data with timestamps** — import data that already has timestamps, IPA, segments complete (e.g., legacy data from old review tool pipeline). Skip Annotate for these speakers.

3. **Manual onboarding** — user fills out speaker metadata form (name, file paths, language variety, etc.) during onboarding wizard.

4. **Agent-assisted import (future)** — user tells the agent a folder path, agent scans the folder and imports whatever data it finds (WAVs, CSVs, JSONs, TextGrids).

### 17.6 Save & Export

**Primary save format:** JSON (PARSE's native annotation format)
- Autosave on every edit
- **Save history maintained** — changes don't overwrite previous saves
- Version snapshots so user can roll back
- No GitHub integration for now — everything local

**Export options:**
- `wordlist.tsv` — LingPy-compatible format (ID, DOCULECT, CONCEPT, IPA, COGID)
- `decisions.json` — reviewer decisions, cognate sets, borrowing adjudications
- Praat TextGrid, ELAN XML, CSV (already in plan)
- Segment audio export via ffmpeg (already in plan)

### 17.7 Pipeline: Compare → BEAST2

The downstream pipeline from Compare mode to phylogenetic analysis:

```
PARSE Annotate (per-speaker segmentation + annotation)
  → PARSE Compare (cross-speaker cognate review + borrowing adjudication)
    → Export: wordlist.tsv
      → LingPy LexStat cognate detection (sk_lingpy_cognate_detect.py)
        → cognates.csv
          → Binary character matrix conversion (TBD — script not yet built)
            → NEXUS file
              → BEAST2 XML generation (TBD — script not yet built)
                → BEAST2 run
```

**Existing:** `sk_lingpy_cognate_detect.py` (LexStat/SCA → cognates.csv)
**Missing/TBD:** cognates.csv → binary matrix → NEXUS → BEAST2 XML scripts
**Legacy reference:** Old review_tool.html pipeline (preserved, not active)

### 17.8 Data Architecture — Hybrid (Option C)

**Decision:** 2026-03-26 — Hybrid approach. Live annotations + separate enrichments layer.

**Core data (always live):**
- Compare reads directly from per-speaker annotation files (localStorage/disk)
- IPA, ortho, timestamps, audio regions are always current — no rebuild needed
- Switching from Annotate to Compare immediately reflects any edits

**Enrichments layer (computed on demand):**
- Stored separately in `parse-enrichments.json`
- Contains: cognate sets, contact language similarity scores, borrowing flags, manual overrides
- Computed by Python/LingPy server-side, triggered by user via "Compute" button in Compare
- Enrichments have a visible "last computed" timestamp so user knows freshness

**Enrichment schema:**
```json
{
  "computed_at": "2026-03-26T10:00:00Z",
  "config": {
    "contact_languages": ["ar", "fa"],
    "speakers_included": ["Fail01", "Kalh01", "Mand01"],
    "concepts_included": [1, 2, 5, 12],
    "lexstat_threshold": 0.6
  },
  "cognate_sets": { "1": { "A": ["Fail01","Kalh01"], "B": ["Mand01"] } },
  "similarity": { "1": { "Fail01": { "ar": 0.12, "fa": 0.05 } } },
  "borrowing_flags": {},
  "manual_overrides": {}
}
```

**Computation workflow:**
1. User selects contact languages in Compare UI (SIL codes)
2. User selects which tagged concepts to compute (e.g., only "cognate" tagged items — not all 500)
3. User selects which speakers to include (baseline may be ready, others still in progress)
4. User clicks "Compute" → warning about potential duration → runs in background
5. User keeps working (Annotate, fix other speakers, anything) while computation runs
6. Results appear in Compare when done — cognate badges, similarity bars populate
7. User can re-run with additional speakers/concepts as more data becomes ready

**Computation engine:**
- LexStat cognate detection + similarity scoring = **purely algorithmic** (LingPy, CPU only, no AI/GPU needed)
- For 10 speakers × 80 concepts: runs in seconds
- For very large datasets (100+ speakers, thousands of concepts): could take minutes → background execution essential
- Python server handles computation, writes results to enrichments file

**Spectrogram computation in Compare:**
- User-controlled granularity:
  - **Single lexeme** — compute spectrogram for one concept × one speaker on click
  - **Single speaker** — compute all spectrograms for one speaker's tagged concepts
  - **All speakers** — compute spectrograms for all speakers × all tagged concepts (batch)
- Computed from source WAV regions via Web Worker FFT (same as Annotate)
- Cached after first computation — no redundant recomputation
- On-demand by default, batch as user option

### 17.9 Legacy Preservation

These files are preserved as reference material. **Do not modify:**
- `/mnt/c/Users/Lucas/Thesis/review_tool.html` — old monolithic review tool (1,716 lines)
- `/mnt/c/Users/Lucas/Thesis/review_data.json` — old review dataset (82 concepts × 6 speakers)
- `/home/lucas/.openclaw/workspace/parse/review_tool_dev.html` — PARSE dev shell (linked to data)

### 17.10 Build Scope — Full Functionality

**Decision:** 2026-03-26 — Build everything. No MVP/stripped-down version. Full Compare mode with all features for thesis deadline (May 2026). Target: 1-2 day build sprint.

---

## 18. Definition of Done

### PARSE v1.0 — Annotate Mode
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
- [ ] Tagging system: custom named tags, filter sidebar by tag
- [ ] Bulk tag application (paste/import concept list)
- [ ] "Include in analysis" toggle per concept
- [ ] All paths relative — works on Windows, macOS, Linux
- [ ] MIT LICENSE file in repo
- [ ] All existing features from v3.0 still work (waveform, spectrogram, transcript, regions, fullscreen)

### PARSE v1.1 — Compare Mode
- [ ] Mode switcher: Annotate | Compare in top nav
- [ ] Concept × Speaker table/matrix layout
- [ ] Per-cell: IPA, ortho, audio play, spectrogram toggle, cognate badge
- [ ] Cognate controls: Accept / Split / Merge All / click-to-cycle
- [ ] Borrowing adjudication: similarity bars, confirmed/not_borrowing, missing vs separate
- [ ] Contact language selection via SIL codes (onboarding)
- [ ] Audio playback from annotated source WAV regions
- [ ] Filter to tagged items only (e.g., "cognate" tag)
- [ ] Save as JSON with version history (no overwrites)
- [ ] Export to `wordlist.tsv` (LingPy-compatible)
- [ ] Export to `decisions.json` (reviewer decisions)
- [ ] Multiple speaker import paths (raw audio, pre-existing data, manual, agent-assisted)

### PARSE v2.0 — Future
- [ ] Built-in chat box for agent commands
- [ ] Voice command support (STT → agent)
- [ ] Agent-assisted folder import
- [ ] Additional analysis modes (vowel charts, phonetic scripts, speaker comparison)
- [ ] cognates.csv → binary matrix conversion script
- [ ] NEXUS → BEAST2 XML generation script
- [ ] Full pipeline automation: Compare → LexStat → BEAST2
