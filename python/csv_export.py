#!/usr/bin/env python3
"""
csv_export.py — Export PARSE annotations to flat CSV.

CSV schema:
    speaker,concept_id,concept_en,start_sec,end_sec,duration_sec,ipa,ortho,source_file

Usage:
    # Single speaker
    python csv_export.py --input annotations/Fail01.parse.json --output exports/Fail01.csv

    # All speakers
    python csv_export.py --input-dir annotations/ --output exports/all_annotations.csv --all

    # To stdout (for piping)
    python csv_export.py --input annotations/Fail01.parse.json --stdout
"""

import argparse
import csv
import json
import sys
from pathlib import Path


CSV_COLUMNS = [
    "speaker",
    "concept_id",
    "concept_en",
    "start_sec",
    "end_sec",
    "duration_sec",
    "ipa",
    "ortho",
    "source_file",
]


class _StringBuffer:
    """Minimal writeable text buffer for csv module output."""

    def __init__(self) -> None:
        self._parts = []

    def write(self, chunk: str) -> int:
        self._parts.append(chunk)
        return len(chunk)

    def getvalue(self) -> str:
        return "".join(self._parts)


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get_tier(annotation_data: dict, tier_name: str) -> dict:
    tiers = annotation_data.get("tiers")
    if not isinstance(tiers, dict):
        return {}

    if tier_name in tiers and isinstance(tiers[tier_name], dict):
        return tiers[tier_name]

    target = tier_name.lower()
    for name, tier_data in tiers.items():
        if isinstance(name, str) and name.lower() == target and isinstance(tier_data, dict):
            return tier_data
    return {}


def _get_intervals(annotation_data: dict, tier_name: str) -> list:
    tier = _get_tier(annotation_data, tier_name)
    intervals = tier.get("intervals")
    if not isinstance(intervals, list):
        return []
    return [interval for interval in intervals if isinstance(interval, dict)]


def _is_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and a_end > b_start


def _overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    if not _is_overlap(a_start, a_end, b_start, b_end):
        return 0.0
    return min(a_end, b_end) - max(a_start, b_start)


def _best_overlap(interval: dict, candidates: list) -> dict:
    start = _safe_float(interval.get("start"))
    end = _safe_float(interval.get("end"))

    best = None
    best_overlap = -1.0

    for candidate in candidates:
        c_start = _safe_float(candidate.get("start"))
        c_end = _safe_float(candidate.get("end"))
        overlap = _overlap_seconds(start, end, c_start, c_end)
        if overlap > best_overlap:
            best_overlap = overlap
            best = candidate

    if best_overlap <= 0.0:
        return {}
    return best if isinstance(best, dict) else {}


def _split_concept(concept_text: str) -> tuple:
    text = _safe_text(concept_text).strip()
    if not text:
        return "", ""

    if ":" not in text:
        return "", text

    left, right = text.split(":", 1)
    return left.strip(), right.strip()


def _source_file(annotation_data: dict) -> str:
    source_path = _safe_text(annotation_data.get("source_audio")).strip()

    if not source_path:
        metadata = annotation_data.get("metadata")
        if isinstance(metadata, dict):
            source_path = _safe_text(metadata.get("source_audio") or metadata.get("source_file")).strip()

    if not source_path:
        source_path = _safe_text(annotation_data.get("source_file")).strip()

    if not source_path:
        return ""
    return Path(source_path).name


def _speaker_from_data(annotation_data: dict, annotation_path: Path = None) -> str:
    speaker = _safe_text(annotation_data.get("speaker")).strip()
    if speaker:
        return speaker

    if annotation_path is None:
        return ""

    name = annotation_path.name
    suffix = ".parse.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return annotation_path.stem


def _build_rows(annotation_data: dict, speaker: str) -> list:
    rows = []
    source_file = _source_file(annotation_data)

    ipa_intervals = _get_intervals(annotation_data, "ipa")
    ortho_intervals = _get_intervals(annotation_data, "ortho")
    concept_intervals = _get_intervals(annotation_data, "concept")

    for ipa_interval in ipa_intervals:
        ipa_text = _safe_text(ipa_interval.get("text")).strip()
        if not ipa_text:
            continue

        start_sec = _safe_float(ipa_interval.get("start"))
        end_sec = _safe_float(ipa_interval.get("end"))
        duration_sec = end_sec - start_sec

        ortho_match = _best_overlap(ipa_interval, ortho_intervals)
        concept_match = _best_overlap(ipa_interval, concept_intervals)

        ortho_text = _safe_text(ortho_match.get("text")).strip() if ortho_match else ""
        concept_text = _safe_text(concept_match.get("text")).strip() if concept_match else ""
        concept_id, concept_en = _split_concept(concept_text)

        rows.append(
            {
                "speaker": speaker,
                "concept_id": concept_id,
                "concept_en": concept_en,
                "start_sec": f"{start_sec:.6f}",
                "end_sec": f"{end_sec:.6f}",
                "duration_sec": f"{duration_sec:.6f}",
                "ipa": ipa_text,
                "ortho": ortho_text,
                "source_file": source_file,
                "_start_sort": start_sec,
                "_end_sort": end_sec,
            }
        )

    return rows


