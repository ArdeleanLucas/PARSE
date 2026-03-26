#!/usr/bin/env python3
"""Attach ortho strings from transcription CSVs to coarse transcript JSON files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy the existing ortho column from transcription CSVs into matching "
            "coarse transcript JSON segment records."
        )
    )
    parser.add_argument(
        "--thesis-dir",
        type=Path,
        default=Path("/mnt/c/Users/Lucas/Thesis"),
        help="Root thesis directory containing coarse_transcripts/ and Audio_Processed/",
    )
    parser.add_argument(
        "--speaker",
        action="append",
        default=[],
        help=(
            "Optional transcript speaker stem to process. Repeat to process multiple. "
            "Defaults to all matched speakers."
        ),
    )
    return parser.parse_args()


def sorted_json_paths(coarse_dir: Path) -> List[Path]:
    return sorted(coarse_dir.glob("*.json"))


def sorted_csv_paths(processed_dir: Path) -> List[Path]:
    return sorted(processed_dir.glob("*_process/*_transcriptions.csv"))


def csv_speaker_name(csv_path: Path) -> str:
    filename_stem = csv_path.stem.removesuffix("_transcriptions")
    parent_stem = csv_path.parent.name.removesuffix("_process")
    if filename_stem != parent_stem:
        raise ValueError(
            f"CSV naming mismatch for {csv_path}: filename speaker={filename_stem!r}, "
            f"parent speaker={parent_stem!r}"
        )
    return filename_stem


def build_csv_index(csv_paths: Sequence[Path]) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    for csv_path in csv_paths:
        speaker = csv_speaker_name(csv_path)
        if speaker in index:
            raise ValueError(
                f"Duplicate transcription CSV for speaker {speaker!r}: {index[speaker]} and {csv_path}"
            )
        index[speaker] = csv_path
    return index


def transcript_match_candidates(transcript_speaker: str) -> Iterable[str]:
    yield transcript_speaker
    if "_" in transcript_speaker:
        prefix = transcript_speaker.split("_", 1)[0]
        if prefix != transcript_speaker:
            yield prefix


def match_transcript_to_csv(transcript_path: Path, csv_index: Dict[str, Path]) -> Tuple[str, Path] | None:
    transcript_speaker = transcript_path.stem
    for candidate in transcript_match_candidates(transcript_speaker):
        csv_path = csv_index.get(candidate)
        if csv_path is not None:
            return candidate, csv_path
    return None


def load_transcript(transcript_path: Path) -> Tuple[dict, List[dict]]:
    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise ValueError(f"Transcript {transcript_path} is missing a list-valued 'segments' field")
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(
                f"Transcript {transcript_path} has a non-object segment at index {index}: {segment!r}"
            )
    return data, segments


def load_ortho_rows(csv_path: Path) -> List[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "ortho" not in fieldnames:
            raise ValueError(f"CSV {csv_path} is missing required 'ortho' column; fields={fieldnames}")
        return [row.get("ortho", "") for row in reader]


def write_transcript(transcript_path: Path, data: dict) -> None:
    transcript_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def preview_lines(segments: Sequence[dict], limit: int = 5) -> List[str]:
    lines: List[str] = []
    for segment in list(segments[:limit]):
        ipa = str(segment.get("text", ""))
        ortho = str(segment.get("ortho", ""))
        lines.append(f"  IPA={ipa} | ortho={ortho}")
    return lines


def main() -> int:
    args = parse_args()
    thesis_dir = args.thesis_dir
    coarse_dir = thesis_dir / "coarse_transcripts"
    processed_dir = thesis_dir / "Audio_Processed"

    transcript_paths = sorted_json_paths(coarse_dir)
    csv_paths = sorted_csv_paths(processed_dir)
    csv_index = build_csv_index(csv_paths)

    print(f"Found {len(transcript_paths)} coarse transcripts in {coarse_dir}")
    for transcript_path in transcript_paths:
        print(f"  - {transcript_path.stem}")

    print(f"\nFound {len(csv_paths)} transcription CSVs in {processed_dir}")
    for csv_path in csv_paths:
        print(f"  - {csv_speaker_name(csv_path)}")

    requested = set(args.speaker)
    matched: List[Tuple[Path, str, Path]] = []
    unmatched_transcripts: List[str] = []

    for transcript_path in transcript_paths:
        transcript_speaker = transcript_path.stem
        if requested and transcript_speaker not in requested:
            continue
        match = match_transcript_to_csv(transcript_path, csv_index)
        if match is None:
            unmatched_transcripts.append(transcript_speaker)
            continue
        csv_speaker, csv_path = match
        matched.append((transcript_path, csv_speaker, csv_path))

    if requested:
        found_transcripts = {transcript_path.stem for transcript_path, _, _ in matched} | set(unmatched_transcripts)
        missing_requests = sorted(requested - found_transcripts)
        if missing_requests:
            raise SystemExit(f"Requested transcript(s) not found: {', '.join(missing_requests)}")

    print(f"\nMatched {len(matched)} transcript(s) with transcription CSVs")
    for transcript_path, csv_speaker, _ in matched:
        transcript_speaker = transcript_path.stem
        alias_note = "" if transcript_speaker == csv_speaker else f" (via CSV speaker {csv_speaker})"
        print(f"  - {transcript_speaker}{alias_note}")

    if unmatched_transcripts:
        print("\nSkipping transcripts without transcription CSVs:")
        for speaker in unmatched_transcripts:
            print(f"  - {speaker}")

    used_csv_speakers = {csv_speaker for _, csv_speaker, _ in matched}
    unmatched_csv_speakers = sorted(set(csv_index) - used_csv_speakers)
    if unmatched_csv_speakers:
        print("\nCSV speakers without a matching coarse transcript:")
        for speaker in unmatched_csv_speakers:
            print(f"  - {speaker}")

    if not matched:
        print("\nNo speakers matched. Nothing to update.")
        return 0

    errors: List[str] = []

    for transcript_path, csv_speaker, csv_path in matched:
        transcript_speaker = transcript_path.stem
        print(f"\n=== {transcript_speaker} ===")
        try:
            data, segments = load_transcript(transcript_path)
            ortho_rows = load_ortho_rows(csv_path)

            if len(segments) != len(ortho_rows):
                raise ValueError(
                    f"Row count mismatch: transcript has {len(segments)} segments, "
                    f"CSV has {len(ortho_rows)} rows"
                )

            for segment, ortho in zip(segments, ortho_rows):
                segment["ortho"] = ortho

            write_transcript(transcript_path, data)
            alias_note = "" if transcript_speaker == csv_speaker else f" (CSV speaker {csv_speaker})"
            print(f"Updated {transcript_path}{alias_note}")
            print(f"Verified {len(segments)} aligned rows")
            print("First 5 segments:")
            for line in preview_lines(segments, limit=5):
                print(line)
        except Exception as exc:  # pragma: no cover - CLI error aggregation
            errors.append(f"{transcript_speaker}: {exc}")
            print(f"ERROR: {exc}")

    if errors:
        print("\nCompleted with errors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"\nDone. Updated {len(matched)} coarse transcript file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
