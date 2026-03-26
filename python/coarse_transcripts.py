#!/usr/bin/env python3
"""
build_coarse_transcripts.py — Convert existing pipeline data into
coarse_transcripts/<Speaker>.json files for use by generate_ai_suggestions.py.

Three conversion strategies depending on available data:

  Strategy A — Audition CSV + transcription CSV (Fail01, Fail02, Kalh01)
    Timestamps come from the Audition cue export; text comes from transcription CSV.

  Strategy B — Audition CSV only (Mand01, Qasr01, Saha01, Kala01, Kifr01, Zang01)
    Timestamps from Audition CSV; concept name used as text (English label from
    the Name column, e.g. "(1.2)- forehead" → "forehead").

  Strategy C — manifest.json + transcription CSV (Khan01, Khan02, Khan04)
    Timestamps (audio_start, duration) from manifest; IPA text from transcriptions CSV.

  Strategy D — final_segmentation.csv + transcription CSV (Khan03, video speaker)
    Timestamps from Khan03_final_segmentation.csv (start/end/source);
    IPA text from Khan03_transcriptions.csv. Multiple source WAVs → separate entries.

Output schema (per speaker):
  {
    "source_wav": "audio/working/<Speaker>/<primary>.wav",
    "segments": [
      {"start": <float>, "end": <float>, "text": "<ortho or concept>"},
      ...
    ]
  }

For Khan03 (multi-WAV), one JSON file is written per source WAV:
  Khan03_C0401.json, Khan03_C0402.json, Khan03_C0403.json

Usage:
    python build_coarse_transcripts.py \\
        --thesis-dir C:/Users/Lucas/Thesis \\
        --output-dir coarse_transcripts/
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Audition CSV timestamp parsing
# ---------------------------------------------------------------------------

def parse_audition_time(time_str: str) -> float:
    """Parse Audition cue time format H:MM:SS.mmm → seconds."""
    time_str = time_str.strip()
    # Format: H:MM:SS.mmm or M:SS.mmm
    parts = time_str.split(':')
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = int(parts[0]), float(parts[1])
            return m * 60 + s
        else:
            return float(time_str)
    except (ValueError, IndexError):
        return 0.0


def parse_audition_duration(dur_str: str) -> float:
    """Parse Audition duration format M:SS.mmm → seconds."""
    return parse_audition_time(dur_str)


def clean_concept_name(raw: str) -> str:
    """Extract the concept label from an Audition Name field.
    e.g. '(1.2)- forehead' → 'forehead'
         '(1.4)- eyebrow A' → 'eyebrow'
    """
    # Strip leading numbering like (1.2)-
    name = re.sub(r'^\([^)]+\)\s*[-–]\s*', '', raw).strip()
    # Strip trailing variant markers (A, B, C, ' A', etc.)
    name = re.sub(r'\s+[A-D]$', '', name).strip()
    return name if name else raw.strip()


def load_audition_csv(path: Path) -> list[dict]:
    """Load an Adobe Audition cue export CSV.
    Returns list of {name, start_sec, end_sec}.
    """
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh, delimiter='\t')
        for row in reader:
            name = row.get('Name', '').strip()
            start_raw = row.get('Start', '').strip()
            dur_raw = row.get('Duration', '').strip()
            if not start_raw:
                continue
            start_sec = parse_audition_time(start_raw)
            dur_sec = parse_audition_duration(dur_raw) if dur_raw else 1.0
            if dur_sec <= 0:
                dur_sec = 1.0
            rows.append({
                'name': name,
                'start_sec': start_sec,
                'end_sec': start_sec + dur_sec,
            })
    return rows


# ---------------------------------------------------------------------------
# Transcription CSV loaders
# ---------------------------------------------------------------------------

def load_transcriptions_csv(path: Path) -> dict[str, dict]:
    """Load a <Speaker>_transcriptions.csv.
    Returns dict keyed by lexeme_id (or filename stem) → {ortho, ipa}.
    """
    result = {}
    with open(path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        # Two formats:
        # A: lexeme_id, ortho, ipa, audio_path, status
        # B: filename, ortho, ipa, status  (Khan03)
        id_field = 'lexeme_id' if 'lexeme_id' in fieldnames else 'filename'
        for row in reader:
            key = row.get(id_field, '').strip()
            if not key:
                continue
            # Normalise key: strip path prefix and .wav suffix
            key = Path(key).stem
            result[key] = {
                'ortho': row.get('ortho', '').strip(),
                'ipa': row.get('ipa', '').strip(),
            }
    return result


# ---------------------------------------------------------------------------
# Strategy A: Audition CSV + transcription CSV
# ---------------------------------------------------------------------------

def strategy_a(
    speaker: str,
    audition_csv: Path,
    transcriptions_csv: Path,
    working_wav: str,
) -> dict:
    """Pair Audition cue timestamps with IPA/ortho from transcription CSV.
    Uses the concept name from the Audition 'Name' field as fallback text.
    """
    cues = load_audition_csv(audition_csv)
    trans = load_transcriptions_csv(transcriptions_csv)

    # Build a concept-name→IPA lookup from transcriptions (concept in lexeme_id)
    # Lexeme IDs look like JBIL_001_A_one_Fail01 → concept = "one"
    concept_to_ipa = {}
    concept_to_ortho = {}
    for stem, data in trans.items():
        m = re.search(r'_([a-z_]+)_' + re.escape(speaker), stem, re.IGNORECASE)
        if m:
            concept = m.group(1).replace('_', ' ')
            if data['ipa']:
                concept_to_ipa[concept] = data['ipa']
            if data['ortho']:
                concept_to_ortho[concept] = data['ortho']

    segments = []
    for cue in cues:
        concept = clean_concept_name(cue['name'])
        # Prefer Kurdish ortho, fall back to concept name in English
        text = concept_to_ortho.get(concept) or concept_to_ortho.get(concept.lower()) or concept
        segments.append({
            'start': round(cue['start_sec'], 3),
            'end': round(cue['end_sec'], 3),
            'text': text,
        })

    return {'source_wav': working_wav, 'segments': segments}


# ---------------------------------------------------------------------------
# Strategy B: Audition CSV only (no transcription CSV)
# ---------------------------------------------------------------------------

def strategy_b(
    speaker: str,
    audition_csv: Path,
    working_wav: str,
) -> dict:
    """Use Audition cue timestamps + English concept name as text proxy."""
    cues = load_audition_csv(audition_csv)
    segments = []
    for cue in cues:
        concept = clean_concept_name(cue['name'])
        segments.append({
            'start': round(cue['start_sec'], 3),
            'end': round(cue['end_sec'], 3),
            'text': concept,
        })
    return {'source_wav': working_wav, 'segments': segments}


# ---------------------------------------------------------------------------
# Strategy C: manifest.json + transcription CSV (Khan01, Khan02, Khan04)
# ---------------------------------------------------------------------------

def strategy_c(
    speaker: str,
    manifest_json: Path,
    transcriptions_csv: Path,
    working_wav: str,
) -> dict:
    """Use manifest audio_start/duration timestamps + IPA from transcription CSV."""
    with open(manifest_json, encoding='utf-8') as fh:
        manifest = json.load(fh)

    trans = load_transcriptions_csv(transcriptions_csv)

    items = manifest.get('items', [])
    segments = []
    for item in items:
        filename_stem = Path(item.get('filename', '')).stem
        audio_start = float(item.get('audio_start', 0.0))
        duration = float(item.get('duration', 1.0))
        if duration <= 0:
            duration = 1.0

        data = trans.get(filename_stem, {})
        # Prefer IPA (human-entered), fall back to concept name
        text = data.get('ipa') or data.get('ortho') or item.get('concept', '')

        segments.append({
            'start': round(audio_start, 3),
            'end': round(audio_start + duration, 3),
            'text': text,
        })

    return {'source_wav': working_wav, 'segments': segments}


# ---------------------------------------------------------------------------
# Strategy D: Khan03 final_segmentation.csv (multi-WAV video speaker)
# ---------------------------------------------------------------------------

def strategy_d(
    speaker: str,
    final_seg_csv: Path,
    transcriptions_csv: Path,
    working_wav_dir: str,
) -> dict[str, dict]:
    """Build one transcript entry per source WAV file for Khan03.
    Returns a dict: source_name → coarse_transcript_dict.
    """
    trans = load_transcriptions_csv(transcriptions_csv)

    # Group cue rows by source WAV
    by_source: dict[str, list] = {}
    with open(final_seg_csv, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            source = row.get('source', '').strip()   # e.g. C0401
            filename = row.get('filename', '').strip()
            start = float(row.get('start', 0.0))
            end = float(row.get('end', start + 1.0))
            if end <= start:
                end = start + 1.0

            filename_stem = Path(filename).stem
            data = trans.get(filename_stem, {})
            text = data.get('ipa') or data.get('ortho') or row.get('concept', '')

            by_source.setdefault(source, []).append({
                'start': round(start, 3),
                'end': round(end, 3),
                'text': text,
            })

    result = {}
    for source_name, segs in by_source.items():
        segs.sort(key=lambda s: s['start'])
        wav_filename = f'{source_name}_audio.wav'
        result[source_name] = {
            'source_wav': f'{working_wav_dir}/{wav_filename}',
            'segments': segs,
        }
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--thesis-dir', required=True, help='Root of C:/Users/Lucas/Thesis (WSL path OK)')
    parser.add_argument('--output-dir', required=True, help='Where to write coarse_transcripts/*.json')
    args = parser.parse_args()

    thesis = Path(args.thesis_dir).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    orig = thesis / 'Audio_Original'
    processed = thesis / 'Audio_Processed'

    # -----------------------------------------------------------------------
    # Speaker definitions
    # -----------------------------------------------------------------------

    speakers_a = [
        # (speaker_id, audition_csv_path, transcriptions_csv_path, working_wav_rel)
        ('Fail01',
         orig / 'Fail01' / 'Faili_M_1984.csv',
         processed / 'Fail01_process' / 'Fail01_transcriptions.csv',
         'audio/working/Fail01/Faili_M_1984.wav'),
        ('Fail02',
         orig / 'Fail02' / 'Faili_F_1968.csv',
         processed / 'Fail02_process' / 'Fail02_transcriptions.csv',
         'audio/working/Fail02/SK_Faili_F_1968.wav'),
        ('Kalh01',
         orig / 'Kalh01' / 'Kalhori_M_1900_01 - Kaso Solav.csv',
         processed / 'Kalh01_process' / 'Kalh01_transcriptions.csv',
         'audio/working/Kalh01/Kalh_M_1981.wav'),
    ]

    speakers_b = [
        # (speaker_id, audition_csv_path, working_wav_rel)
        ('Mand01',
         orig / 'Mand01' / 'Mandali_M_1900_01 - Kaso Solav.csv',
         'audio/working/Mand01/Mandali_M_1900_01.wav'),
        ('Qasr01',
         orig / 'Qasr01' / 'Qasrashirin_M_1973_01 - Kaso Solav.csv',
         'audio/working/Qasr01/Qasrashirin_M_1973.wav'),
        ('Saha01',
         orig / 'Saha01' / 'Sahana_F_1978_01 - Kaso Solav.csv',
         'audio/working/Saha01/Sahana_F_1978.wav'),
        ('Kala01',
         orig / 'Kala01' / 'Kalari_F_2001.csv',
         'audio/working/Kala01/Kalari_F_2001.wav'),
        ('Kifr01',
         orig / 'Kifr01' / 'Kifri_M_1990_01_01 - Kaso Solav.csv',
         'audio/working/Kifr01/Kifri_M_1990_01.wav'),
        ('Zang01',
         orig / 'Zang01' / 'Zangana_F_1987_01 - Kaso Solav.csv',
         'audio/working/Zang01/Zangana_F_1987.wav'),
    ]

    speakers_c = [
        # (speaker_id, manifest_path, transcriptions_csv_path, working_wav_rel)
        ('Khan01',
         processed / 'Khan01_process' / 'Khan01_manifest.json',
         processed / 'Khan01_process' / 'Khan01_transcriptions.csv',
         'audio/working/Khan01/REC00002.wav'),
        ('Khan02',
         processed / 'Khan02_process' / 'Khan02_manifest.json',
         processed / 'Khan02_process' / 'Khan02_transcriptions.csv',
         'audio/working/Khan02/khanaqini_F_1967.wav'),
        ('Khan04',
         processed / 'Khan04_process' / 'Khan04_manifest.json',
         processed / 'Khan04_process' / 'Khan04_transcriptions.csv',
         'audio/working/Khan04/Khanaqin_F_2000.wav'),
    ]

    # Khan03 — Strategy D
    khan03_seg_csv = processed / 'Khan03_process' / 'Khan03_final_segmentation.csv'
    khan03_trans_csv = processed / 'Khan03_process' / 'Khan03_transcriptions.csv'
    khan03_working_dir = 'audio/working/Khan03'

    # -----------------------------------------------------------------------
    # Process
    # -----------------------------------------------------------------------

    total = 0
    errors = 0

    print('--- Strategy A (Audition CSV + transcriptions) ---')
    for speaker, aud_csv, trans_csv, working_wav in speakers_a:
        try:
            if not aud_csv.exists():
                print(f'  SKIP {speaker}: missing audition CSV {aud_csv}')
                continue
            if not trans_csv.exists():
                print(f'  WARN {speaker}: no transcription CSV, falling back to Strategy B')
                result = strategy_b(speaker, aud_csv, working_wav)
            else:
                result = strategy_a(speaker, aud_csv, trans_csv, working_wav)
            out_path = out_dir / f'{speaker}.json'
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'  WROTE {speaker}.json ({len(result["segments"])} segments)')
            total += 1
        except Exception as exc:
            print(f'  ERROR {speaker}: {exc}', file=sys.stderr)
            errors += 1

    print('\n--- Strategy B (Audition CSV only) ---')
    for speaker, aud_csv, working_wav in speakers_b:
        try:
            if not aud_csv.exists():
                print(f'  SKIP {speaker}: missing audition CSV {aud_csv}')
                continue
            result = strategy_b(speaker, aud_csv, working_wav)
            out_path = out_dir / f'{speaker}.json'
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'  WROTE {speaker}.json ({len(result["segments"])} segments)')
            total += 1
        except Exception as exc:
            print(f'  ERROR {speaker}: {exc}', file=sys.stderr)
            errors += 1

    print('\n--- Strategy C (manifest.json + transcriptions) ---')
    for speaker, manifest_json, trans_csv, working_wav in speakers_c:
        try:
            if not manifest_json.exists():
                print(f'  SKIP {speaker}: missing manifest {manifest_json}')
                continue
            result = strategy_c(speaker, manifest_json, trans_csv, working_wav)
            out_path = out_dir / f'{speaker}.json'
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'  WROTE {speaker}.json ({len(result["segments"])} segments)')
            total += 1
        except Exception as exc:
            print(f'  ERROR {speaker}: {exc}', file=sys.stderr)
            errors += 1

    print('\n--- Strategy D (Khan03 video — multi-WAV) ---')
    try:
        if not khan03_seg_csv.exists():
            print(f'  SKIP Khan03: missing {khan03_seg_csv}')
        else:
            results = strategy_d('Khan03', khan03_seg_csv, khan03_trans_csv, khan03_working_dir)
            for source_name, result in results.items():
                out_path = out_dir / f'Khan03_{source_name}.json'
                out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f'  WROTE Khan03_{source_name}.json ({len(result["segments"])} segments)')
                total += 1
    except Exception as exc:
        print(f'  ERROR Khan03: {exc}', file=sys.stderr)
        errors += 1

    print(f'\nDone. Wrote {total} transcript files, {errors} errors.')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
