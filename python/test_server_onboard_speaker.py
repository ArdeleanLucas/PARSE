"""Tests for _run_onboard_speaker_job concepts.csv / project.json updates."""
import csv
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
from server_routes import media


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


def _read_concepts_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _parse_audition_rows(rows: list[dict[str, str]]):
    from lexeme_notes import parse_audition_csv

    header = ["Name", "Start", "Duration", "Time Format", "Type", "Description"]
    lines = ["\t".join(header)]
    for row in rows:
        payload = {"Time Format": "decimal", "Type": "Cue", "Description": ""}
        payload.update(row)
        lines.append("\t".join(payload.get(column, "") for column in header))
    return parse_audition_csv("\n".join(lines) + "\n")


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
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "2", "concept_en": "forehead"},
            {"id": "225", "concept_en": "nine"},
        ],
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
    assert [interval["concept_id"] for interval in concept_intervals] == ["2", "225", "226"]
    assert [interval["import_index"] for interval in concept_intervals] == [0, 1, 2]
    assert [interval["audition_prefix"] for interval in concept_intervals] == ["1.2", "9", "8.4"]

    ortho_words = annotation["tiers"]["ortho_words"]["intervals"]
    assert ortho_words == concept_intervals
    assert [interval["import_index"] for interval in ortho_words] == [0, 1, 2]
    assert annotation["tiers"]["ipa"]["intervals"] == []
    assert annotation["tiers"]["ortho"]["intervals"] == []
    assert "bnd" not in annotation["tiers"]

    concept_rows = _read_concepts_csv(tmp_path / "concepts.csv")
    for row in concept_rows:
        int(row["id"])
    rows_by_id = {row["id"]: row["concept_en"] for row in concept_rows}
    assert rows_by_id == {"2": "forehead", "225": "nine", "226": "to listen to"}
    assert complete_calls[0][2]["message"] == "Imported 3 lexemes from cues.csv"
    assert complete_calls[0][1]["lexemesImported"] == 3


def test_audition_concept_resolver_reuses_casefold_labels_and_allocates_stably(tmp_path, monkeypatch) -> None:
    server._install_route_bindings()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "2", "concept_en": "Forehead"},
            {"id": "225", "concept_en": "nine"},
        ],
    )
    rows = _parse_audition_rows(
        [
            {"Name": "(1.2)- forehead", "Start": "0", "Duration": "1"},
            {"Name": "9- NINE", "Start": "1", "Duration": "1"},
            {"Name": "(8.4)- to listen to", "Start": "2", "Duration": "1"},
            {"Name": "(8.5)- TO LISTEN TO", "Start": "3", "Duration": "1"},
        ]
    )

    resolved = media._resolve_audition_concepts(rows)

    assert resolved == [
        {"id": "2", "label": "forehead", "audition_prefix": "1.2"},
        {"id": "225", "label": "NINE", "audition_prefix": "9"},
        {"id": "226", "label": "to listen to", "audition_prefix": "8.4"},
        {"id": "226", "label": "TO LISTEN TO", "audition_prefix": "8.5"},
    ]

    media._merge_concepts_into_root_csv(resolved)
    assert media._resolve_audition_concepts(rows) == resolved


def test_onboard_audition_import_index_tracks_shuffled_physical_csv_order(tmp_path, monkeypatch) -> None:
    server._install_route_bindings()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _stub_job(monkeypatch)
    _write_concepts_csv(
        tmp_path / "concepts.csv",
        [
            {"id": "2", "concept_en": "forehead"},
            {"id": "225", "concept_en": "nine"},
        ],
    )

    wav_dest = _make_wav(tmp_path, "ShuffleTest")
    csv_dest = wav_dest.parent / "cues.csv"
    _write_audition_csv(
        csv_dest,
        [
            {"Name": "(8.4)- to listen to", "Start": "2", "Duration": "1"},
            {"Name": "(1.2)- forehead", "Start": "0", "Duration": "1"},
            {"Name": "9- nine", "Start": "1", "Duration": "1"},
        ],
    )

    server._run_onboard_speaker_job("job-shuffle", "ShuffleTest", wav_dest, csv_dest)

    annotation = json.loads((tmp_path / "annotations" / "ShuffleTest.parse.json").read_text(encoding="utf-8"))
    concept_intervals = annotation["tiers"]["concept"]["intervals"]
    assert [interval["text"] for interval in concept_intervals] == ["to listen to", "forehead", "nine"]
    assert [interval["import_index"] for interval in concept_intervals] == [0, 1, 2]
    assert [interval["audition_prefix"] for interval in concept_intervals] == ["8.4", "1.2", "9"]
    assert [interval["concept_id"] for interval in concept_intervals] == ["226", "2", "225"]


def test_append_audition_rows_preserves_existing_source_audio_duration(tmp_path, monkeypatch) -> None:
    server._install_route_bindings()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _write_concepts_csv(tmp_path / "concepts.csv", [{"id": "10", "concept_en": "ash"}])
    rows = _parse_audition_rows([
        {"Name": "10- ash", "Start": "20", "Duration": "5"},
    ])
    resolved = media._resolve_audition_concepts(rows)
    annotation = server._annotation_empty_record("DurationTest", "audio/original/DurationTest/source.wav", 12.0, None)

    media._append_audition_rows_to_annotation(annotation, rows, resolved)

    assert annotation["source_audio_duration_sec"] == 12.0


def test_looks_like_audition_csv_logs_detection_failures(capsys) -> None:
    class BrokenCsvPath:
        def read_text(self, *args, **kwargs):
            raise OSError("cannot read")

        def __str__(self) -> str:
            return "/broken/cues.csv"

    assert media._looks_like_audition_csv(BrokenCsvPath()) is False
    captured = capsys.readouterr()
    assert "[audition-csv] detection failed for /broken/cues.csv:" in captured.err


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
