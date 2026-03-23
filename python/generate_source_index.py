#!/usr/bin/env python3
"""
generate_source_index.py — Build source_index.json from a speaker manifest.

Reads a JSON manifest (produced by an ffprobe scan) and transforms it into
the SourceIndex schema consumed by the Source Explorer JS modules.

Usage:
    python generate_source_index.py --manifest manifest.json --output source_index.json

Manifest schema (input):
    {
      "speakers": {
        "<SpeakerId>": {
          "wav_files": [
            {
              "path": "Audio_Original/...",
              "duration_sec": <float>,
              "file_size_bytes": <int>,
              "bit_depth": <int>,
              "sample_rate": <int>,
              "channels": <int>,
              "is_primary": <bool>,
              "lexicon_start_sec": <number>   // optional: per-wav override
            },
            ...
          ],
          "lexicon_start_sec": <number>,       // speaker-level default
          "has_csv": <bool>,
          "notes": "<string>"                  // optional
        }
      }
    }

SourceIndex schema (output):
    {
      "speakers": {
        "<SpeakerId>": {
          "source_wavs": [
            {
              "filename": "Audio_Original/...",
              "duration_sec": <float>,
              "file_size_bytes": <int>,
              "bit_depth": <int>,
              "sample_rate": <int>,
              "channels": <int>,
              "lexicon_start_sec": <number>,
              "is_primary": <bool>
            },
            ...
          ],
          "peaks_file": "peaks/<SpeakerId>[_<primary_stem>].json",
          "transcript_file": "coarse_transcripts/<SpeakerId>[_<primary_stem>].json",
          "has_csv": <bool>,
          "notes": "<string>"
        }
      }
    }

Notes:
    - For speakers with a single WAV, peaks_file and transcript_file use the
      plain speaker ID: peaks/Fail01.json
    - For speakers with multiple WAVs, the primary WAV's filename stem is
      appended: peaks/Khan01_REC00002.json
    - `lexicon_start_sec` is taken per-wav if present, otherwise falls back
      to the speaker-level field.
    - Input WAV paths must be project-relative URL paths (forward-slash form
      in the output). Absolute filesystem paths are rejected.
"""

import argparse
import json
import math
import os
import re
import sys


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

WAV_REQUIRED_FIELDS = [
    "path",
    "duration_sec",
    "file_size_bytes",
    "bit_depth",
    "sample_rate",
    "channels",
    "is_primary",
]

SPEAKER_REQUIRED_FIELDS = [
    "wav_files",
    "has_csv",
]

WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _fail(msg: str) -> None:
    """Print an error message and exit with status 1."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _ensure_object(value, label: str) -> dict:
    if not isinstance(value, dict):
        _fail(f"{label}: value must be an object")
    return value


def _ensure_bool(value, label: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"{label}: value must be a boolean")
    return value


def _ensure_positive_int(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{label}: value must be a positive integer")
    return value


def _ensure_positive_number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label}: value must be a positive number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        _fail(f"{label}: value must be a finite positive number")
    return value


def _ensure_nonnegative_number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label}: value must be a non-negative number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        _fail(f"{label}: value must be a finite non-negative number")
    return value


def _ensure_optional_string(value, label: str) -> str:
    if not isinstance(value, str):
        _fail(f"{label}: value must be a string")
    return value


def _normalize_relative_url_path(path_value, label: str) -> str:
    if not isinstance(path_value, str) or not path_value.strip():
        _fail(f"{label}: path must be a non-empty string")

    path = path_value.strip().replace("\\", "/")

    if path.startswith("/") or path.startswith("//") or WINDOWS_ABS_RE.match(path):
        _fail(f"{label}: absolute paths are not allowed; expected project-relative path")

    segments = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            _fail(f"{label}: path traversal ('..') is not allowed")
        segments.append(segment)

    if not segments:
        _fail(f"{label}: path must contain at least one non-empty segment")

    return "/".join(segments)


def validate_speaker(speaker_id: str, data: dict) -> None:
    """Validate a single speaker entry from the manifest."""
    prefix = f"Speaker '{speaker_id}'"
    data = _ensure_object(data, prefix)

    for field in SPEAKER_REQUIRED_FIELDS:
        if field not in data:
            _fail(f"{prefix}: missing required field '{field}'")

    wav_files = data["wav_files"]
    if not isinstance(wav_files, list) or len(wav_files) == 0:
        _fail(f"{prefix}: 'wav_files' must be a non-empty list")

    _ensure_bool(data["has_csv"], f"{prefix} field 'has_csv'")

    if "notes" in data:
        _ensure_optional_string(data["notes"], f"{prefix} field 'notes'")

    speaker_lexicon = data.get("lexicon_start_sec")
    if speaker_lexicon is not None:
        _ensure_nonnegative_number(
            speaker_lexicon,
            f"{prefix} field 'lexicon_start_sec'",
        )

    primary_count = 0
    for idx, wav in enumerate(wav_files):
        wav = _ensure_object(wav, f"{prefix} wav[{idx}]")
        wav_prefix = f"{prefix} wav[{idx}]"

        for field in WAV_REQUIRED_FIELDS:
            if field not in wav:
                _fail(f"{wav_prefix}: missing required field '{field}'")

        _normalize_relative_url_path(wav["path"], f"{wav_prefix} field 'path'")
        _ensure_positive_number(wav["duration_sec"], f"{wav_prefix} field 'duration_sec'")
        _ensure_positive_int(wav["file_size_bytes"], f"{wav_prefix} field 'file_size_bytes'")

        bit_depth = _ensure_positive_int(wav["bit_depth"], f"{wav_prefix} field 'bit_depth'")
        if bit_depth != 16:
            _fail(f"{wav_prefix} field 'bit_depth': expected 16-bit PCM, got {bit_depth}")

        _ensure_positive_int(wav["sample_rate"], f"{wav_prefix} field 'sample_rate'")

        channels = _ensure_positive_int(wav["channels"], f"{wav_prefix} field 'channels'")
        if channels not in (1, 2):
            _fail(f"{wav_prefix} field 'channels': expected 1 or 2, got {channels}")

        is_primary = _ensure_bool(wav["is_primary"], f"{wav_prefix} field 'is_primary'")
        if is_primary:
            primary_count += 1

        wav_lexicon = wav.get("lexicon_start_sec", speaker_lexicon)
        if wav_lexicon is None:
            _fail(f"{wav_prefix}: no 'lexicon_start_sec' found at wav or speaker level")
        _ensure_nonnegative_number(wav_lexicon, f"{wav_prefix} field 'lexicon_start_sec'")

    if primary_count == 0:
        _fail(f"{prefix}: no wav entry has 'is_primary: true'")
    if primary_count > 1:
        _fail(
            f"{prefix}: {primary_count} wav entries have 'is_primary: true'; exactly one is required"
        )


# ---------------------------------------------------------------------------
# Transformation helpers
# ---------------------------------------------------------------------------

def _wav_stem(path: str) -> str:
    """Return the filename stem (no directory, no extension) for a WAV path."""
    basename = os.path.basename(path)
    stem, _ = os.path.splitext(basename)
    return stem


def _peaks_and_transcript_paths(speaker_id: str, wav_files: list) -> tuple[str, str]:
    """Return (peaks_file, transcript_file) paths for a speaker."""
    is_multi = len(wav_files) > 1

    if is_multi:
        primary_wav = next(w for w in wav_files if w["is_primary"])
        stem = _wav_stem(primary_wav["path"])
        key = f"{speaker_id}_{stem}"
    else:
        key = speaker_id

    peaks_file = f"peaks/{key}.json"
    transcript_file = f"coarse_transcripts/{key}.json"
    return peaks_file, transcript_file


def transform_speaker(speaker_id: str, data: dict) -> dict:
    """Transform a single speaker manifest entry into SourceIndex format."""
    wav_files = data["wav_files"]
    speaker_lexicon = data.get("lexicon_start_sec")

    source_wavs = []
    for wav in wav_files:
        lexicon_start = wav.get("lexicon_start_sec", speaker_lexicon)

        source_wav = {
            "filename": _normalize_relative_url_path(wav["path"], f"Speaker '{speaker_id}' path"),
            "duration_sec": float(wav["duration_sec"]),
            "file_size_bytes": int(wav["file_size_bytes"]),
            "bit_depth": int(wav["bit_depth"]),
            "sample_rate": int(wav["sample_rate"]),
            "channels": int(wav["channels"]),
            "lexicon_start_sec": float(lexicon_start),
            "is_primary": bool(wav["is_primary"]),
        }
        source_wavs.append(source_wav)

    peaks_file, transcript_file = _peaks_and_transcript_paths(speaker_id, wav_files)

    result = {
        "source_wavs": source_wavs,
        "peaks_file": peaks_file,
        "transcript_file": transcript_file,
        "has_csv": data["has_csv"],
    }

    if "notes" in data:
        result["notes"] = data["notes"]

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_source_index(manifest: dict) -> dict:
    """Validate and transform the full manifest into a SourceIndex dict."""
    if "speakers" not in manifest:
        _fail("Manifest is missing top-level 'speakers' key")

    speakers_in = manifest["speakers"]
    if not isinstance(speakers_in, dict) or len(speakers_in) == 0:
        _fail("'speakers' must be a non-empty object")

    speakers_out = {}
    for speaker_id, speaker_data in speakers_in.items():
        validate_speaker(speaker_id, speaker_data)
        speakers_out[speaker_id] = transform_speaker(speaker_id, speaker_data)

    return {"speakers": speakers_out}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--manifest",
        required=True,
        metavar="FILE",
        help="Path to the input manifest JSON (ffprobe-derived speaker metadata)",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="FILE",
        help="Path for the output source_index.json",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.manifest):
        _fail(f"Manifest file not found: {args.manifest}")

    try:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except json.JSONDecodeError as exc:
        _fail(f"Failed to parse manifest JSON: {exc}")

    source_index = build_source_index(manifest)

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(source_index, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        _fail(f"Failed to write output file '{args.output}': {exc}")

    speaker_count = len(source_index["speakers"])
    wav_count = sum(len(v["source_wavs"]) for v in source_index["speakers"].values())
    print(
        f"OK: wrote {args.output} "
        f"({speaker_count} speaker(s), {wav_count} WAV file(s))"
    )


if __name__ == "__main__":
    main()
