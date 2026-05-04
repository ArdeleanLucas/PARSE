from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys
import wave
from types import MethodType

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ChatToolValidationError, ParseChatTools
from concept_source_item import CONCEPT_FIELDNAMES
import ai.tools.speaker_import_tools as speaker_import_tools
from ai.tools.speaker_import_tools import (
    tool_csv_only_reimport,
    tool_import_processed_speaker,
    tool_onboard_speaker_import,
    tool_revert_csv_reimport,
)


def _write_test_wav(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 8000)


def _write_processed_fixture(root: pathlib.Path, speaker: str = "Fail02") -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    wav_path = root / "Audio_Working" / speaker / "speaker.wav"
    _write_test_wav(wav_path)

    annotation_path = root / "annotations" / f"{speaker}.json"
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "southern-kurdish-dialect-comparison",
                "speaker": speaker,
                "source_audio": f"audio/working/{speaker}/speaker.wav",
                "source_audio_duration_sec": 2.0,
                "metadata": {"language_code": "sdh", "timestamps_source": "processed"},
                "tiers": {
                    "concept": {"display_order": 3, "intervals": [{"start": 0.0, "end": 1.0, "text": "1: ash"}, {"start": 1.0, "end": 2.0, "text": "2: bark"}]},
                    "speaker": {"display_order": 4, "intervals": [{"start": 0.0, "end": 1.0, "text": speaker}, {"start": 1.0, "end": 2.0, "text": speaker}]},
                },
            }
        ),
        encoding="utf-8",
    )

    peaks_path = root / "peaks" / f"{speaker}.json"
    peaks_path.parent.mkdir(parents=True, exist_ok=True)
    peaks_path.write_text(json.dumps({"duration": 2.0, "peaks": [0, 1, 0, -1]}), encoding="utf-8")
    return wav_path, annotation_path, peaks_path


