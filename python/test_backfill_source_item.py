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


def test_backfill_does_not_match_concept_id_against_jbil_source_item(tmp_path: pathlib.Path) -> None:
    """Concept id=1/label=hair must not inherit JBIL cue '1- one' by ID collision."""
    workspace = tmp_path / "workspace"
    staging = workspace / "imports" / "staging" / "Test01"
    staging.mkdir(parents=True)
    (staging / "cues.csv").write_text(
        "Name\tStart\tDuration\n"
        "1- one\t0\t1\n"
        "(2.5)- hair\t1\t1\n",
        encoding="utf-8",
    )
    concepts_path = workspace / "concepts.csv"
    with concepts_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(
            [
                {"id": "1", "concept_en": "hair", "source_item": "", "source_survey": "", "custom_order": ""},
                {"id": "2", "concept_en": "one", "source_item": "", "source_survey": "", "custom_order": ""},
            ]
        )

    summary = backfill_source_items(workspace, dry_run=False)
    rows = _read_rows(concepts_path)

    assert rows[0]["source_item"] == "2.5"
    assert rows[0]["source_survey"] == "KLQ"
    assert rows[1]["source_item"] == "1"
    assert rows[1]["source_survey"] == "JBIL"
    assert format_summary(summary) == "matched=2 added=2 skipped=0"


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
    assert rows[0]["source_survey"] == "KLQ"
    assert rows[1]["source_item"] == "2.10"
    assert rows[1]["source_survey"] == "KLQ"
    assert rows[2]["source_item"] == "1.10"
    assert rows[2]["source_survey"] == "KLQ"
    assert rows[3]["source_item"] == "2.13"
    assert rows[3]["source_survey"] == "KLQ"
    assert rows[4]["source_item"] == ""
    assert rows[4]["source_survey"] == ""
    assert list(rows[0]) == FIELDNAMES

    second_summary = backfill_source_items(workspace, dry_run=False)
    assert format_summary(second_summary) == "matched=4 added=0 skipped=4"


def test_backfill_populates_jbil_ext_surveys_and_skips_conflicting_existing_survey(tmp_path: pathlib.Path) -> None:
    workspace = tmp_path / "workspace"
    staging = workspace / "imports" / "staging" / "Mixed01"
    staging.mkdir(parents=True)
    (staging / "cues.csv").write_text(
        "Name\tStart\tDuration\n"
        "324-we\t0\t1\n"
        "[5.20]- When I was cutting up vegetables, I cut my hand.\t1\t1\n",
        encoding="utf-8",
    )

    concepts_path = workspace / "concepts.csv"
    with concepts_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(
            [
                {"id": "324", "concept_en": "we", "source_item": "", "source_survey": "", "custom_order": ""},
                {
                    "id": "5",
                    "concept_en": "When I was cutting up vegetables, I cut my hand.",
                    "source_item": "5.20",
                    "source_survey": "KLQ",
                    "custom_order": "",
                },
            ]
        )

    summary = backfill_source_items(workspace, dry_run=False)

    assert format_summary(summary) == "matched=2 added=1 skipped=1"
    rows = _read_rows(concepts_path)
    assert rows[0]["source_item"] == "324"
    assert rows[0]["source_survey"] == "JBIL"
    assert rows[1]["source_item"] == "5.20"
    assert rows[1]["source_survey"] == "KLQ"
    assert any("existing source_survey KLQ != EXT" in decision for decision in summary.decisions)
