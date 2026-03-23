#!/usr/bin/env python3
"""
reformat_transcripts.py — Convert coarse alignment JSON to simplified CoarseTranscript schema.

Converts *_coarse.json files produced by the alignment pipeline into the simplified
per-speaker transcript format expected by the Source Explorer.

Output schema (CoarseTranscript):
  {
    "speaker": "Mand01",
    "source_wav": "Audio_Original/Mand01/Mandali_M_1900_01.wav",
    "duration_sec": 11924.0,
    "segments": [
      {"start": 0.0, "end": 3.0, "text": "..."},
      ...
    ]
  }

Usage (single file):
  python reformat_transcripts.py \
    --input alignment/Mand01_Mandali_M_1900_01_coarse.json \
    --speaker Mand01 \
    --source-wav "Audio_Original/Mand01/Mandali_M_1900_01.wav" \
    --duration 11924.0 \
    --output coarse_transcripts/Mand01.json

Usage (batch mode — process all *_coarse.json in a directory):
  python reformat_transcripts.py \
    --batch-dir alignment/ \
    --output-dir coarse_transcripts/ \
    [--speaker SPEAKER_ID]  # optional filter in batch mode

In batch mode, --speaker / --source-wav / --duration are optional.
If omitted, the script tries to infer them from the filename and the JSON content.
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Segment extraction helpers — permissive about input shape
# ---------------------------------------------------------------------------

SEGMENT_KEYS = [
    "segments",
    "words",
    "results",
    "utterances",
    "chunks",
    "transcript_segments",
    "output",
    "data",
]

START_KEYS = ["start", "start_sec", "start_time", "begin", "offset", "from"]
END_KEYS = ["end", "end_sec", "end_time", "finish", "to", "stop"]
TEXT_KEYS = ["text", "transcript", "content", "word", "label", "value"]

DURATION_KEYS = [
    "duration",
    "duration_sec",
    "total_duration",
    "length",
    "duration_seconds",
]


def _first_existing(d: dict, keys: list):
    """Return the first non-None value for the given keys, or None."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _normalize_relative_path(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = value.strip().replace("\\", "/")
    return normalized


def extract_segments(data, source_path: str) -> list:
    """
    Try to pull a segment list out of the top-level JSON object.
    Returns a list of raw segment dicts (may need further normalisation).
    Raises ValueError with a helpful message if no segments found.
    """
    if isinstance(data, list):
        if len(data) > 0:
            return data
        raise ValueError(f"Input JSON in '{source_path}' is an empty list; no segments found")

    if not isinstance(data, dict):
        raise ValueError(
            f"Top-level JSON in '{source_path}' must be an object or a list, "
            f"got {type(data).__name__}"
        )

    for key in SEGMENT_KEYS:
        if key in data and isinstance(data[key], list) and len(data[key]) > 0:
            return data[key]

    for val in data.values():
        if isinstance(val, dict):
            for key in SEGMENT_KEYS:
                if key in val and isinstance(val[key], list) and len(val[key]) > 0:
                    return val[key]

    checked = ", ".join(SEGMENT_KEYS)
    raise ValueError(
        f"Could not find a segment list in '{source_path}'.\n"
        f"Tried keys: {checked}\n"
        f"Top-level keys present: {list(data.keys())}"
    )


