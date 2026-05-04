"""Shared concepts.csv registry helpers for PARSE concept ids."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from concept_source_item import concept_row_from_item, read_concepts_csv_rows, row_value, write_concepts_csv_rows


@dataclass
class ConceptRegistry:
    label_to_id: dict[str, str]
    max_id: int
    raw_rows: list[dict[str, str]]


def concept_label_key(label: str) -> str:
    return " ".join(str(label or "").strip().split()).casefold()


def _normalize_integer_concept_id(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("#"):
        text = text[1:].strip()
    if ":" in text:
        text = text.split(":", 1)[0].strip()
    if not text:
        return ""
    try:
        int_id = int(text)
    except (TypeError, ValueError):
        return ""
    return text if str(int_id) == text else ""


def _row_value(row: dict[str, object], name: str) -> str:
    return row_value(row, name)


def load_concept_registry(project_root: Path) -> ConceptRegistry:
    registry = ConceptRegistry(label_to_id={}, max_id=0, raw_rows=[])
    path = Path(project_root) / "concepts.csv"
    if not path.exists():
        return registry
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fields = {str(name or "").strip().lower() for name in reader.fieldnames or []}
            if not {"id", "concept_en"}.issubset(fields):
                return registry
            seen_ids: set[str] = set()
            for row in reader:
                cid = _normalize_integer_concept_id(_row_value(row, "id"))
                label = _row_value(row, "concept_en")
                if not cid or not label or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                registry.max_id = max(registry.max_id, int(cid))
                normalized = concept_row_from_item(row)
                normalized["id"] = cid
                normalized["concept_en"] = label
                registry.raw_rows.append(normalized)
                registry.label_to_id.setdefault(concept_label_key(label), cid)
    except (OSError, csv.Error, UnicodeDecodeError):
        return ConceptRegistry(label_to_id={}, max_id=0, raw_rows=[])
    return registry


def resolve_or_allocate_concept_id(registry: ConceptRegistry, label: str) -> tuple[str, bool]:
    clean_label = str(label or "").strip()
    key = concept_label_key(clean_label)
    if not key:
        return "", False
    existing = registry.label_to_id.get(key)
    if existing:
        return existing, False
    registry.max_id += 1
    concept_id = str(registry.max_id)
    registry.label_to_id[key] = concept_id
    registry.raw_rows.append({"id": concept_id, "concept_en": clean_label, "source_item": "", "source_survey": "", "custom_order": ""})
    return concept_id, True


def persist_concept_registry(project_root: Path, registry: ConceptRegistry) -> None:
    seen_ids: set[str] = set()
    rows: list[dict[str, str]] = []
    for row in registry.raw_rows:
        cid = _normalize_integer_concept_id(_row_value(row, "id"))
        label = _row_value(row, "concept_en")
        if not cid or not label or cid in seen_ids:
            continue
        seen_ids.add(cid)
        normalized = concept_row_from_item(row)
        normalized["id"] = cid
        normalized["concept_en"] = label
        rows.append(normalized)
    rows.sort(key=lambda item: int(item["id"]))
    path = Path(project_root) / "concepts.csv"
    write_concepts_csv_rows(path, rows)


def merge_concepts_into_root_csv(
    project_root: Path,
    new_concepts: Sequence[Mapping[str, object]],
    *,
    normalize_concept_id: Callable[[object], str],
    concept_sort_key: Callable[[str], Any] | None = None,
) -> int:
    """Merge concepts into root concepts.csv while preserving the 5-column schema.

    Existing labels remain canonical. Optional traceability columns are filled only
    when an existing row is empty and the incoming concept supplies a non-empty
    value. Rows present only in the existing file are retained; incoming-only rows
    are added.
    """

    concepts_path = Path(project_root) / "concepts.csv"
    merged: dict[str, dict[str, str]] = {}
    try:
        for row in read_concepts_csv_rows(concepts_path):
            cid = normalize_concept_id(row.get("id"))
            label = row_value(row, "concept_en")
            if cid and label:
                normalized = concept_row_from_item(row)
                normalized["id"] = cid
                normalized["concept_en"] = label
                merged[cid] = normalized
    except (OSError, csv.Error, UnicodeDecodeError):
        pass

    for item in new_concepts:
        incoming = concept_row_from_item(item)
        cid = normalize_concept_id(incoming.get("id"))
        label = row_value(incoming, "concept_en")
        if not (cid and label):
            continue
        incoming["id"] = cid
        incoming["concept_en"] = label
        if cid not in merged:
            merged[cid] = incoming
            continue
        existing = merged[cid]
        for key in ("source_item", "source_survey", "custom_order"):
            if not existing.get(key) and incoming.get(key):
                existing[key] = incoming[key]

    def _sort_key(item: tuple[str, dict[str, str]]) -> Any:
        concept_id, _row = item
        if concept_sort_key is None:
            return concept_id
        return concept_sort_key(concept_id)

    ordered = [row for _cid, row in sorted(merged.items(), key=_sort_key)]
    write_concepts_csv_rows(concepts_path, ordered)
    return len(ordered)