def _sort_rows_single(rows: list) -> None:
    rows.sort(key=lambda row: (row["_start_sort"], row["_end_sort"]))


def _sort_rows_all(rows: list) -> None:
    rows.sort(key=lambda row: (row["speaker"], row["_start_sort"], row["_end_sort"]))


def _rows_to_csv_string(rows: list) -> str:
    buffer = _StringBuffer()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    for row in rows:
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})

    return buffer.getvalue()


def _write_rows_to_csv(rows: list, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})


def _read_annotation_file(annotation_path: Path) -> dict:
    if not annotation_path.exists():
        raise FileNotFoundError(f"Annotation file not found: {annotation_path}")
    if not annotation_path.is_file():
        raise ValueError(f"Annotation path is not a file: {annotation_path}")

    with annotation_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(f"Annotation JSON must be an object: {annotation_path}")
    return data


def _collect_all_rows(annotation_dir: Path) -> list:
    if not annotation_dir.exists():
        raise FileNotFoundError(f"Annotation directory not found: {annotation_dir}")
    if not annotation_dir.is_dir():
        raise ValueError(f"Annotation path is not a directory: {annotation_dir}")

    all_rows = []
    annotation_paths = sorted(annotation_dir.glob("*.parse.json"))

    for annotation_path in annotation_paths:
        annotation_data = _read_annotation_file(annotation_path)
        speaker = _speaker_from_data(annotation_data, annotation_path)
        all_rows.extend(_build_rows(annotation_data, speaker))

    return all_rows


def export_csv(annotation_data: dict, output_path: Path, speaker: str) -> None:
    """
    Export single speaker annotations to CSV.
    """
    rows = _build_rows(annotation_data, speaker)
    _sort_rows_single(rows)
    _write_rows_to_csv(rows, output_path)


def export_all_csv(annotation_dir: Path, output_path: Path) -> None:
    """
    Export all speakers from annotation_dir to a single merged CSV.
    Sorted by speaker, then start_sec.
    """
    rows = _collect_all_rows(annotation_dir)
    _sort_rows_all(rows)
    _write_rows_to_csv(rows, output_path)


def annotations_to_csv_str(annotation_data: dict, speaker: str) -> str:
    """
    Serialize to CSV string without writing to disk.
    Used by annotation-store.js export via server endpoint.
    """
    rows = _build_rows(annotation_data, speaker)
    _sort_rows_single(rows)
    return _rows_to_csv_string(rows)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export PARSE annotations to flat CSV format.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to a single annotation file (e.g. annotations/Fail01.parse.json).",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Directory containing *.parse.json annotation files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output CSV file path.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export all speakers from --input-dir.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write CSV to stdout instead of (or in addition to) --output.",
    )
    return parser


def _run_cli(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.all:
        if args.input is not None:
            parser.error("--all cannot be combined with --input.")
        if args.input_dir is None:
            parser.error("--all requires --input-dir.")
        if args.output is None and not args.stdout:
            parser.error("For --all export, provide --output or --stdout.")

        rows = _collect_all_rows(args.input_dir)
        _sort_rows_all(rows)

        if args.output is not None:
            _write_rows_to_csv(rows, args.output)
        if args.stdout:
            sys.stdout.write(_rows_to_csv_string(rows))
        return 0

    if args.input is None:
        parser.error("Single-speaker export requires --input.")
    if args.input_dir is not None:
        parser.error("--input-dir can only be used with --all.")
    if args.output is None and not args.stdout:
        parser.error("Single-speaker export requires --output or --stdout.")

    annotation_data = _read_annotation_file(args.input)
    speaker = _speaker_from_data(annotation_data, args.input)

    if args.output is not None:
        export_csv(annotation_data, args.output, speaker)
    if args.stdout:
        sys.stdout.write(annotations_to_csv_str(annotation_data, speaker))
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        return _run_cli(args, parser)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Failed to parse JSON: {exc}", file=sys.stderr)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
