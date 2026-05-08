#!/usr/bin/env python3
"""Audit the live PARSE thesis concept tag after the May 2026 CSV re-import.

This script is intentionally read-only. It compares the `custom-sk-concept-list`
concept tag in live speaker annotation files against Lucas's 82-row thesis CSV,
folding PARSE concept labels to their base label before parenthesized variants.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

WORKSPACE_ROOT = Path("/home/lucas/parse-workspace")
THESIS_CSV_PATH = Path("/mnt/c/Users/Lucas/Thesis/concepts.csv")
OUTPUT_PATH = Path("docs/reports/2026-05-09-thesis-tag-reimport-outcome.tsv")
TAG_ID = "custom-sk-concept-list"

EXCLUDED_ANNOTATION_NAMES = {"manifest.json", "parse-enrichments.json"}


def base_label(label: str) -> str:
    """Return the folded base label used for thesis-list comparison."""
    return str(label or "").split(" (")[0].strip().lower()


def speaker_name_for_annotation(path: Path) -> str:
    if path.name.endswith(".parse.json"):
        return path.name[: -len(".parse.json")]
    if path.name.endswith(".json"):
        return path.name[: -len(".json")]
    return path.stem


def read_thesis_labels(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        labels: list[str] = []
        for row in reader:
            raw = row.get("concept_en") or row.get("label") or row.get("concept") or ""
            folded = base_label(raw)
            if folded:
                labels.append(folded)
    return labels


def read_concept_labels(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        label_field = "concept_en" if "concept_en" in fieldnames else "label" if "label" in fieldnames else "concept"
        return {
            str(row.get("id") or "").strip(): str(row.get(label_field) or "").strip()
            for row in reader
            if str(row.get("id") or "").strip()
        }


def iter_annotation_files(annotations_dir: Path) -> Iterable[Path]:
    candidates: list[Path] = []
    for path in sorted(annotations_dir.glob("*.json")):
        if path.name in EXCLUDED_ANNOTATION_NAMES:
            continue
        if path.name.endswith(".tmp") or ".bak" in path.name:
            continue
        candidates.append(path)
    parse_speakers = {
        path.name[: -len(".parse.json")]
        for path in candidates
        if path.name.endswith(".parse.json")
    }
    for path in candidates:
        if path.name.endswith(".parse.json"):
            yield path
            continue
        speaker = path.name[: -len(".json")] if path.name.endswith(".json") else path.stem
        if speaker in parse_speakers:
            continue
        yield path


def tagged_concept_ids(annotation_path: Path) -> list[str]:
    try:
        payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    concept_tags = payload.get("concept_tags")
    if not isinstance(concept_tags, dict):
        return []
    tagged: list[str] = []
    for concept_id, tag_ids in concept_tags.items():
        if not isinstance(tag_ids, list):
            continue
        if TAG_ID in {str(tag_id) for tag_id in tag_ids}:
            tagged.append(str(concept_id))
    return sorted(tagged, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))


def main() -> int:
    thesis_labels = read_thesis_labels(THESIS_CSV_PATH)
    thesis_set = set(thesis_labels)
    concept_labels = read_concept_labels(WORKSPACE_ROOT / "concepts.csv")
    rows: list[dict[str, str | int]] = []

    for annotation_path in iter_annotation_files(WORKSPACE_ROOT / "annotations"):
        concept_ids = tagged_concept_ids(annotation_path)
        tagged_bases = {
            folded
            for folded in (base_label(concept_labels.get(concept_id, "")) for concept_id in concept_ids)
            if folded
        }
        missing = sorted(thesis_set - tagged_bases)
        extra = sorted(tagged_bases - thesis_set)
        rows.append(
            {
                "speaker": speaker_name_for_annotation(annotation_path),
                "thesis_csv_count": len(thesis_labels),
                "tagged_id_count": len(concept_ids),
                "tagged_base_count": len(tagged_bases),
                "missing_thesis_labels": ";".join(missing),
                "extra_tagged_labels": ";".join(extra),
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "speaker",
            "thesis_csv_count",
            "tagged_id_count",
            "tagged_base_count",
            "missing_thesis_labels",
            "extra_tagged_labels",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    missing_speakers = [str(row["speaker"]) for row in rows if row["missing_thesis_labels"]]
    print(f"wrote {OUTPUT_PATH}")
    print(f"speakers={len(rows)} thesis_csv_count={len(thesis_labels)} missing_speakers={len(missing_speakers)}")
    if missing_speakers:
        print("missing_speakers=" + ",".join(missing_speakers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
