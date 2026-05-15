#!/usr/bin/env python3
"""Generate a read-only duplicate concept-row audit manifest."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DEFAULT_CONCEPTS_CSV = Path("/tmp/parse-audit-snapshot-MC396A/concepts.csv")
DEFAULT_ANNOTATIONS_DIR = Path("/tmp/parse-audit-snapshot-MC396A/annotations")


def _read_concepts(concepts_csv: Path) -> list[dict[str, str]]:
    with concepts_csv.open(newline="", encoding="utf-8-sig") as handle:
        rows: list[dict[str, str]] = []
        for raw in csv.DictReader(handle):
            row = {str(k or "").strip(): str(v or "").strip() for k, v in raw.items()}
            rows.append(
                {
                    "id": row.get("id", ""),
                    "concept_en": row.get("concept_en") or row.get("label", ""),
                    "source_item": row.get("source_item") or row.get("survey_item", ""),
                    "source_survey": row.get("source_survey", ""),
                    "custom_order": row.get("custom_order", ""),
                }
            )
        return rows


def _speaker_name(path: Path, payload: Any) -> str:
    if isinstance(payload, dict) and str(payload.get("speaker") or "").strip():
        return str(payload.get("speaker") or "").strip()
    return path.name.removesuffix(".parse.json").removesuffix(".json")


def _read_tag_refs(annotations_dir: Path) -> dict[str, list[tuple[str, list[str]]]]:
    refs: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    if not annotations_dir.is_dir():
        return refs
    for path in sorted(annotations_dir.glob("*.parse.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        speaker = _speaker_name(path, payload)
        concept_tags = payload.get("concept_tags") if isinstance(payload, dict) else None
        if not isinstance(concept_tags, dict):
            continue
        for concept_id, raw_tags in concept_tags.items():
            if not isinstance(raw_tags, list):
                continue
            tags = [str(tag) for tag in raw_tags if isinstance(tag, str)]
            if tags:
                refs[str(concept_id)].append((speaker, tags))
    return refs


def _format_bucket_rows(rows: list[dict[str, str]]) -> str:
    return ", ".join(f"`{row['id']}|{row['concept_en']}`" for row in rows)


def _format_refs(rows: list[dict[str, str]], refs: dict[str, list[tuple[str, list[str]]]]) -> str:
    chunks: list[str] = []
    for row in rows:
        cid = row["id"]
        row_refs = refs.get(cid, [])
        if not row_refs:
            chunks.append(f"{cid}: —")
            continue
        speaker_chunks = [f"{speaker} [{', '.join(f'`{tag}`' for tag in tags)}]" for speaker, tags in row_refs]
        chunks.append(f"{cid}: " + "; ".join(speaker_chunks))
    return "<br>".join(chunks)


def build_manifest(*, concepts_csv: Path = DEFAULT_CONCEPTS_CSV, annotations_dir: Path = DEFAULT_ANNOTATIONS_DIR) -> str:
    rows = _read_concepts(concepts_csv)
    refs = _read_tag_refs(annotations_dir)
    buckets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row.get("source_item", "").strip(), row.get("source_survey", "").strip())
        if key[0] and key[1]:
            buckets[key].append(row)
    duplicate_buckets = {key: bucket for key, bucket in buckets.items() if len(bucket) > 1}
    all_ids = {row["id"] for row in rows if row.get("id")}
    orphan_ids = sorted(cid for cid in all_ids if not refs.get(cid))
    survey_counts = Counter(key[1] for key in duplicate_buckets)

    lines = [
        "# Duplicate concept-row audit — 2026-05-15",
        "",
        "This is a read-only point-in-time audit. Cleanup is a follow-up MC task. Do not modify concepts.csv or annotation JSONs based on this audit without Lucas's per-row approval.",
        "",
        "## Summary",
        "",
        f"- Duplicate buckets: {len(duplicate_buckets)}",
        f"- Orphan ids: {len(orphan_ids)}",
        "- Per-survey breakdown:",
    ]
    if survey_counts:
        for survey, count in sorted(survey_counts.items()):
            lines.append(f"  - {survey}: {count}")
    else:
        lines.append("  - none: 0")
    if orphan_ids:
        lines.append("- Orphan id list: " + ", ".join(orphan_ids))
    lines.extend([
        "",
        "## Duplicate buckets",
        "",
        "| source_item | source_survey | ids / labels | speaker tag references | proposed action |",
        "|---|---|---|---|---|",
    ])
    for (source_item, source_survey), bucket in sorted(duplicate_buckets.items(), key=lambda item: (item[0][1], item[0][0])):
        bucket_sorted = sorted(bucket, key=lambda row: int(row["id"]) if row["id"].isdigit() else row["id"])
        lines.append(
            f"| {source_item} | {source_survey} | {_format_bucket_rows(bucket_sorted)} | {_format_refs(bucket_sorted, refs)} |  |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("concepts_csv", nargs="?", type=Path, default=DEFAULT_CONCEPTS_CSV)
    parser.add_argument("annotations_dir", nargs="?", type=Path, default=DEFAULT_ANNOTATIONS_DIR)
    args = parser.parse_args()
    print(build_manifest(concepts_csv=args.concepts_csv, annotations_dir=args.annotations_dir))


if __name__ == "__main__":
    main()
