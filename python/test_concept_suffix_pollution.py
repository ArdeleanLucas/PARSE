from __future__ import annotations

import csv
import json
from pathlib import Path

from migration.concept_suffix_pollution import validate_cross_survey_links


def _write_concepts_csv(workspace: Path, rows: list[dict[str, str]]) -> None:
    with (workspace / "concepts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_survey_overlap(workspace: Path, links: dict[str, dict[str, str]]) -> None:
    (workspace / "survey-overlap.json").write_text(
        json.dumps({"concept_survey_links": links}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_validate_cross_survey_links_tolerates_clarifier_parens(tmp_path: Path) -> None:
    _write_concepts_csv(
        tmp_path,
        [
            {"id": "1", "concept_en": "wide", "source_item": "13.1", "source_survey": "KLQ", "custom_order": ""},
            {"id": "2", "concept_en": "wide (road)", "source_item": "41", "source_survey": "JBIL", "custom_order": ""},
        ],
    )
    _write_survey_overlap(tmp_path, {"1": {"JBIL": "41"}})

    assert validate_cross_survey_links(tmp_path) == []


def test_validate_cross_survey_links_still_catches_real_mismatches(tmp_path: Path) -> None:
    _write_concepts_csv(
        tmp_path,
        [
            {"id": "1", "concept_en": "blue", "source_item": "9.1", "source_survey": "KLQ", "custom_order": ""},
            {"id": "2", "concept_en": "green", "source_item": "27", "source_survey": "JBIL", "custom_order": ""},
        ],
    )
    _write_survey_overlap(tmp_path, {"1": {"JBIL": "27"}})

    violations = validate_cross_survey_links(tmp_path)

    assert len(violations) == 1
    assert "blue" in violations[0]
    assert "links 1" in violations[0]
