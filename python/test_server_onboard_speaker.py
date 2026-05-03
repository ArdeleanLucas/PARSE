"""Tests for _run_onboard_speaker_job concepts.csv / project.json updates."""
import csv
import email
import io
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
from server_routes import media


class _OnboardHandlerHarness(server.RangeRequestHandler):
    def __init__(self, *, body: bytes, boundary: str):
        self.path = "/api/onboard/speaker"
        self.headers = email.message_from_string(
            f"Content-Type: multipart/form-data; boundary={boundary}\n"
            f"Content-Length: {len(body)}\n\n"
        )
        self.rfile = io.BytesIO(body)
        self.sent_json = []

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))


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


def _make_onboard_multipart(
    *,
    speaker_id: str = "Http01",
    include_audio: bool = True,
    cue_csv: str | None = None,
    comments_csv: str | None = None,
) -> tuple[bytes, str]:
    boundary = "----parseonboardboundary"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(
            (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )

    def add_file(name: str, filename: str, payload: bytes, content_type: str) -> None:
        parts.append(
            (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
            + payload
            + b"\r\n"
        )

    add_field("speaker_id", speaker_id)
    if include_audio:
        add_file("audio", "source.wav", b"RIFF0000WAVEfmt ", "audio/wav")
    if cue_csv is not None:
        add_file("csv", "cue.csv", cue_csv.encode("utf-8"), "text/csv")
    if comments_csv is not None:
        add_file("commentsCsv", "comments.csv", comments_csv.encode("utf-8"), "text/csv")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), boundary


class _FakeThread:
    calls: list[tuple] = []

    def __init__(self, *, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False
        type(self).calls.append((target, args, daemon, self))

    def start(self) -> None:
        self.started = True


def _stub_onboard_http(monkeypatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    job_payloads = []
    monkeypatch.setattr(server, "_create_job", lambda job_type, payload: job_payloads.append((job_type, payload)) or "job-http")
    _FakeThread.calls = []
    monkeypatch.setattr(server.threading, "Thread", _FakeThread)
    return job_payloads


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


def test_api_post_onboard_speaker_accepts_optional_comments_csv(tmp_path, monkeypatch) -> None:
    job_payloads = _stub_onboard_http(monkeypatch, tmp_path)
    cue_csv = "Name\tStart\tDuration\tTime Format\tType\tDescription\n9- nine\t0\t1\tdecimal\tCue\t\n"
    comments_csv = "Name\tStart\tDuration\tTime Format\tType\tDescription\n9- nine analyst note\t0\t1\tdecimal\tCue\t\n"
    body, boundary = _make_onboard_multipart(cue_csv=cue_csv, comments_csv=comments_csv)
    handler = _OnboardHandlerHarness(body=body, boundary=boundary)

    handler._api_post_onboard_speaker()

    speaker_dir = tmp_path / "audio" / "original" / "Http01"
    assert (speaker_dir / "source.wav").read_bytes() == b"RIFF0000WAVEfmt "
    assert (speaker_dir / "cue.csv").read_text(encoding="utf-8") == cue_csv
    comments_path = speaker_dir / "cue.comments.csv"
    assert comments_path.read_text(encoding="utf-8") == comments_csv
    assert handler.sent_json == [(HTTPStatus.OK, {"job_id": "job-http", "jobId": "job-http", "status": "running", "speaker": "Http01"})]
    assert job_payloads == [
        (
            "onboard:speaker",
            {
                "speaker": "Http01",
                "wavPath": "audio/original/Http01/source.wav",
                "csvPath": "audio/original/Http01/cue.csv",
                "commentsCsvPath": "audio/original/Http01/cue.comments.csv",
            },
        )
    ]
    assert _FakeThread.calls[0][1] == ("job-http", "Http01", speaker_dir / "source.wav", speaker_dir / "cue.csv", comments_path)
    assert _FakeThread.calls[0][3].started is True


def test_api_post_onboard_speaker_preserves_cue_only_upload(tmp_path, monkeypatch) -> None:
    _stub_onboard_http(monkeypatch, tmp_path)
    cue_csv = "Name\tStart\tDuration\tTime Format\tType\tDescription\n9- nine\t0\t1\tdecimal\tCue\t\n"
    body, boundary = _make_onboard_multipart(cue_csv=cue_csv)
    handler = _OnboardHandlerHarness(body=body, boundary=boundary)

    handler._api_post_onboard_speaker()

    speaker_dir = tmp_path / "audio" / "original" / "Http01"
    assert (speaker_dir / "cue.csv").exists()
    assert _FakeThread.calls[0][1] == ("job-http", "Http01", speaker_dir / "source.wav", speaker_dir / "cue.csv", None)


def test_api_post_onboard_speaker_rejects_comments_without_cue(tmp_path, monkeypatch) -> None:
    job_payloads = _stub_onboard_http(monkeypatch, tmp_path)
    comments_csv = "Name\tStart\tDuration\tTime Format\tType\tDescription\n9- nine note\t0\t1\tdecimal\tCue\t\n"
    body, boundary = _make_onboard_multipart(comments_csv=comments_csv)
    handler = _OnboardHandlerHarness(body=body, boundary=boundary)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_onboard_speaker()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert "commentsCsv requires csv" in exc_info.value.message
    assert job_payloads == []
    assert _FakeThread.calls == []


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
        {"id": "1", "concept_en": "ash", "source_item": "", "source_survey": "", "custom_order": ""},
        {"id": "2", "concept_en": "bark", "source_item": "", "source_survey": "", "custom_order": ""},
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
    rows_by_id = {row["id"]: row for row in concept_rows}
    assert {cid: row["concept_en"] for cid, row in rows_by_id.items()} == {"2": "forehead", "225": "nine", "226": "to listen to"}
    assert rows_by_id["2"]["source_item"] == "1.2"
    assert rows_by_id["2"]["source_survey"] == "KLQ"
    assert rows_by_id["225"]["source_item"] == "9"
    assert rows_by_id["225"]["source_survey"] == "JBIL"
    assert rows_by_id["226"]["source_item"] == "8.4"
    assert rows_by_id["226"]["source_survey"] == "KLQ"
    assert complete_calls[0][2]["message"] == "Imported 3 lexemes from cues.csv"
    assert complete_calls[0][1]["lexemesImported"] == 3


def test_onboard_audition_csv_imports_bracket_and_bare_rows_without_drops(tmp_path, monkeypatch) -> None:
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

    wav_dest = _make_wav(tmp_path, "NoDropTest")
    csv_dest = wav_dest.parent / "cues.csv"
    cue_rows = [
        {"Name": "[5.1]- The boy cut the rope with a knife !", "Start": "1", "Duration": "0.5"},
        {"Name": "He saw me", "Start": "2", "Duration": "0.5"},
        {"Name": "(2.29- child of one's son)-", "Start": "3", "Duration": "0.5"},
    ]
    _write_audition_csv(csv_dest, cue_rows)

    server._run_onboard_speaker_job("job-no-drop", "NoDropTest", wav_dest, csv_dest)

    annotation = json.loads((tmp_path / "annotations" / "NoDropTest.parse.json").read_text(encoding="utf-8"))
    concept_intervals = annotation["tiers"]["concept"]["intervals"]
    assert len(concept_intervals) == len(cue_rows)
    assert [interval["text"] for interval in concept_intervals] == [
        "The boy cut the rope with a knife !",
        "He saw me",
        "(2.29- child of one's son)-",
    ]
    assert [interval["concept_id"] for interval in concept_intervals] == ["1", "2", "3"]
    assert [interval["import_index"] for interval in concept_intervals] == [0, 1, 2]
    assert [interval["audition_prefix"] for interval in concept_intervals] == ["5.1", "row_1", "row_2"]

    concept_rows = _read_concepts_csv(tmp_path / "concepts.csv")
    for row in concept_rows:
        int(row["id"])
    assert {row["id"]: row["concept_en"] for row in concept_rows} == {
        "1": "The boy cut the rope with a knife !",
        "2": "He saw me",
        "3": "(2.29- child of one's son)-",
    }
    rows_by_id = {row["id"]: row for row in concept_rows}
    assert rows_by_id["1"]["source_item"] == "5.1"
    assert rows_by_id["1"]["source_survey"] == "EXT"
    assert rows_by_id["2"]["source_item"] == ""
    assert rows_by_id["2"]["source_survey"] == ""
    assert rows_by_id["3"]["source_item"] == ""
    assert rows_by_id["3"]["source_survey"] == ""
    assert complete_calls[0][2]["message"] == "Imported 3 lexemes from cues.csv"
    assert complete_calls[0][1]["lexemesImported"] == 3


def test_onboard_audition_comments_csv_writes_import_notes_by_row_index(tmp_path, monkeypatch) -> None:
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
            {"id": "225", "concept_en": "nine"},
            {"id": "226", "concept_en": "to listen to"},
        ],
    )

    wav_dest = _make_wav(tmp_path, "SahaComments")
    csv_dest = wav_dest.parent / "cues.csv"
    comments_dest = wav_dest.parent / "cues.comments.csv"
    cue_rows = [
        {"Name": "9- nine", "Start": "20:12.776", "Duration": "0:00.967"},
        {"Name": "(8.4)- to listen to", "Start": "2:48:11.681", "Duration": "0:00.993"},
        {"Name": "32- hair B", "Start": "26:13.370", "Duration": "0:00.629"},
    ]
    _write_audition_csv(csv_dest, cue_rows)
    _write_audition_csv(
        comments_dest,
        [
            cue_rows[0],
            {"Name": "(8.4)- to listen to - produced with reduced vowel", "Start": "2:48:11.681", "Duration": "0:00.993"},
            {"Name": "32- hair B \"another way of pronuncing\"", "Start": "26:13.370", "Duration": "0:00.629"},
        ],
    )

    server._run_onboard_speaker_job("job-comments", "SahaComments", wav_dest, csv_dest, comments_dest)

    annotation = json.loads((tmp_path / "annotations" / "SahaComments.parse.json").read_text(encoding="utf-8"))
    concept_intervals = annotation["tiers"]["concept"]["intervals"]
    assert len(concept_intervals) == len(cue_rows)
    assert [interval["import_index"] for interval in concept_intervals] == [0, 1, 2]
    assert [interval["audition_prefix"] for interval in concept_intervals] == ["9", "8.4", "32"]

    enrichments = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))
    notes = enrichments["lexeme_notes"]["SahaComments"]
    assert set(notes) == {"226", "227"}
    assert notes["226"]["import_note"] == "produced with reduced vowel"
    assert notes["226"]["import_raw"] == "(8.4)- to listen to - produced with reduced vowel"
    assert notes["226"]["import_index"] == 1
    assert notes["226"]["audition_prefix"] == "8.4"
    assert notes["227"]["import_note"] == '"another way of pronuncing"'
    assert notes["227"]["import_raw"] == '32- hair B "another way of pronuncing"'
    assert notes["227"]["import_index"] == 2
    assert notes["227"]["audition_prefix"] == "32"
    assert complete_calls[0][1]["commentsImported"] == 2


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
        {"id": "2", "label": "forehead", "audition_prefix": "1.2", "source_item": "1.2", "source_survey": "KLQ"},
        {"id": "225", "label": "NINE", "audition_prefix": "9", "source_item": "9", "source_survey": "JBIL"},
        {"id": "226", "label": "to listen to", "audition_prefix": "8.4", "source_item": "8.4", "source_survey": "KLQ"},
        {"id": "226", "label": "TO LISTEN TO", "audition_prefix": "8.5", "source_item": "8.5", "source_survey": "KLQ"},
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
    assert rows == [{"id": "1", "concept_en": "ash", "source_item": "", "source_survey": "", "custom_order": ""}]

    project = json.loads((tmp_path / "project.json").read_text())
    assert list(project["speakers"].keys()) == ["Fail02"]

    source_index = json.loads((tmp_path / "source_index.json").read_text())
    wav_entries = source_index["speakers"]["Fail02"]["source_wavs"]
    assert len(wav_entries) == 1
