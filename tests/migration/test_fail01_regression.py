from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from python.migration.concept_suffix_pollution import (
    audit_text_vs_concept_en,
    validate_cross_survey_links,
    verify_post_migration,
    run_migration,
)

EXPECTED_MERGES = {
    "634": "53",
    "635": "54",
    "636": "55",
    "637": "56",
    "638": "57",
    "639": "58",
    "640": "59",
    "641": "60",
}


def test_fail01_full_regression_merges_eight_pollution_patterns(tmp_path: Path) -> None:
    source = Path(__file__).parent / "fixtures" / "issue_529_full"
    workspace = tmp_path / "ws"
    shutil.copytree(source, workspace)

    result = run_migration(workspace)

    assert result.success
    assert result.already_canonical is False
    for old_id, new_id in EXPECTED_MERGES.items():
        assert result.merge_map[old_id] == new_id
    assert result.intervals_rekeyed >= 8
    assert result.text_fields_stripped >= 8
    assert result.concept_tags_rekeyed >= 8
    assert result.parse_tags_rekeyed == 1
    assert result.post_migration_violations == []
    assert result.cross_survey_link_violations == []
    assert result.text_vs_concept_en_inconsistencies == []

    rows = list(csv.DictReader((workspace / "concepts.csv").open(encoding="utf-8-sig")))
    remaining_ids = {row["id"] for row in rows}
    assert not (set(EXPECTED_MERGES) & remaining_ids)
    assert set(EXPECTED_MERGES.values()) <= remaining_ids

    fail01 = json.loads((workspace / "annotations" / "Fail01.parse.json").read_text(encoding="utf-8"))
    intervals = fail01["tiers"]["concept"]["intervals"]
    concept_ids = {str(interval["concept_id"]) for interval in intervals}
    assert not (set(EXPECTED_MERGES) & concept_ids)
    assert set(EXPECTED_MERGES.values()) <= concept_ids
    assert all("(A)" not in interval["text"] and "(B)" not in interval["text"] for interval in intervals)

    tags = json.loads((workspace / "parse-tags.json").read_text(encoding="utf-8"))
    thesis_tag = next(tag for tag in tags if tag["id"] == "custom-sk-concept-list")
    assert not (set(EXPECTED_MERGES) & set(thesis_tag["concepts"]))
    assert set(EXPECTED_MERGES.values()) <= set(thesis_tag["concepts"])
    assert len(thesis_tag["concepts"]) == len(set(thesis_tag["concepts"]))

    assert verify_post_migration(workspace) == []
    assert validate_cross_survey_links(workspace) == []
    assert audit_text_vs_concept_en(workspace) == []
