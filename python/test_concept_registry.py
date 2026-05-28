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
    fieldnames = ["id", "concept_en"]
    if any(any(key in row for key in ("source_item", "source_survey", "custom_order")) for row in rows):
        fieldnames = ["id", "concept_en", "source_item", "source_survey", "custom_order"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
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
        {"id": "2", "concept_en": "forehead", "source_item": "", "source_survey": "", "custom_order": ""},
        {"id": "225", "concept_en": "nine", "source_item": "", "source_survey": "", "custom_order": ""},
        {"id": "226", "concept_en": "to listen to", "source_item": "", "source_survey": "", "custom_order": ""},
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
        {"id": "1", "concept_en": "existing", "source_item": "", "source_survey": "", "custom_order": ""},
    ]


def test_resolver_matches_canonical_triple_instead_of_minting_duplicate(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "53", "concept_en": "big (A)", "source_survey": "KLQ", "source_item": "4.1"},
        ],
    )
    registry = load_concept_registry(tmp_path)

    concept_id, was_allocated = resolve_or_allocate_concept_id(
        registry,
        "big",
        source_survey="KLQ",
        source_item="4.1",
    )

    assert concept_id == "53"
    assert was_allocated is False
    assert registry.label_to_ids["big"] == ["53"]
    assert registry.triple_to_id[("KLQ", "4.1", "big")] == "53"


def test_resolver_canonicalizes_cue_prefix_for_slot_match(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "53", "concept_en": "big", "source_survey": "KLQ", "source_item": "4.1"},
        ],
    )
    registry = load_concept_registry(tmp_path)

    concept_id, was_allocated = resolve_or_allocate_concept_id(
        registry,
        "4.1- big",
        source_survey="KLQ",
        source_item="4.1",
    )

    assert concept_id == "53"
    assert was_allocated is False


def test_resolver_preserves_parenthetical_clarifier_while_canonicalizing_variants(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "10", "concept_en": "hair (women)", "source_survey": "JBIL", "source_item": "32"},
        ],
    )
    registry = load_concept_registry(tmp_path)

    concept_id, was_allocated = resolve_or_allocate_concept_id(
        registry,
        "hair (women)",
        source_survey="JBIL",
        source_item="32",
    )

    assert concept_id == "10"
    assert was_allocated is False


def test_resolver_fail01_regression_prefers_existing_slot_variant(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "53", "concept_en": "big (A)", "source_survey": "KLQ", "source_item": "4.1"},
            {"id": "619", "concept_en": "big (B)", "source_survey": "KLQ", "source_item": "4.1"},
        ],
    )
    registry = load_concept_registry(tmp_path)

    concept_id, was_allocated = resolve_or_allocate_concept_id(
        registry,
        "big",
        source_survey="KLQ",
        source_item="4.1",
    )

    assert concept_id == "53"
    assert was_allocated is False
    assert registry.max_id == 619
    assert len(registry.raw_rows) == 2


def test_resolver_legacy_label_only_fallback_still_uses_first_label_match(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "53", "concept_en": "big (A)", "source_survey": "KLQ", "source_item": "4.1"},
            {"id": "619", "concept_en": "big (B)", "source_survey": "KLQ", "source_item": "4.1"},
        ],
    )
    registry = load_concept_registry(tmp_path)

    concept_id, was_allocated = resolve_or_allocate_concept_id(registry, "big")

    assert concept_id == "53"
    assert was_allocated is False


def test_resolver_allocates_new_slot_row_when_triple_has_no_match(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "53", "concept_en": "big (A)", "source_survey": "KLQ", "source_item": "4.1"},
        ],
    )
    registry = load_concept_registry(tmp_path)

    concept_id, was_allocated = resolve_or_allocate_concept_id(
        registry,
        "big (B)",
        source_survey="KLQ",
        source_item="4.2",
    )

    assert concept_id == "54"
    assert was_allocated is True
    assert registry.raw_rows[-1] == {
        "id": "54",
        "concept_en": "big",
        "source_item": "4.2",
        "source_survey": "KLQ",
        "custom_order": "",
    }
