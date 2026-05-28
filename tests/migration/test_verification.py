from __future__ import annotations

import json
from pathlib import Path

from python.migration.concept_suffix_pollution import (
    audit_text_vs_concept_en,
    validate_cross_survey_links,
    verify_post_migration,
)


def _write_workspace(workspace: Path) -> None:
    (workspace / "annotations").mkdir(parents=True)
    (workspace / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "53,snow,1.1,KLQ,1\n"
        "54,fog,9.9,XYZ,2\n",
        encoding="utf-8",
    )
    (workspace / "annotations" / "Khan01.parse.json").write_text(
        json.dumps({
            "tiers": {"concept": {"intervals": [
                {"start": 0, "end": 1, "text": "ice", "concept_id": "53"},
                {"start": 1, "end": 2, "text": "ghost", "concept_id": "999"},
            ]}},
            "concept_tags": {"999": ["custom-sk-concept-list"]},
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (workspace / "parse-tags.json").write_text(
        json.dumps([{"id": "custom-sk-concept-list", "concepts": ["53", "999"]}], indent=2) + "\n",
        encoding="utf-8",
    )


def test_verify_post_migration_reports_suffix_prefix_and_orphan_references(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_workspace(workspace)
    (workspace / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "53,snow (A),1.1,KLQ,1\n"
        "54,48 fog,9.9,XYZ,2\n",
        encoding="utf-8",
    )

    violations = verify_post_migration(workspace)

    assert any("suffix" in item and "id=53" in item for item in violations)
    assert any("leading cue prefix" in item and "id=54" in item for item in violations)
    assert any("orphan concept_id" in item and "999" in item for item in violations)
    assert any("parse-tags.json" in item and "999" in item for item in violations)


def test_validate_cross_survey_links_flags_wrong_target_label(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_workspace(workspace)
    (workspace / "survey-overlap.json").write_text(
        json.dumps({"concept_survey_links": {"53": {"XYZ": "9.9"}}}, indent=2) + "\n",
        encoding="utf-8",
    )

    violations = validate_cross_survey_links(workspace)

    assert violations
    assert any("hosts no concept matching label 'snow'" in item for item in violations)


def test_validate_cross_survey_links_missing_file_is_not_violation(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_workspace(workspace)

    assert validate_cross_survey_links(workspace) == []


def test_audit_text_vs_concept_en_flags_khan_snow_ice_swap(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_workspace(workspace)

    inconsistencies = audit_text_vs_concept_en(workspace)

    assert any("Khan01.parse.json" in item and "text='ice'" in item and "concept_en='snow'" in item for item in inconsistencies)


def test_cli_verify_only_returns_nonzero_for_audit_findings(tmp_path: Path, capsys) -> None:
    from python.scripts.migrate_concept_suffix_pollution import main

    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_workspace(workspace)

    exit_code = main(["--workspace", str(workspace), "--verify-only"])

    captured = capsys.readouterr().out
    assert exit_code == 1
    assert "post_migration_violations" in captured
    assert "text_vs_concept_en_inconsistencies" in captured
    assert "Khan01.parse.json" in captured