def normalise_segment(raw, idx: int, source_path: str) -> dict:
    """
    Convert a raw segment dict to {start, end, text}.
    Raises ValueError if required fields are missing or invalid.
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"segment[{idx}] in '{source_path}' must be an object, got {type(raw).__name__}"
        )

    start = _first_existing(raw, START_KEYS)
    end = _first_existing(raw, END_KEYS)
    text = _first_existing(raw, TEXT_KEYS)

    errors = []
    if start is None:
        errors.append(f"  segment[{idx}]: missing start time (tried: {START_KEYS})")
    if end is None:
        errors.append(f"  segment[{idx}]: missing end time (tried: {END_KEYS})")
    if text is None:
        text = ""

    if errors:
        raise ValueError(
            f"Segment parsing errors in '{source_path}':\n"
            + "\n".join(errors)
            + f"\n  Segment keys present: {list(raw.keys())}"
        )

    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Segment[{idx}] in '{source_path}': cannot convert start/end to float — {exc}"
        ) from exc

    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError(
            f"Segment[{idx}] in '{source_path}': start/end must be finite numbers"
        )
    if start < 0:
        raise ValueError(
            f"Segment[{idx}] in '{source_path}': start time must be >= 0, got {start}"
        )
    if end < start:
        raise ValueError(
            f"Segment[{idx}] in '{source_path}': end time ({end}) < start time ({start})"
        )

    return {"start": start, "end": end, "text": str(text)}


def infer_speaker_from_filename(path: Path) -> str:
    """
    Attempt to infer speaker ID from filename.
    E.g. "Mand01_Mandali_M_1900_01_coarse.json" → "Mand01"
    Pattern: first token before underscore that matches [A-Za-z]+[0-9]+
    """
    stem = path.stem
    stem = re.sub(r"_coarse$", "", stem, flags=re.IGNORECASE)
    parts = stem.split("_")
    for part in parts:
        if re.match(r"^[A-Za-z]{2,8}\d{1,4}$", part):
            return part
    return parts[0] if parts else stem


def infer_duration_from_segments(segments: list) -> float:
    """Return the end time of the last segment as an approximation of duration."""
    if not segments:
        return 0.0
    return max(s["end"] for s in segments)


def derive_output_stem(path: Path) -> str:
    """Return the filename stem with trailing _coarse removed."""
    return re.sub(r"_coarse$", "", path.stem, flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Core reformatter
# ---------------------------------------------------------------------------

def reformat(
    input_path: str,
    speaker: str | None,
    source_wav: str | None,
    duration: float | None,
    output_path: str,
) -> None:
    """
    Load a coarse alignment JSON, reformat it, and write the simplified transcript.
    """
    input_path = str(input_path)
    output_path = str(output_path)

    try:
        with open(input_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in '{input_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    if speaker is None:
        speaker = _first_existing(data, ["speaker", "speaker_id", "speaker_name"])
        if speaker is None:
            speaker = infer_speaker_from_filename(Path(input_path))
            print(
                f"  [INFO] --speaker not provided; inferred from filename: '{speaker}'",
                file=sys.stderr,
            )

    if not isinstance(speaker, str) or not speaker.strip():
        print(f"ERROR: Could not determine speaker for '{input_path}'.", file=sys.stderr)
        sys.exit(1)
    speaker = speaker.strip()

    if source_wav is None:
        source_wav = _first_existing(
            data,
            [
                "source_wav",
                "audio_file",
                "audio_path",
                "wav_path",
                "file",
                "input_file",
                "filename",
            ],
        )

    if source_wav is None:
        print(
            f"ERROR: Could not determine source_wav for '{input_path}'. "
            "Provide --source-wav or include a top-level source_wav/audio_path field.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        source_wav = _normalize_relative_path(source_wav, "source_wav")
    except ValueError as exc:
        print(f"ERROR: {exc} in '{input_path}'", file=sys.stderr)
        sys.exit(1)

    try:
        raw_segments = extract_segments(data, input_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    normalised = []
    errors = []
    for i, raw in enumerate(raw_segments):
        try:
            seg = normalise_segment(raw, i, input_path)
            normalised.append(seg)
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        print(
            f"ERROR: Failed to parse {len(errors)} segment(s) in '{input_path}':\n"
            + "\n".join(errors),
            file=sys.stderr,
        )
        sys.exit(1)

    normalised.sort(key=lambda s: s["start"])

    if duration is None:
        duration = _first_existing(data, DURATION_KEYS)
        if duration is not None:
            try:
                duration = float(duration)
            except (TypeError, ValueError):
                duration = None
        if duration is None:
            duration = infer_duration_from_segments(normalised)
            print(
                f"  [INFO] --duration not provided; inferred from last segment end: {duration:.1f}s",
                file=sys.stderr,
            )

    try:
        duration = float(duration)
    except (TypeError, ValueError):
        print(f"ERROR: duration for '{input_path}' is not numeric.", file=sys.stderr)
        sys.exit(1)

    if not math.isfinite(duration) or duration < 0:
        print(
            f"ERROR: duration for '{input_path}' must be a finite non-negative number.",
            file=sys.stderr,
        )
        sys.exit(1)

    output = {
        "speaker": speaker,
        "source_wav": source_wav,
        "duration_sec": float(duration),
        "segments": normalised,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError as exc:
        print(f"ERROR: Cannot write output file '{output_path}': {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"ERROR: Invalid transcript data for '{input_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"  OK  {os.path.basename(input_path)}"
        f" → {output_path}"
        f" ({len(normalised)} segments, {duration:.1f}s)",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

def batch_reformat(
    batch_dir: str,
    output_dir: str,
    speaker_filter: str | None,
    source_wav: str | None,
    duration: float | None,
) -> None:
    """
    Process all *_coarse.json files in batch_dir, writing output to output_dir.

    For speakers with multiple input files, output filenames include the input
    stem (e.g. Khan01_REC00002.json) to avoid silent overwrite.
    """
    batch_dir = Path(batch_dir)
    output_dir = Path(output_dir)

    coarse_files = sorted(batch_dir.glob("*_coarse.json"))
    if not coarse_files:
        coarse_files = sorted(batch_dir.glob("*.json"))

    if not coarse_files:
        print(
            f"ERROR: No *_coarse.json files found in '{batch_dir}'.", file=sys.stderr
        )
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    filtered_files = []
    for coarse_file in coarse_files:
        inferred_speaker = infer_speaker_from_filename(coarse_file)
        if speaker_filter and inferred_speaker.lower() != speaker_filter.lower():
            continue
        filtered_files.append((coarse_file, inferred_speaker))

    speaker_counts = {}
    for _, inferred_speaker in filtered_files:
        speaker_counts[inferred_speaker] = speaker_counts.get(inferred_speaker, 0) + 1

    processed = 0
    skipped = len(coarse_files) - len(filtered_files)

    for coarse_file, inferred_speaker in filtered_files:
        if speaker_counts[inferred_speaker] > 1:
            out_stem = derive_output_stem(coarse_file)
        else:
            out_stem = inferred_speaker

        out_file = output_dir / f"{out_stem}.json"

        reformat(
            input_path=str(coarse_file),
            speaker=inferred_speaker,
            source_wav=source_wav,
            duration=duration,
            output_path=str(out_file),
        )
        processed += 1

    print(
        f"\nBatch complete: {processed} file(s) processed, {skipped} skipped.",
        file=sys.stderr,
    )
    if processed == 0 and speaker_filter:
        print(
            f"  (No files matched --speaker '{speaker_filter}'. Check the filename pattern.)",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reformat_transcripts.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    single = parser.add_argument_group("Single-file mode")
    single.add_argument(
        "--input", "-i",
        metavar="FILE",
        help="Path to the input *_coarse.json file.",
    )
    single.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Path to write the reformatted CoarseTranscript JSON.",
    )

    meta = parser.add_argument_group("Metadata (optional in batch mode, inferred if missing)")
    meta.add_argument(
        "--speaker", "-s",
        metavar="SPEAKER_ID",
        help='Speaker ID, e.g. "Mand01". Inferred from filename if omitted.',
    )
    meta.add_argument(
        "--source-wav",
        metavar="PATH",
        help='Relative path to the source WAV, e.g. "Audio_Original/Mand01/Mandali_M_1900_01.wav".',
    )
    meta.add_argument(
        "--duration",
        metavar="SECONDS",
        type=float,
        help="Total recording duration in seconds. Inferred from last segment end if omitted.",
    )

    batch = parser.add_argument_group("Batch mode")
    batch.add_argument(
        "--batch-dir",
        metavar="DIR",
        help="Directory containing *_coarse.json files to process.",
    )
    batch.add_argument(
        "--output-dir",
        metavar="DIR",
        help="Directory to write reformatted JSON files (one per speaker).",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    is_batch = bool(args.batch_dir or args.output_dir)
    is_single = bool(args.input or args.output)

    if is_batch and is_single:
        parser.error(
            "Specify either single-file mode (--input / --output) or batch mode (--batch-dir / --output-dir), not both."
        )

    if not is_batch and not is_single:
        parser.print_help()
        sys.exit(0)

    if is_batch:
        if not args.batch_dir:
            parser.error("--batch-dir is required for batch mode.")
        if not args.output_dir:
            parser.error("--output-dir is required for batch mode.")

        print(
            f"Batch mode: {args.batch_dir} → {args.output_dir}",
            file=sys.stderr,
        )
        batch_reformat(
            batch_dir=args.batch_dir,
            output_dir=args.output_dir,
            speaker_filter=args.speaker,
            source_wav=args.source_wav,
            duration=args.duration,
        )
    else:
        if not args.input:
            parser.error("--input FILE is required in single-file mode.")
        if not args.output:
            parser.error("--output FILE is required in single-file mode.")

        reformat(
            input_path=args.input,
            speaker=args.speaker,
            source_wav=args.source_wav,
            duration=args.duration,
            output_path=args.output,
        )


if __name__ == "__main__":
    main()
