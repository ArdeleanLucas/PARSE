"""Tests for the whole-speaker deletion core (speaker_delete.py)."""

from __future__ import annotations

import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import speaker_delete  # noqa: E402
from speaker_delete import SpeakerDeleteError, delete_speaker, speaker_exists  # noqa: E402


def _write_json(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_workspace(root: pathlib.Path, speaker: str = "Saha01") -> None:
    _write_json(root / "annotations" / "{0}.parse.json".format(speaker), {"speaker": speaker})
    _write_json(root / "annotations" / "{0}.json".format(speaker), {"speaker": speaker})
    (root / "audio" / "original" / speaker).mkdir(parents=True, exist_ok=True)
    (root / "audio" / "original" / speaker / "source.wav").write_bytes(b"RIFF")
    (root / "audio" / "working" / speaker).mkdir(parents=True, exist_ok=True)
    (root / "audio" / "working" / speaker / "recording.wav").write_bytes(b"RIFF")
    _write_json(root / "peaks" / "{0}.json".format(speaker), {"peaks": []})
    _write_json(root / "peaks" / "{0}_stem2.json".format(speaker), {"peaks": []})
    _write_json(root / "coarse_transcripts" / "{0}.json".format(speaker), {"segments": []})
    _write_json(root / "project.json", {"speakers": {speaker: {}, "Other01": {}}})
    _write_json(root / "source_index.json", {"speakers": {speaker: {"source_wavs": []}}})
    _write_json(
        root / "survey-overlap.json",
        {
            "speaker_choices": {speaker: {"1": "s1"}, "Other01": {"2": "s2"}},
            "speaker_concept_survey_links": {speaker: {"1": {}}},
        },
    )
    _write_json(
        root / "parse-enrichments.json",
        {
            "lexeme_notes": {speaker: {"1": "note"}, "Other01": {"2": "keep"}},
            "manual_overrides": {
                "canonical_lexemes": {
                    "bundleA": {speaker: {"csv_row_id": "5"}, "Other01": {"csv_row_id": "6"}},
                    "bundleB": {speaker: {"csv_row_id": "7"}},
                }
            },
        },
    )


def test_speaker_exists_detects_via_files_and_registry(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    assert speaker_exists(tmp_path, "Saha01") is True
    assert speaker_exists(tmp_path, "Nope99") is False


def test_dry_run_lists_without_touching_disk(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    result = delete_speaker(tmp_path, "Saha01", dry_run=True)

    assert result["dryRun"] is True
    assert result["speaker"] == "Saha01"
    # Files still present.
    assert (tmp_path / "annotations" / "Saha01.parse.json").exists()
    assert not (tmp_path / speaker_delete.TRASH_DIRNAME).exists()
    # Plan covers every artifact, including the multi-stem peaks file.
    planned = set(result["plannedFiles"])
    assert "annotations/Saha01.parse.json" in planned
    assert "annotations/Saha01.json" in planned
    assert "audio/original/Saha01" in planned
    assert "audio/working/Saha01" in planned
    assert "peaks/Saha01.json" in planned
    assert "peaks/Saha01_stem2.json" in planned
    assert "coarse_transcripts/Saha01.json" in planned
    # Registry plan mentions each shared sidecar key.
    registry = " ".join(result["plannedRegistry"])
    assert "project.json:speakers[Saha01]" in registry
    assert "source_index.json:speakers[Saha01]" in registry
    assert "survey-overlap.json:speaker_choices[Saha01]" in registry
    assert "parse-enrichments.json:lexeme_notes[Saha01]" in registry
    assert "canonical_lexemes[bundleA][Saha01]" in registry


def test_delete_moves_files_to_trash_and_prunes_registries(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    result = delete_speaker(tmp_path, "Saha01")

    assert result["dryRun"] is False
    trash_dir = tmp_path / result["trashDir"]
    assert trash_dir.is_dir()

    # Speaker artifacts gone from their live locations.
    assert not (tmp_path / "annotations" / "Saha01.parse.json").exists()
    assert not (tmp_path / "annotations" / "Saha01.json").exists()
    assert not (tmp_path / "audio" / "original" / "Saha01").exists()
    assert not (tmp_path / "audio" / "working" / "Saha01").exists()
    assert not (tmp_path / "peaks" / "Saha01.json").exists()
    assert not (tmp_path / "peaks" / "Saha01_stem2.json").exists()
    # ...and recoverable in trash.
    assert (trash_dir / "annotations" / "Saha01.parse.json").exists()
    assert (trash_dir / "audio" / "original" / "Saha01" / "source.wav").exists()

    # Registries pruned, other speakers untouched.
    project = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert "Saha01" not in project["speakers"]
    assert "Other01" in project["speakers"]
    source_index = json.loads((tmp_path / "source_index.json").read_text(encoding="utf-8"))
    assert "Saha01" not in source_index["speakers"]
    survey = json.loads((tmp_path / "survey-overlap.json").read_text(encoding="utf-8"))
    assert "Saha01" not in survey["speaker_choices"]
    assert "Other01" in survey["speaker_choices"]
    assert "Saha01" not in survey["speaker_concept_survey_links"]
    enrichments = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))
    assert "Saha01" not in enrichments["lexeme_notes"]
    assert "Other01" in enrichments["lexeme_notes"]
    canonical = enrichments["manual_overrides"]["canonical_lexemes"]
    assert "Saha01" not in canonical["bundleA"]
    assert "Other01" in canonical["bundleA"]
    # bundleB had only Saha01 -> emptied bundle dropped entirely.
    assert "bundleB" not in canonical

    # Shared registries backed up before mutation.
    backup = trash_dir / "_registry_backup"
    assert (backup / "project.json").exists()
    assert (backup / "survey-overlap.json").exists()
    assert (backup / "parse-enrichments.json").exists()


def test_unknown_speaker_raises_404(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    with pytest.raises(SpeakerDeleteError) as excinfo:
        delete_speaker(tmp_path, "Ghost42")
    assert excinfo.value.status == HTTPStatus.NOT_FOUND


def test_active_job_blocks_with_409(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    holder = {"jobId": "job-1", "jobType": "normalize"}
    with pytest.raises(SpeakerDeleteError) as excinfo:
        delete_speaker(tmp_path, "Saha01", active_job_check=lambda: holder)
    assert excinfo.value.status == HTTPStatus.CONFLICT
    assert excinfo.value.holder == holder
    # Nothing deleted when blocked.
    assert (tmp_path / "annotations" / "Saha01.parse.json").exists()


def test_active_job_check_none_allows_delete(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    result = delete_speaker(tmp_path, "Saha01", active_job_check=lambda: None)
    assert result["ok"] is True


@pytest.mark.parametrize("bad", ["../etc", "a/b", "a\\b", "", "."])
def test_invalid_speaker_name_raises_400(tmp_path: pathlib.Path, bad: str) -> None:
    with pytest.raises(SpeakerDeleteError) as excinfo:
        delete_speaker(tmp_path, bad)
    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