def _write_csv_reimport_workspace(project_root: pathlib.Path, speaker: str = "Saha01") -> tuple[pathlib.Path, pathlib.Path]:
    (project_root / "annotations").mkdir(parents=True, exist_ok=True)
    (project_root / "audio" / "original" / speaker).mkdir(parents=True, exist_ok=True)
    wav_path = project_root / "audio" / "original" / speaker / "registered.wav"
    _write_test_wav(wav_path)
    (project_root / "annotations" / f"{speaker}.json").write_bytes(b'{"before":"legacy"}\n')
    (project_root / "annotations" / f"{speaker}.parse.json").write_bytes(b'{"before":"parse"}\n')
    (project_root / "parse-enrichments.json").write_bytes(b'{"lexeme_notes":{}}\n')
    (project_root / "concepts.csv").write_bytes(b"id,concept_en\n1,old ash\n")
    (project_root / "source_index.json").write_text(
        json.dumps(
            {
                "speakers": {
                    speaker: {
                        "source_wavs": [
                            {"filename": "secondary.wav", "path": f"audio/original/{speaker}/secondary.wav", "is_primary": False},
                            {"filename": "registered.wav", "path": f"audio/original/{speaker}/registered.wav", "is_primary": True},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    source_csv = project_root / "audio" / "original" / speaker / "refreshed.csv"
    comments_csv = project_root / "audio" / "original" / speaker / "refreshed-comments.csv"
    source_csv.write_text(
        "Name\tStart\tDuration\tTime Format\tType\tDescription\n"
        "(1.1)- ash\t0:00.000\t0:01.000\tdecimal\tCue\t\n"
        "(2.1)- bark\t0:01.000\t0:01.000\tdecimal\tCue\t\n",
        encoding="utf-8",
    )
    comments_csv.write_text(
        "Name\tStart\tDuration\tTime Format\tType\tDescription\n"
        "(1.1)- ash - field note\t0:00.000\t0:01.000\tdecimal\tCue\t\n"
        "(2.1)- bark - second note\t0:01.000\t0:01.000\tdecimal\tCue\t\n",
        encoding="utf-8",
    )
    return source_csv, comments_csv


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked_reimport_files(project_root: pathlib.Path, speaker: str = "Saha01") -> dict[str, pathlib.Path]:
    return {
        f"{speaker}.json": project_root / "annotations" / f"{speaker}.json",
        f"{speaker}.parse.json": project_root / "annotations" / f"{speaker}.parse.json",
        "parse-enrichments.json": project_root / "parse-enrichments.json",
        "concepts.csv": project_root / "concepts.csv",
    }


def _write_concepts_fixture(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CONCEPT_FIELDNAMES))
        writer.writeheader()
        writer.writerows(rows)


def _read_concepts_fixture(path: pathlib.Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def test_mcp_write_concepts_csv_preserves_existing_source_item_and_survey(tmp_path) -> None:
    project_root = tmp_path / "proj"
    concepts_path = project_root / "concepts.csv"
    _write_concepts_fixture(
        concepts_path,
        [
            {
                "id": "1",
                "concept_en": "ash",
                "source_item": "1.1",
                "source_survey": "KLQ",
                "custom_order": "10",
            },
            {
                "id": "2",
                "concept_en": "water",
                "source_item": "",
                "source_survey": "",
                "custom_order": "",
            },
        ],
    )
    tools = ParseChatTools(project_root=project_root)

    total = speaker_import_tools._write_concepts_csv(tools, [{"id": "3", "label": "bark"}])

    fieldnames, rows = _read_concepts_fixture(concepts_path)
    rows_by_id = {row["id"]: row for row in rows}
    assert total == 3
    assert fieldnames == list(CONCEPT_FIELDNAMES)
    assert rows_by_id["1"]["source_item"] == "1.1"
    assert rows_by_id["1"]["source_survey"] == "KLQ"
    assert rows_by_id["1"]["custom_order"] == "10"


def test_mcp_write_concepts_csv_writes_source_item_and_survey_for_new_rows(tmp_path) -> None:
    project_root = tmp_path / "proj"
    tools = ParseChatTools(project_root=project_root)

    total = speaker_import_tools._write_concepts_csv(
        tools,
        [
            {
                "id": "5",
                "label": "forehead",
                "source_item": "1.2",
                "source_survey": "KLQ",
                "custom_order": "20",
            }
        ],
    )

    fieldnames, rows = _read_concepts_fixture(project_root / "concepts.csv")
    assert total == 1
    assert fieldnames == list(CONCEPT_FIELDNAMES)
    assert rows == [
        {
            "id": "5",
            "concept_en": "forehead",
            "source_item": "1.2",
            "source_survey": "KLQ",
            "custom_order": "20",
        }
    ]


def test_tool_onboard_speaker_import_reports_dry_run_plan_directly(tmp_path) -> None:
    external_root = tmp_path / "external"
    external_root.mkdir()
    wav_path = external_root / "spk1.wav"
    _write_test_wav(wav_path)

    project_root = tmp_path / "proj"
    project_root.mkdir()
    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])

    def _display_override(self, path: pathlib.Path) -> str:
        return f"display::{path.name}"

    tools._display_readable_path = MethodType(_display_override, tools)

    payload = tool_onboard_speaker_import(
        tools,
        {"speaker": "Speaker01", "sourceWav": str(wav_path), "dryRun": True},
    )

    assert payload["ok"] is True
    assert payload["dryRun"] is True
    assert payload["plan"]["speaker"] == "Speaker01"
    assert payload["plan"]["wavDest"] == "display::spk1.wav"


def test_tool_import_processed_speaker_reports_dry_run_plan_directly(tmp_path) -> None:
    external_root = tmp_path / "Thesis"
    wav_path, annotation_path, peaks_path = _write_processed_fixture(external_root)
    project_root = tmp_path / "proj"
    project_root.mkdir()
    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])

    payload = tool_import_processed_speaker(
        tools,
        {
            "speaker": "Fail02",
            "workingWav": str(wav_path),
            "annotationJson": str(annotation_path),
            "peaksJson": str(peaks_path),
            "dryRun": True,
        },
    )

    assert payload["ok"] is True
    assert payload["dryRun"] is True
    assert payload["plan"]["speaker"] == "Fail02"
    assert payload["plan"]["conceptCount"] == 2
    assert payload["plan"]["audioDest"].endswith("audio/working/Fail02/speaker.wav")


def test_csv_only_reimport_takes_backup_and_calls_worker(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    source_csv, comments_csv = _write_csv_reimport_workspace(project_root)
    tools = ParseChatTools(project_root=project_root, external_read_roots=[project_root])
    calls: list[dict[str, pathlib.Path | str | None]] = []

    def _fake_worker(root: pathlib.Path, speaker: str, wav_dest: pathlib.Path, csv_dest: pathlib.Path, comments_dest: pathlib.Path | None) -> dict[str, object]:
        calls.append({"root": root, "speaker": speaker, "wav": wav_dest, "csv": csv_dest, "comments": comments_dest})
        return {
            "speaker": speaker,
            "wavPath": "audio/original/Saha01/registered.wav",
            "csvPath": "audio/original/Saha01/refreshed.csv",
            "commentsCsvPath": "audio/original/Saha01/refreshed-comments.csv",
            "annotationPath": "annotations/Saha01.parse.json",
            "conceptsAdded": 2,
            "conceptTotal": 2,
            "commentsImported": 2,
            "lexemesImported": 2,
        }

    monkeypatch.setattr(speaker_import_tools, "_run_csv_reimport_worker", _fake_worker)

    payload = tool_csv_only_reimport(
        tools,
        {"speaker": "Saha01", "sourceCsv": str(source_csv), "commentsCsv": str(comments_csv)},
    )

    assert payload["ok"] is True
    assert payload["dryRun"] is False
    assert payload["lexemesImported"] == 2
    assert calls == [
        {
            "root": project_root.resolve(),
            "speaker": "Saha01",
            "wav": project_root.resolve() / "audio" / "original" / "Saha01" / "registered.wav",
            "csv": source_csv.resolve(),
            "comments": comments_csv.resolve(),
        }
    ]
    backup_dir = project_root / payload["backupDir"]
    assert backup_dir.parent == project_root / "annotations" / "backups"
    assert backup_dir.name.endswith("-Saha01-csv-reimport")
    assert {path.name for path in backup_dir.iterdir()} == {
        "Saha01.json",
        "Saha01.parse.json",
        "parse-enrichments.json",
        "concepts.csv",
        "manifest.json",
    }
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    assert manifest["speaker"] == "Saha01"
    assert manifest["operation"] == "csv_only_reimport"
    assert manifest["files"] == ["Saha01.json", "Saha01.parse.json", "parse-enrichments.json", "concepts.csv"]
    assert manifest["input"] == {
        "sourceCsv": "audio/original/Saha01/refreshed.csv",
        "commentsCsv": "audio/original/Saha01/refreshed-comments.csv",
        "wavPath": "audio/original/Saha01/registered.wav",
    }
    assert manifest["result"]["lexemesImported"] == 2
    assert (backup_dir / "Saha01.json").read_bytes() == b'{"before":"legacy"}\n'


def test_csv_only_reimport_dry_run_does_not_write(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    source_csv, comments_csv = _write_csv_reimport_workspace(project_root)
    tools = ParseChatTools(project_root=project_root, external_read_roots=[project_root])

    def _fail_worker(*_args, **_kwargs) -> dict[str, object]:
        raise AssertionError("dry-run must not call worker")

    monkeypatch.setattr(speaker_import_tools, "_run_csv_reimport_worker", _fail_worker)

    payload = tool_csv_only_reimport(
        tools,
        {"speaker": "Saha01", "sourceCsv": str(source_csv), "commentsCsv": str(comments_csv), "dryRun": True},
    )

    assert payload["ok"] is True
    assert payload["dryRun"] is True
    assert payload["lexemesImported"] is None
    assert payload["backupDir"].startswith("annotations/backups/")
    assert not (project_root / "annotations" / "backups").exists()


def test_csv_only_reimport_rejects_speaker_without_wav(tmp_path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    source_csv, _comments_csv = _write_csv_reimport_workspace(project_root)
    (project_root / "source_index.json").write_text(json.dumps({"speakers": {"Saha01": {"source_wavs": []}}}), encoding="utf-8")
    tools = ParseChatTools(project_root=project_root, external_read_roots=[project_root])

    with pytest.raises(ChatToolValidationError, match="has no registered WAV"):
        tool_csv_only_reimport(tools, {"speaker": "Saha01", "sourceCsv": str(source_csv)})


def test_csv_only_reimport_rejects_speaker_without_annotation(tmp_path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    source_csv, _comments_csv = _write_csv_reimport_workspace(project_root)
    (project_root / "annotations" / "Saha01.json").unlink()
    (project_root / "annotations" / "Saha01.parse.json").unlink()
    tools = ParseChatTools(project_root=project_root, external_read_roots=[project_root])

    with pytest.raises(ChatToolValidationError, match="has no annotation record"):
        tool_csv_only_reimport(tools, {"speaker": "Saha01", "sourceCsv": str(source_csv)})


def test_revert_csv_reimport_restores_all_files(tmp_path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    _write_csv_reimport_workspace(project_root)
    backup_dir = project_root / "annotations" / "backups" / "20260430T010000Z-Saha01-csv-reimport"
    backup_dir.mkdir(parents=True)
    for filename, path in _tracked_reimport_files(project_root).items():
        (backup_dir / filename).write_bytes(path.read_bytes())
        path.write_bytes(f"mutated {filename}\n".encode("utf-8"))
    (backup_dir / "manifest.json").write_text(
        json.dumps({"version": 1, "speaker": "Saha01", "operation": "csv_only_reimport", "files": list(_tracked_reimport_files(project_root).keys())}),
        encoding="utf-8",
    )
    tools = ParseChatTools(project_root=project_root)

    payload = tool_revert_csv_reimport(tools, {"speaker": "Saha01", "backupDir": backup_dir.name})

    assert payload["ok"] is True
    assert payload["dryRun"] is False
    assert payload["restoredFiles"] == ["Saha01.json", "Saha01.parse.json", "parse-enrichments.json", "concepts.csv"]
    assert payload["skippedFiles"] == []
    assert (project_root / "annotations" / "Saha01.json").read_bytes() == b'{"before":"legacy"}\n'
    assert (project_root / "annotations" / "Saha01.parse.json").read_bytes() == b'{"before":"parse"}\n'
    assert (project_root / "parse-enrichments.json").read_bytes() == b'{"lexeme_notes":{}}\n'
    assert (project_root / "concepts.csv").read_bytes() == b"id,concept_en\n1,old ash\n"


def test_revert_csv_reimport_picks_latest_backup_when_dir_omitted(tmp_path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    _write_csv_reimport_workspace(project_root)
    backups_root = project_root / "annotations" / "backups"
    for stamp, content in [("20260430T010000Z", b"oldest\n"), ("20260430T020000Z", b"newest\n")]:
        backup_dir = backups_root / f"{stamp}-Saha01-csv-reimport"
        backup_dir.mkdir(parents=True)
        (backup_dir / "concepts.csv").write_bytes(content)
        (backup_dir / "manifest.json").write_text(
            json.dumps({"version": 1, "speaker": "Saha01", "operation": "csv_only_reimport", "files": ["concepts.csv"]}),
            encoding="utf-8",
        )
    (project_root / "concepts.csv").write_bytes(b"mutated\n")
    tools = ParseChatTools(project_root=project_root)

    payload = tool_revert_csv_reimport(tools, {"speaker": "Saha01"})

    assert payload["backupDir"] == "annotations/backups/20260430T020000Z-Saha01-csv-reimport"
    assert payload["restoredFiles"] == ["concepts.csv"]
    assert (project_root / "concepts.csv").read_bytes() == b"newest\n"


def test_revert_csv_reimport_rejects_unknown_speaker(tmp_path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    tools = ParseChatTools(project_root=project_root)

    with pytest.raises(ChatToolValidationError, match="No csv-reimport backups found"):
        tool_revert_csv_reimport(tools, {"speaker": "Saha01"})


def test_csv_reimport_round_trip_preserves_files(tmp_path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    source_csv, comments_csv = _write_csv_reimport_workspace(project_root)
    before = {filename: _sha256(path) for filename, path in _tracked_reimport_files(project_root).items()}
    tools = ParseChatTools(project_root=project_root, external_read_roots=[project_root])

    imported = tool_csv_only_reimport(
        tools,
        {"speaker": "Saha01", "sourceCsv": str(source_csv), "commentsCsv": str(comments_csv)},
    )
    assert imported["ok"] is True
    assert imported["lexemesImported"] == 2
    assert before != {filename: _sha256(path) for filename, path in _tracked_reimport_files(project_root).items()}

    reverted = tool_revert_csv_reimport(tools, {"speaker": "Saha01"})

    assert reverted["ok"] is True
    assert {filename: _sha256(path) for filename, path in _tracked_reimport_files(project_root).items()} == before
