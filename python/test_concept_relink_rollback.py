from __future__ import annotations

import csv
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import concept_relink
from concept_relink import ConceptRelinkError, apply_relink_by_gloss

_FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


def _seed_concepts(project_root: pathlib.Path) -> None:
    with (project_root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "concept_en": "(1.5)- Nose",
                "source_item": "",
                "source_survey": "",
                "custom_order": "10",
            }
        )
        writer.writerow(
            {
                "id": "2",
                "concept_en": "Nose A",
                "source_item": "34",
                "source_survey": "JBIL",
                "custom_order": "20",
            }
        )


def _seed_overlap(project_root: pathlib.Path) -> None:
    payload = {
        "version": 1,
        "color_coding_enabled": True,
        "surveys": {},
        "concept_survey_links": {"1": {"KLQ": "1.5"}, "2": {"EXT": "5.1"}},
        "speaker_choices": {"Saha01": {"1": "KLQ"}},
    }
    (project_root / "survey-overlap.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_annotation(project_root: pathlib.Path) -> pathlib.Path:
    annotations_dir = project_root / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    path = annotations_dir / "Saha01.parse.json"
    payload = {
        "speaker": "Saha01",
        "tiers": {
            "concept": {
                "name": "concept",
                "display_order": 1,
                "intervals": [
                    {"start": 1.0, "end": 1.5, "text": "nose", "concept_id": "1", "manuallyAdjusted": True}
                ],
            }
        },
        "confirmed_anchors": {"1": {"start": 1.0, "end": 1.5, "source": "manual"}},
        "concept_tags": {"1": ["core"]},
        "ipa_candidates": {"1::ipa::0": [{"raw_ipa": "n"}]},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _seed_workspace(project_root: pathlib.Path) -> pathlib.Path:
    _seed_concepts(project_root)
    _seed_overlap(project_root)
    return _seed_annotation(project_root)


def _backup_files(project_root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(path for path in (project_root / "backups").glob("relink-by-gloss-*/**/*") if path.is_file())


def test_apply_restores_backups_after_mid_apply_write_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    annotation_path = _seed_workspace(tmp_path)
    pre_concepts = (tmp_path / "concepts.csv").read_text(encoding="utf-8")
    pre_overlap = (tmp_path / "survey-overlap.json").read_text(encoding="utf-8")
    pre_annotation = annotation_path.read_text(encoding="utf-8")

    def fail_concepts_write(*args: object, **kwargs: object) -> None:
        raise OSError("concept write exploded")

    monkeypatch.setattr(concept_relink, "write_concepts_csv_rows", fail_concepts_write)

    with pytest.raises(ConceptRelinkError) as exc_info:
        apply_relink_by_gloss(tmp_path, accepted_groups=[{"keep_concept_id": "2", "merge_concept_ids": ["1"]}])

    assert exc_info.value.status == 500
    assert exc_info.value.message.startswith("apply_failed_restored_from_backup")
    assert (tmp_path / "concepts.csv").read_text(encoding="utf-8") == pre_concepts
    assert (tmp_path / "survey-overlap.json").read_text(encoding="utf-8") == pre_overlap
    assert annotation_path.read_text(encoding="utf-8") == pre_annotation

    backup_paths = [path.relative_to(tmp_path).as_posix() for path in _backup_files(tmp_path)]
    assert any(path.endswith("concepts.csv") for path in backup_paths)
    assert any(path.endswith("survey-overlap.json") for path in backup_paths)
    assert any(path.endswith("annotations/Saha01.parse.json") for path in backup_paths)


def test_apply_reports_original_and_restore_errors_when_restore_fails(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_workspace(tmp_path)

    def fail_copy2(*args: object, **kwargs: object) -> None:
        raise OSError("restore copy exploded")

    def fail_concepts_write(*args: object, **kwargs: object) -> None:
        monkeypatch.setattr(concept_relink.shutil, "copy2", fail_copy2)
        raise OSError("concept write exploded")

    monkeypatch.setattr(concept_relink, "write_concepts_csv_rows", fail_concepts_write)

    with pytest.raises(ConceptRelinkError) as exc_info:
        apply_relink_by_gloss(tmp_path, accepted_groups=[{"keep_concept_id": "2", "merge_concept_ids": ["1"]}])

    assert exc_info.value.status == 500
    assert exc_info.value.message.startswith("apply_failed_restore_failed:")
    assert "concept write exploded" in exc_info.value.message
    assert "restore copy exploded" in exc_info.value.message
