from __future__ import annotations

import shutil
from pathlib import Path

from cross_survey_links import compute_cross_survey_link_patch, patch_from_cross_survey_link_summary
from survey_overlap import update_survey_overlap_state

FIXTURE = Path(__file__).parent / "test_fixtures" / "cross_survey_links_workspace"


def copy_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace)
    return workspace


def by_concept(entries: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(entry["concept_id"]): entry for entry in entries}


def test_compute_cross_survey_link_patch_adds_single_word_twin(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    additions = by_concept(summary["would_add"])
    assert additions["1"]["links"] == {"klq": "1.5"}
    assert by_concept(summary["matched"])["1"]["reference_links"] == {"jbil": "10", "klq": "1.5"}


def test_compute_cross_survey_link_patch_skips_multiword_by_default(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    skipped = by_concept(summary["skipped_multiword"])
    assert skipped["2"]["concept_en"] == "father (vocative)"
    assert skipped["2"]["reason"] == "single_word_only"


def test_compute_cross_survey_link_patch_conflicts_on_legacy_primary_mismatch(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["3"]
    assert conflict["reason"] == "legacy_primary_mismatch"
    assert conflict["legacy_primary"] == {"survey": "jbil", "source_item": "30"}
    assert conflict["reference_primary"] == {"survey": "jbil", "source_item": "31"}
    assert "3" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_does_not_duplicate_existing_sidecar_link(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    assert "4" in by_concept(summary["matched"])
    assert "4" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_empty_workspace_returns_empty_lists(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.csv"
    reference_path.write_text("source,id,lexeme\nJBIL,1,one\nKLQ,1.1,one\n", encoding="utf-8")

    summary = compute_cross_survey_link_patch(tmp_path / "empty", reference_path)

    assert summary == {"matched": [], "would_add": [], "conflicts": [], "skipped_multiword": []}


def test_cross_survey_link_patch_is_idempotent_after_sidecar_update(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")
    patch = patch_from_cross_survey_link_summary(summary)

    update_survey_overlap_state(workspace, {"concept_survey_links": patch})
    second = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    assert patch == {"1": {"klq": "1.5"}, "5": {"klq": "5.0"}}
    assert second["would_add"] == []
