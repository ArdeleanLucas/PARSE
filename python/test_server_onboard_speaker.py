"""Tests for _run_onboard_speaker_job concepts.csv / project.json updates."""
import csv
import json
import pathlib
import sys

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


def _stub_job(monkeypatch) -> None:
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
