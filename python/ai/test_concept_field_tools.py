from __future__ import annotations

import csv
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import ChatToolValidationError, ParseChatTools


FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


def _write_concepts(path: pathlib.Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(
            [
                {"id": "1", "concept_en": "hair", "source_item": "1.1", "source_survey": "", "custom_order": ""},
                {"id": "2", "concept_en": "forehead", "source_item": "1.2", "source_survey": "", "custom_order": ""},
                {"id": "3", "concept_en": "eyelid", "source_item": "1.3", "source_survey": "", "custom_order": ""},
            ]
        )


def _read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_set_concept_field_updates_id_range(tmp_path: pathlib.Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(concepts_path)

    result = ParseChatTools(project_root=tmp_path).execute(
        "set_concept_field",
        {"column": "source_survey", "value": "KLQ", "filter": {"id_range": [1, 2]}},
    )["result"]

    rows = _read_rows(concepts_path)
    assert result["ok"] is True
    assert result["matched"] == 2
    assert result["updated"] == 2
    assert [row["source_survey"] for row in rows] == ["KLQ", "KLQ", ""]


def test_set_concept_field_updates_explicit_ids(tmp_path: pathlib.Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(concepts_path)

    result = ParseChatTools(project_root=tmp_path).execute(
        "set_concept_field",
        {"column": "custom_order", "value": "99", "filter": {"ids": [1, 3]}},
    )["result"]

    rows = _read_rows(concepts_path)
    assert result["matched"] == 2
    assert [row["custom_order"] for row in rows] == ["99", "", "99"]


def test_set_concept_field_updates_all_rows(tmp_path: pathlib.Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(concepts_path)

    result = ParseChatTools(project_root=tmp_path).execute(
        "set_concept_field",
        {"column": "source_survey", "value": "JBIL", "filter": {"all": True}},
    )["result"]

    rows = _read_rows(concepts_path)
    assert result["matched"] == 3
    assert {row["source_survey"] for row in rows} == {"JBIL"}


def test_set_concept_field_rejects_zero_row_filter(tmp_path: pathlib.Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(concepts_path)

    with pytest.raises(ChatToolValidationError, match="selected 0 concept rows"):
        ParseChatTools(project_root=tmp_path).execute(
            "set_concept_field",
            {"column": "source_survey", "value": "KLQ", "filter": {"ids": [99]}},
        )
