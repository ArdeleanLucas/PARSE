"""Unit tests for shared concepts.csv registry allocation."""
from __future__ import annotations

import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from concept_registry import (  # noqa: E402
    load_concept_registry,
    persist_concept_registry,
    resolve_or_allocate_concept_id,
)


def _write_concepts_csv(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerows(rows)


def _read_concepts_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_registry_load_reuses_casefold_whitespace_normalized_labels(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "2", "concept_en": "Forehead"},
            {"id": "225", "concept_en": "to   listen\tto"},
            {"id": "1.5", "concept_en": "decimal ids are not registry ids"},
            {"id": "bad", "concept_en": "bad ids are ignored"},
            {"id": "226", "concept_en": ""},
        ],
    )

    registry = load_concept_registry(tmp_path)
    concept_id, was_allocated = resolve_or_allocate_concept_id(registry, "  TO listen   TO  ")

    assert registry.label_to_id == {"forehead": "2", "to listen to": "225"}
    assert registry.max_id == 225
    assert concept_id == "225"
    assert was_allocated is False


def test_registry_allocates_next_integer_id_and_persists_integer_only_csv(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "2", "concept_en": "forehead"},
            {"id": "225", "concept_en": "nine"},
        ],
    )
    registry = load_concept_registry(tmp_path)

    concept_id, was_allocated = resolve_or_allocate_concept_id(registry, "to listen to")
    persist_concept_registry(tmp_path, registry)

    assert concept_id == "226"
    assert was_allocated is True
    assert _read_concepts_csv(tmp_path / "concepts.csv") == [
        {"id": "2", "concept_en": "forehead"},
        {"id": "225", "concept_en": "nine"},
        {"id": "226", "concept_en": "to listen to"},
    ]


def test_registry_persist_keeps_existing_row_for_duplicate_id(tmp_path: pathlib.Path) -> None:
    registry = load_concept_registry(tmp_path)
    registry.raw_rows.extend(
        [
            {"id": "1", "concept_en": "existing"},
            {"id": "1", "concept_en": "duplicate must not win"},
            {"id": "2.5", "concept_en": "decimal must not persist"},
        ]
    )

    persist_concept_registry(tmp_path, registry)

    assert _read_concepts_csv(tmp_path / "concepts.csv") == [
        {"id": "1", "concept_en": "existing"},
    ]
