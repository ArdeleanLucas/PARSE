# PARSE — Onboarding & Import Planning Document

**Status:** Living design doc
**Updated:** 2026-04-20
**Original author:** dr-kurd (dictated by Lucas Ardelean)

> This doc describes the full import-wizard design intent. The runtime contract
> actually shipped today is the simpler `POST /api/onboard/speaker` multipart
> upload surfaced in `src/components/compare/SpeakerImport.tsx`. Treat this
> document as the roadmap the wizard should grow into, not the current behavior.

---

## Core Principle

> The linguist's starting point is always an existing dataset they trust. PARSE must meet them there — not ask them to enter data from scratch.

The software must accept what a field linguist already has: a WAV recording (or several), a timestamp/cue file, and optionally an IPA transcription or cognate list. From these inputs, PARSE derives the full working dataset. An AI layer handles ambiguity in the matching process so the linguist does not have to do it manually.

---

## Onboarding Entry Point

When a linguist opens PARSE for the first time (or starts a new project), the first screen is not a blank canvas — it is an **import wizard**. The wizard has one goal: connect the linguist's existing data to PARSE's internal representation.

### Minimum viable import (required):
1. **WAV file(s)** — the audio recording(s) for one reference speaker
2. **Timestamp CSV** — a cue/marker export from Audition, Praat, or a custom CSV with start/end times and concept labels

### Optional enrichment (if available):
3. **IPA transcription file** — a CSV matching segment IDs or timestamps to IPA strings and/or orthographic forms
4. **Praat TextGrid** — segment boundaries + tier labels (replaces timestamp CSV)
5. **ELAN .eaf file** — annotation tiers with timestamps (replaces timestamp CSV)

---

## Import Wizard — Step-by-Step Flow

### Step 1: Speaker identity
- Speaker ID (e.g. `Kalh01`)
- Speaker name (optional free text)
- Variety / dialect (e.g. Southern Kurdish — Kalhori)
- Sex, birth year, origin city (optional metadata)

### Step 2: Link WAV file(s)
- File picker or drag-and-drop
- **Multiple WAV support:** If the linguist selects multiple WAVs (e.g. a recording split across sessions), PARSE notes all of them. The AI layer later determines which WAV contains the lexicon section.
- PARSE reads file duration and basic audio metadata client-side (Web Audio API) — no upload required if served locally.

### Step 3: Link timestamp/cue file
- Accepted formats:
  - Adobe Audition cue export (TSV: Name, Start, Duration, Time Format, Type, Description)
  - Custom CSV (user maps columns to: concept label, start time, end time / duration)
  - Praat TextGrid (`.TextGrid`)
  - ELAN annotation file (`.eaf`)
- PARSE previews parsed rows so the linguist can verify before proceeding.

### Step 4: Link IPA/cognate file (optional)
- CSV with columns: concept label or segment ID, IPA, orthographic form, status
- If present, PARSE pairs rows to timestamp entries by:
  1. Exact ID match (e.g. `JBIL_001_A_one_Kalh01` ↔ `JBIL_001_one`)
  2. Concept name match (fuzzy: `"1- one"` ↔ `"one"`)
  3. Row-order match (fallback when row counts are equal)
- Column mapping is shown to the user for confirmation.

### Step 5: AI-assisted resolution (automatic, non-blocking)
See section below.

### Step 6: Preview & confirm
- Show a table: concept label | start time | end time | IPA (if available) | WAV source
- Linguist can correct any row before saving.
- On confirm: PARSE writes a `project.json` and a `coarse_transcripts/<Speaker>.json` internally.

---

## Current shipped contract (reference)

Until the wizard below lands, the live onboarding path is:

- **Frontend:** `src/components/compare/SpeakerImport.tsx` — speaker ID, audio WAV, optional audition CSV, required xAI/OpenAI provider radio → calls `onboardSpeaker(speakerId, audioFile, csvFile, provider)`.
- **API client:** `src/api/client.ts` → `POST /api/onboard/speaker` multipart form (`speaker_id`, `audio`, `csv?`, `provider`).
- **Server:** `python/server.py::_api_post_onboard_speaker` → background job that writes audio, scaffolds the annotation record, and returns `{ job_id }`. Progress is polled via `POST /api/onboard/speaker/status`.

