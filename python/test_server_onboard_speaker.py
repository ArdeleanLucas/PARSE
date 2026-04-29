"""Tests for _run_onboard_speaker_job concepts.csv / project.json updates."""
import csv
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def _make_wav(project_root: pathlib.Path, speaker: str, name: str = "source.wav") -> pathlib.Path:
    wav_dir = project_root / "audio" / "original" / speaker
    wav_dir.mkdir(parents=True, exist_ok=True)
    wav_dest = wav_dir / name
    wav_dest.write_bytes(b"RIFF0000WAVEfmt ")
    return wav_dest


def _write_concepts_csv(path: pathlib.Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_audition_csv(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Name", "Start", "Duration", "Time Format", "Type", "Description"],
            delimiter="\t",
        )
        writer.writeheader()
        for row in rows:
            payload = {"Time Format": "decimal", "Type": "Cue", "Description": ""}
            payload.update(row)
            writer.writerow(payload)


def _stub_job(monkeypatch) -> None:
    server._install_route_bindings()
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_set_job_complete", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_set_job_error", lambda *args, **kwargs: None)


def test_onboard_populates_project_json_speakers(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _stub_job(monkeypatch)

    wav_dest = _make_wav(tmp_path, "Fail02")
    server._run_onboard_speaker_job("job-1", "Fail02", wav_dest, None)

    project = json.loads((tmp_path / "project.json").read_text())
    assert "speakers" in project
    assert "Fail02" in project["speakers"]


def test_onboard_merges_concepts_csv_when_format_matches(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _stub_job(monkeypatch)

    wav_dest = _make_wav(tmp_path, "Fail02")
    csv_dest = wav_dest.parent / "elicitation.csv"
    _write_concepts_csv(
        csv_dest,
        [{"id": "1", "concept_en": "ash"}, {"id": "2", "concept_en": "bark"}],
    )

    server._run_onboard_speaker_job("job-2", "Fail02", wav_dest, csv_dest)

    concepts_path = tmp_path / "concepts.csv"
    assert concepts_path.exists()
    with open(concepts_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"id": "1", "concept_en": "ash"},
        {"id": "2", "concept_en": "bark"},
    ]


def test_onboard_preserves_existing_concepts_on_id_collision(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _stub_job(monkeypatch)

    existing = tmp_path / "concepts.csv"
    _write_concepts_csv(existing, [{"id": "1", "concept_en": "ash"}])

    wav_dest = _make_wav(tmp_path, "Fail02")
    csv_dest = wav_dest.parent / "elicitation.csv"
    _write_concepts_csv(
        csv_dest,
        [
            {"id": "1", "concept_en": "ASH-OVERWRITE"},
            {"id": "3", "concept_en": "fire"},
        ],
    )

    server._run_onboard_speaker_job("job-3", "Fail02", wav_dest, csv_dest)

    with open(existing, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows_by_id = {row["id"]: row["concept_en"] for row in rows}
    assert rows_by_id == {"1": "ash", "3": "fire"}


def test_onboard_ignores_csv_with_unexpected_columns(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _stub_job(monkeypatch)

    wav_dest = _make_wav(tmp_path, "Fail02")
    csv_dest = wav_dest.parent / "cues.csv"
    csv_dest.write_text("Start,End,Label\n0.0,1.0,cue1\n", encoding="utf-8")

    server._run_onboard_speaker_job("job-4", "Fail02", wav_dest, csv_dest)

    assert not (tmp_path / "concepts.csv").exists()


def test_onboard_audition_csv_writes_lexeme_intervals_in_csv_order(tmp_path, monkeypatch) -> None:
    server._install_route_bindings()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    complete_calls = []
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_set_job_complete", lambda job_id, result, **kwargs: complete_calls.append((job_id, result, kwargs)))
    monkeypatch.setattr(
        server,
        "_set_job_error",
        lambda job_id, message: (_ for _ in ()).throw(AssertionError(message)),
    )

    wav_dest = _make_wav(tmp_path, "SahaTest")
    csv_dest = wav_dest.parent / "cues.csv"
    _write_audition_csv(
        csv_dest,
        [
            {"Name": "(1.2)- forehead", "Start": "2:19:07.403", "Duration": "0:01.236"},
            {"Name": "9- nine", "Start": "20:12.776", "Duration": "0:00.967"},
            {"Name": "(8.4)- to listen to", "Start": "2:48:11.681", "Duration": "0:00.993"},
        ],
    )

    server._run_onboard_speaker_job("job-audition", "SahaTest", wav_dest, csv_dest)

    canonical_path = tmp_path / "annotations" / "SahaTest.parse.json"
    legacy_path = tmp_path / "annotations" / "SahaTest.json"
    assert canonical_path.exists()
    assert legacy_path.exists()
    annotation = json.loads(canonical_path.read_text(encoding="utf-8"))
    legacy_annotation = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert legacy_annotation == annotation

    concept_intervals = annotation["tiers"]["concept"]["intervals"]
    assert [interval["text"] for interval in concept_intervals] == ["forehead", "nine", "to listen to"]
    assert [interval["start"] for interval in concept_intervals] == pytest.approx([8347.403, 1212.776, 10091.681])
    assert [interval["end"] for interval in concept_intervals] == pytest.approx([8348.639, 1213.743, 10092.674])

    ortho_words = annotation["tiers"]["ortho_words"]["intervals"]
    assert ortho_words == concept_intervals
    assert annotation["tiers"]["ipa"]["intervals"] == []
    assert annotation["tiers"]["ortho"]["intervals"] == []
    assert "bnd" not in annotation["tiers"]

    with open(tmp_path / "concepts.csv", newline="", encoding="utf-8") as handle:
        rows_by_id = {row["id"]: row["concept_en"] for row in csv.DictReader(handle)}
    assert rows_by_id == {"1.2": "forehead", "9": "nine", "8.4": "to listen to"}
    assert complete_calls[0][2]["message"] == "Imported 3 lexemes from cues.csv"
    assert complete_calls[0][1]["lexemesImported"] == 3


def test_onboard_is_idempotent_on_replay(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _stub_job(monkeypatch)

    wav_dest = _make_wav(tmp_path, "Fail02")
    csv_dest = wav_dest.parent / "elicitation.csv"
    _write_concepts_csv(csv_dest, [{"id": "1", "concept_en": "ash"}])

    server._run_onboard_speaker_job("job-5a", "Fail02", wav_dest, csv_dest)
    server._run_onboard_speaker_job("job-5b", "Fail02", wav_dest, csv_dest)

    with open(tmp_path / "concepts.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"id": "1", "concept_en": "ash"}]

    project = json.loads((tmp_path / "project.json").read_text())
    assert list(project["speakers"].keys()) == ["Fail02"]

    source_index = json.loads((tmp_path / "source_index.json").read_text())
    wav_entries = source_index["speakers"]["Fail02"]["source_wavs"]
    assert len(wav_entries) == 1
