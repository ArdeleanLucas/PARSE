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


def write_minimal_workspace(
    tmp_path: Path,
    *,
    concepts_csv: str,
    reference_csv: str,
    survey_overlap_json: str | None = None,
) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "concepts.csv").write_text(concepts_csv, encoding="utf-8")
    (workspace / "reference.csv").write_text(reference_csv, encoding="utf-8")
    if survey_overlap_json is not None:
        (workspace / "survey-overlap.json").write_text(survey_overlap_json, encoding="utf-8")
    return workspace


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


def test_compute_cross_survey_link_patch_flags_reference_ambiguous(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n1,stone,50,JBIL,1\n",
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,50,stone\n"
            "KLQ,5.0,stone\n"
            "KLQ,5.1,stone\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["1"]
    assert conflict["reason"] == "reference_ambiguous"
    assert conflict["reference_conflicts"] == [
        {"survey": "klq", "first_source_item": "5.0", "conflicting_source_item": "5.1"}
    ]
    assert "1" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_flags_existing_sidecar_mismatch(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n1,stone,50,JBIL,1\n",
        reference_csv="source,id,lexeme\nJBIL,50,stone\nKLQ,5.0,stone\n",
        survey_overlap_json='{ "concept_survey_links": { "1": { "klq": "9.9" } } }\n',
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["1"]
    assert conflict["reason"] == "existing_sidecar_mismatch"
    assert conflict["sidecar_mismatches"] == [
        {"survey": "klq", "existing_source_item": "9.9", "reference_source_item": "5.0"}
    ]
    assert "1" not in by_concept(summary["would_add"])


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