The AI-assisted resolution described below (Tasks A–D) is the target richer behavior, not the current runtime.

---

## AI-Assisted Matching Layer

### Why AI is needed

The linguist's files may not be perfectly structured:
- Timestamp CSV may have mixed time formats (H:MM:SS and M:SS in the same file)
- Multiple WAV files with no clear indication of which contains the lexicon section
- IPA CSV rows may be in a different order than the timestamp CSV
- Column names may vary between researchers' exports

Manual reconciliation of this is error-prone and slow. An AI layer handles it automatically with a confidence score, surfacing only ambiguous cases for human review.

### AI tasks and instructions

#### Task A: Identify lexicon section in multi-WAV recordings
**Input:** List of WAV filenames + durations, timestamp CSV content  
**Instruction to AI:**
> "Given these WAV files and this timestamp CSV, identify which WAV file contains the lexicon recording session. The timestamps in the CSV may be relative (starting near 0:00) or absolute (starting at the actual offset within a longer recording). Determine the lexicon start offset in seconds. Return: {primary_wav, lexicon_start_sec, confidence, reasoning}."

**Fallback:** If only one WAV, it is the primary. If CSV timestamps start below 300s, treat as relative and require user to confirm the offset.

#### Task B: Match IPA file to timestamp file
**Input:** First 20 rows of timestamp CSV, first 20 rows of IPA CSV  
**Instruction to AI:**
> "These two CSV files describe the same set of lexical items for one speaker. The first has timestamps; the second has IPA/orthographic transcriptions. Determine the correct row-to-row alignment. The files may differ in row count (one may have variants or duplicates), ordering, or section structure. Return: alignment_strategy (by_id | by_name | by_order | by_section), confidence (0–1), any_mismatches (list), notes."

**Fallback:** If row counts match exactly → align by order. If both have an ID column with common structure → align by ID. If AI confidence < 0.7 → show user a side-by-side preview and ask for manual confirmation.

#### Task C: Parse ambiguous time formats
**Input:** Sample of Start column values from timestamp CSV  
**Instruction to AI:**
> "These are time values from an Adobe Audition cue export. Some may be in H:MM:SS.mmm format (absolute from recording start) and some in M:SS.mmm format (relative to a section start). Classify each format and identify the offset to apply to convert relative times to absolute. Return: format_map [{value, format, absolute_sec}], section_boundary (the row index where format changes, if any)."

**Fallback:** Rule-based parser handles H:MM:SS vs M:SS distinction; AI is only called when more than two formats are detected or when values are ambiguous.

#### Task D: Column mapping for unknown CSV formats
**Input:** CSV header row + first 5 data rows  
**Instruction to AI:**
> "This CSV file contains phonetic annotation data for a field linguistics recording session. Identify which column contains: (1) a unique segment or concept ID, (2) a concept label in English, (3) a start timestamp, (4) an end timestamp or duration, (5) IPA transcription, (6) orthographic transcription in Arabic script. Return: {id_col, label_col, start_col, end_col, ipa_col, ortho_col} using the actual column header names."

---

## Handling the Kalh01 Case (Simulation Target)

Kalh01 is the reference case for testing the import wizard. The known data:

| Item | File | Location |
|------|------|----------|
| WAV | `Kalh_M_1981.wav` | `Audio_Original/Kalh01/` |
| Timestamp CSV | `Kalhori_M_1900_01 - Kaso Solav.csv` | Same folder — Audition export |
| IPA CSV | `Kalh01_transcriptions.csv` | `Audio_Processed/Kalh01_process/` |

**Known challenge:** The Audition CSV has 543 rows in H:MM:SS format (absolute). The IPA CSV has 543 rows starting with JBIL section then KLQ section. Row counts match → align by order after sorting Audition by timestamp. Lexicon start = 884s (confirmed from prior pipeline work).

