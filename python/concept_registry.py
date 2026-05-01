"""Shared concepts.csv registry helpers for PARSE concept ids."""
from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path


_LABEL_SEPARATOR_RE = re.compile(r"[\W_]+", flags=re.UNICODE)


@dataclass
class ConceptRegistry:
    label_to_id: dict[str, str]
    max_id: int
    raw_rows: list[dict[str, str]]


def concept_label_key(label: str) -> str:
    cleaned = _LABEL_SEPARATOR_RE.sub(" ", str(label or ""))
    return " ".join(cleaned.split()).casefold()


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
    for key, value in row.items():
        if str(key or "").strip().lower() == name:
            return str(value or "").strip()
    return ""


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
            dropped_duplicates: list[tuple[str, str, str]] = []
            for row in reader:
                cid = _normalize_integer_concept_id(_row_value(row, "id"))
                label = _row_value(row, "concept_en")
                key = concept_label_key(label)
                if not cid or not label or not key or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                registry.max_id = max(registry.max_id, int(cid))
                existing_id = registry.label_to_id.get(key)
                if existing_id:
                    if existing_id != cid:
                        dropped_duplicates.append((cid, existing_id, label))
                    continue
                registry.raw_rows.append({"id": cid, "concept_en": label})
                registry.label_to_id[key] = cid
            if dropped_duplicates:
                dropped = ", ".join(
                    f"{dropped_id} -> {kept_id} ({label})" for dropped_id, kept_id, label in dropped_duplicates
                )
                print(
                    f"[concept_registry] duplicate concept label keys in concepts.csv; dropped {dropped}",
                    file=sys.stderr,
                )
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
    registry.raw_rows.append({"id": concept_id, "concept_en": clean_label})
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
        rows.append({"id": cid, "concept_en": label})
    rows.sort(key=lambda item: int(item["id"]))
    path = Path(project_root) / "concepts.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerows(rows)
