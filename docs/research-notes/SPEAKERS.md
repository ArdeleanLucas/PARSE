# SPEAKERS.md — Personal Research Data Inventory

> **Personal research data inventory — not a project plan.**
> This file tracks which audio data, transcriptions, and pipeline artefacts exist for each speaker in Lucas's Southern Kurdish thesis dataset. It is specific to that dataset and not authoritative for PARSE itself.

Last updated: 2026-03-24

Update whenever new processing is completed on the thesis corpus.

---

## Tier 1 — Fully normalized, peaks generated (PARSE-ready)

These speakers are complete through step 3 of the pipeline.

| Speaker | WAV (Audio_Original) | WAV size | Audition CSV | Normalized WAV (Audio_Working) | Peaks |
|---------|----------------------|----------|--------------|-------------------------------|-------|
| Fail01  | `Fail01/Faili_M_1984.wav` | 3.3G | `Faili_M_1984.csv` | `Fail01/Faili_M_1984.wav` | `peaks/Fail01.json` (7.5MB) |
| Fail02  | `Fail02/SK_Faili_F_1968.wav` | 1.5G | `Faili_F_1968.csv` | `Fail02/SK_Faili_F_1968.wav` | `peaks/Fail02.json` (3.3MB) |
| Kalh01  | `Kalh01/Kalh_M_1981.wav` | 4.0G | `Kalhori_M_1900_01 - Kaso Solav.csv` | `Kalh01/Kalh_M_1981.wav` | `peaks/Kalh01.json` (9.1MB) |
| Mand01  | `Mand01/Mandali_M_1900_01.wav` | 4.3G | `Mandali_M_1900_01 - Kaso Solav.csv` | `Mand01/Mandali_M_1900_01.wav` | `peaks/Mand01.json` (9.2MB) |
| Qasr01  | `Qasr01/Qasrashirin_M_1973.wav` | 7.2G | `Qasrashirin_M_1973_01 - Kaso Solav.csv` | `Qasr01/Qasrashirin_M_1973.wav` | `peaks/Qasr01.json` (16MB) |
| Saha01  | `Saha01/Sahana_F_1978.wav` | 2.9G | `Sahana_F_1978_01 - Kaso Solav.csv` | `Saha01/Sahana_F_1978.wav` | `peaks/Saha01.json` (8.7MB) |

**Normalization:** -16 LUFS, 16-bit PCM mono 44.1 kHz (ffmpeg loudnorm two-pass)

**Lexicon start offsets (seconds into full recording):**
- Fail01: +506s, Fail02: +335s, Kalh01: +884s, Mand01: 0, Qasr01: 0, Saha01: 0

**Processed segments** (old pipeline, `Audio_Processed/`):
- Fail01: 523 segments | Fail02: 131 | Kalh01: 543 | Mand01: 517 | Qasr01: 505 | Saha01: 497

**Transcription CSVs** (`Audio_Processed/<Speaker>_process/<Speaker>_transcriptions.csv`):
- Format: `lexeme_id,ortho,ipa,audio_path,status`
- Available for: Fail01, Fail02, Kalh01 (not yet confirmed for Mand01, Qasr01, Saha01 — check)

---

## Tier 2 — Have WAV + Audition CSV, not yet normalized

These speakers have the same data quality as Tier 1 but haven't been run through
`normalize_audio.py` or `generate_peaks.py` yet.

| Speaker | WAV (Audio_Original) | WAV size | Audition CSV | Notes |
|---------|----------------------|----------|--------------|-------|
| Kala01  | `Kala01/Kalari_F_2001.wav` | 3.1G | `Kalari_F_2001.csv` | — |
| Kifr01  | `Kifr01/Kifri_M_1990_01.wav` | 3.7G | `Kifri_M_1990_01_01 - Kaso Solav.csv` | — |
| Zang01  | `Zang01/Zangana_F_1987.wav` | 1.9G | `Zangana_F_1987_01 - Kaso Solav.csv` | — |

---

## Tier 3 — Khan speakers (video/multi-WAV, no Audition CSV, segments already done)

These speakers have no Audition-style timestamp CSV for the full recording.
Segmentation was done via a separate pipeline (video alignment / cluster detection).
The processed segments and IPA transcriptions already exist.

### Khan01
- **Original WAVs:** (3 files — recording sessions)
  - `Khan01_missing/2023043001.wav` (1.9G)
  - `Khan01_missing/20230502_khanaqini_01_02.wav` (1.6G)
  - `Khan01_missing/REC00002.wav` (1.2G) ← primary (used by old pipeline)
