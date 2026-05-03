from __future__ import annotations

import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.backfill_source_item import backfill_source_items, format_summary


FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


def _read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_backfill_source_items_dry_run_and_apply_are_idempotent(tmp_path: pathlib.Path) -> None:
    workspace = tmp_path / "workspace"
    staging = workspace / "imports" / "staging" / "Saha01"
    staging.mkdir(parents=True)
    fixture = pathlib.Path(__file__).resolve().parent / "test_fixtures" / "saha01_source_item_cues.csv"
    (staging / "Sahana_F_1978_01 - Kaso Solav.csv").write_bytes(fixture.read_bytes())

    concepts_path = workspace / "concepts.csv"
    with concepts_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerows(
            [
                {"id": "1", "concept_en": "forehead"},
                {"id": "2", "concept_en": "maternal uncle"},
                {"id": "3", "concept_en": "the baby is in the uterus"},
                {"id": "4", "concept_en": "paternal uncle’s son"},
                {"id": "5", "concept_en": "unmatched workspace concept"},
            ]
        )

    dry_summary = backfill_source_items(workspace, dry_run=True)
    assert format_summary(dry_summary) == "matched=4 added=4 skipped=0"
    assert _read_rows(concepts_path)[0].get("source_item") is None

    apply_summary = backfill_source_items(workspace, dry_run=False)
    assert format_summary(apply_summary) == "matched=4 added=4 skipped=0"
    rows = _read_rows(concepts_path)
    assert rows[0]["source_item"] == "1.2"
    assert rows[1]["source_item"] == "2.10"
    assert rows[2]["source_item"] == "1.10"
    assert rows[3]["source_item"] == "2.13"
    assert rows[4]["source_item"] == ""
    assert list(rows[0]) == FIELDNAMES

    second_summary = backfill_source_items(workspace, dry_run=False)
    assert format_summary(second_summary) == "matched=4 added=0 skipped=4"