**Expected simulation outcome:**
1. Linguist selects `Kalh_M_1981.wav` → PARSE reads duration (~10942s, ~3h)
2. Linguist uploads `Kalhori_M_1900_01 - Kaso Solav.csv` → PARSE detects Audition TSV format, parses 543 cue rows, previews them
3. AI Task C confirms all timestamps are H:MM:SS absolute format, starting at ~1:57:45 (=7065s)
4. Linguist uploads `Kalh01_transcriptions.csv` → AI Task B aligns by order (543 = 543, high confidence)
5. Preview table shows: concept label | timestamp | IPA — all 543 rows
6. Confirm → PARSE is ready

---

## Multi-Speaker Workflow (After First Speaker)

Once the first "reference speaker" is imported and confirmed:
- Their IPA forms become the **anchor** for AI suggestions on subsequent speakers
- Adding Speaker 2 follows the same import wizard, but now the AI suggestions panel shows cross-speaker matches based on Speaker 1's verified forms
- The linguist annotates Speaker 2 by scrubbing audio at AI-suggested timestamps and confirming or correcting

---

## Data Model Output (project.json sketch)

```json
{
  "parse_version": "4.0",
  "project_id": "sk-thesis-2026",
  "project_name": "Southern Kurdish Phylogenetics",
  "language": { "code": "sdh", "name": "Southern Kurdish" },
  "speakers": {
    "Kalh01": {
      "name": "Kalhori M 1981",
      "variety": "Kalhori",
      "sex": "M",
      "birth_year": 1981,
      "primary_wav": "audio/working/Kalh01/Kalh_M_1981.wav",
      "lexicon_start_sec": 884,
      "import_source": {
        "timestamp_csv": "Kalhori_M_1900_01 - Kaso Solav.csv",
        "ipa_csv": "Kalh01_transcriptions.csv",
        "alignment_strategy": "by_order"
      },
      "status": "reference"
    }
  }
}
```

---

## UI States

| State | Description |
|-------|-------------|
| `empty` | No project. Show import wizard immediately. |
| `importing` | Wizard open. Files being parsed/matched. |
| `confirming` | Preview table shown. Awaiting linguist confirmation. |
| `ready` | Speaker loaded. Waveform + concept list visible. |
| `annotating` | Concept selected. Annotation form shown. |
| `multi-speaker` | ≥2 speakers imported. AI suggestions panel active. |

---

## Open Questions

1. **File access model:** Can the browser access local folders directly (File System Access API)? Supported in Chrome/Edge — Safari limited. This avoids needing to upload files to the server. The linguist just selects a folder and PARSE reads it directly.

2. **AI provider (resolved):** At onboarding the user must explicitly choose **xAI/Grok** or **OpenAI**. There is no implicit default and no Anthropic/Ollama path in the current scope. The provider is stored on the speaker record and surfaced in `SpeakerImport.tsx` as a required radio selection before Start. Ollama/offline mode is deferred until a real offline-field requirement reappears.

3. **Lexicon ordering:** Does the import wizard need to know the concept list in advance (e.g. JBIL/KLQ ordering), or should it derive it from the CSV? For general use: derive from CSV. For PARSE thesis mode: use the known 85-item list as a validation schema.

4. **Praat/ELAN priority:** These are the most common formats in academic linguistics. Praat TextGrid parser should be the first format to implement after CSV.

5. **What if timestamps are wrong?** The linguist may have made cue errors. After import, the waveform view must make it easy to nudge timestamps by dragging region boundaries. Corrections are saved back to the internal model (not to the original CSV).

---

## Implementation Priority

| Priority | Component | Notes |
|----------|-----------|-------|
| P1 | CSV import wizard (Audition format) | Needed to simulate Kalh01 import |
| P1 | AI column-mapping + alignment (Task B & D) | Core AI layer |
| P1 | Waveform + concept list after import | The working dashboard |
| P2 | TextGrid import | Most common academic format |
| P2 | Multi-WAV + offset resolution (Task A) | Needed for Khan01-04 |
| P3 | ELAN import | Useful but less urgent |
| P3 | Timestamp nudge / region editing | Quality of life |
| P3 | Export back to TextGrid / ELAN | Interoperability |

---

*This document captures the design intent as of 2026-03-25. Update as decisions are made during implementation.*