- **Segments:** 286 in `Audio_Processed/Khan01_process/segments/`
- **Transcriptions:** `Khan01_process/Khan01_transcriptions.csv` (287 rows)
  - Format: `lexeme_id,ortho,ipa,audio_path,status`
  - ortho = noisy Whisper (unreliable); IPA = human-entered (reliable)
  - lexeme_id encodes concept name: e.g. `JBIL_001_A_one_Khan01`

### Khan02
- **Original WAV:** `Khan02_missing/khanaqini_F_1967.wav` (4.1G)
- **Segments:** 503 in `Audio_Processed/Khan02_process/segments/`
- **Transcriptions:** `Khan02_process/Khan02_transcriptions.csv` (504 rows)

### Khan03 ⚠️ VIDEO SPEAKER
- **Source:** 3 MP4 video files (not audio-only)
  - `Khan03_missing/C0401.MP4` (78GB) + `C0401_audio.wav` (197M)
  - `Khan03_missing/C0402.MP4` (41GB) + `C0402_audio.wav` (101M)
  - `Khan03_missing/C0403.MP4` (5.3GB) + `C0403_audio.wav` (14M)
- **Transcript JSONs already extracted:**
  - `C0401_transcript_turbo.json` (1809 entries, Whisper word-level)
  - `C0402_transcript_turbo.json`
  - `C0403_transcript_turbo.json`
  - `detected_clusters.json` (575 cluster entries with start/end/word)
  - `jbil_sequence.json` (concept order list)
- **Final segmentation:** `Khan03_process/Khan03_final_segmentation.csv`
  - Format: `jbil_num,concept,filename,start,end,source,turbo_word,ok`
  - This is the equivalent of the Audition CSV (timestamp-based)
- **Segments:** 284 in `Audio_Processed/Khan03_process/segments/`
- **Transcriptions:** `Khan03_process/Khan03_transcriptions.csv` (format: `filename,ortho,ipa,status`)
- **Other pipeline files:** `Khan03_alignment_v2.json`, `Khan03_filtered_clusters.json`,
  `Khan03_final_assignment.json`, `Khan03_realignment.csv`, `Khan03_review.TextGrid`

### Khan04
- **Original WAV:** `Khan04_missing/Khanaqin_F_2000.wav` (1.6G)
- **Segments:** 138 in `Audio_Processed/Khan04_process/segments/`
- **Transcriptions:** `Khan04_process/Khan04_transcriptions.csv` (139 rows)

---

## Excluded Speakers

These speakers are **NOT part of the thesis project** and will not be processed.

| Speaker | Notes |
|---------|-------|
| Hala01  | Central Kurdish (Halabja/CK variety) — not associated with this project |
| Gora01  | Gorani — not associated with this project |

---

## New Lexicons (unassigned)

Short recordings (not full interviews). May be word-list only recordings.
No speaker metadata assigned yet. Located in `Audio_Original/New_Lexicons/`.

| File | Size | Notes |
|------|------|-------|
| `Kur_Kirmanshah_m_lexicon.WAV` | 51M | Male, Kirmanshah variety |
| `kur_Qasr_f_1967_lexicon.WAV` | 75M | Female, Qasr-e Shirin, born 1967 |
| `kur_gahvara_m_1962_lexicon.WAV` | 72M | Male, Gahvara variety, born 1962 |
| `sk_Qurve_m_1988-lexicon.m4a` | 20M | Male, Qurve variety, born 1988 |

---

## review_data.json

- **Location:** thesis corpus root (`review_data.json`)
- **Generated:** 2026-03-19, 448KB
- **Covers:** Fail01, Fail02, Kalh01, Mand01, Qasr01, Saha01 (6 speakers)
- **Method:** edit_distance_clustering, threshold 0.6
- **Concepts:** 82 total
- Used as input to `generate_ai_suggestions.py`

---

## Pipeline Step Status (2026-03-24)

| Step | Script | Tier 1 (6 spk) | Tier 2 (4 spk) | Khan (4 spk) |
|------|--------|----------------|----------------|--------------|
| 1. Normalize | `normalize_audio.py` | ✅ done | ❌ todo | ❌ todo |
| 2. Source index | `generate_source_index.py` | ✅ done | ❌ todo | ❌ todo |
| 3. Peaks | `generate_peaks.py` | ✅ done | ❌ todo | ❌ todo |
| 4. Coarse transcripts | `reformat_transcripts.py` | ❌ todo | ❌ todo | segments exist |
| 5. AI suggestions | `generate_ai_suggestions.py` | ❌ todo | ❌ todo | ❌ todo |

---

## Related repos

- PARSE application: `ArdeleanLucas/PARSE` (GitHub)
- Thesis corpus / scripts: `ArdeleanLucas/thesis` (GitHub)

Machine-specific working paths (WSL layout, workspace directories) belong in a
personal notes file, not in the public repo. Keep those out of this document.
