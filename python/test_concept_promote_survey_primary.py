"""Tests for POST /api/concepts/{conceptId}/promote-survey-primary."""

from __future__ import annotations

import csv
import io
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402
from app.http import project_config_handlers as project_config_handlers  # noqa: E402


class _FakeWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def flush(self) -> None:
        pass

    def payload(self) -> dict:
        raw = b"".join(self.chunks).decode("utf-8")
        body = raw.split("\r\n\r\n", 1)[-1]
        return json.loads(body)


class _Handler(server.RangeRequestHandler):
    def __init__(self, body: bytes, content_type: str = "application/json", path: str = "/") -> None:
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.status: int | None = None
        self.sent_headers: dict[str, str] = {}

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.sent_headers[str(key)] = str(value)

    def end_headers(self):
        pass


def _seed_concepts(tmp_path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path = tmp_path / "concepts.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})


def _seed_overlap(tmp_path: pathlib.Path, payload: dict) -> None:
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_overlap(tmp_path: pathlib.Path) -> dict:
    return json.loads((tmp_path / "survey-overlap.json").read_text(encoding="utf-8"))


def _read_concepts(tmp_path: pathlib.Path) -> list[dict[str, str]]:
    with (tmp_path / "concepts.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _post(body: dict, concept_id: str = "1") -> _Handler:
    raw = json.dumps(body).encode("utf-8")
    handler = _Handler(raw)
    server._install_route_bindings()
    handler._api_post_concept_promote_survey_primary(concept_id)
    return handler


def _dispatch(method: str, path: str, body: dict) -> _Handler:
    raw = json.dumps(body).encode("utf-8")
    handler = _Handler(raw, path=path)
    server._install_route_bindings()
    assert handler._handle_api(method) is True
    return handler


def test_promote_survey_primary_moves_target_to_csv_and_old_primary_to_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "head", "source_item": "72", "source_survey": "JBIL"}],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "2.1"}},
            "speaker_choices": {},
            "speaker_concept_survey_links": {},
        },
    )

    handler = _dispatch(
        "POST",
        "/api/concepts/1/promote-survey-primary",
        {"survey_id": "klq", "source_item": "2.1"},
    )

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["ok"] is True
    assert payload["concept"]["id"] == "1"
    assert payload["concept"]["source_survey"] == "KLQ"
    assert payload["concept"]["source_item"] == "2.1"
    assert payload["concept"]["surveys"] == {"klq": "2.1", "jbil": "72"}

    row = _read_concepts(tmp_path)[0]
    assert row["source_survey"] == "KLQ"
    assert row["source_item"] == "2.1"
    assert _read_overlap(tmp_path)["concept_survey_links"] == {"1": {"jbil": "72"}}
    assert len(list(tmp_path.glob("concepts.csv.bak-*-pre-promote-1"))) == 1


def test_promote_survey_primary_noops_when_pair_is_already_primary(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "head", "source_item": "2.1", "source_survey": "KLQ"}],
    )
    original_overlap = {
        "version": 1,
        "color_coding_enabled": False,
        "surveys": {},
        "concept_survey_links": {"1": {"jbil": "72"}},
        "speaker_choices": {},
        "speaker_concept_survey_links": {},
    }
    _seed_overlap(tmp_path, original_overlap)
    original_csv = (tmp_path / "concepts.csv").read_bytes()

    handler = _post({"survey_id": "klq", "source_item": "2.1"})

    assert handler.status == HTTPStatus.OK
    assert handler.wfile.payload()["concept"]["source_survey"] == "KLQ"
    assert (tmp_path / "concepts.csv").read_bytes() == original_csv
    assert _read_overlap(tmp_path) == original_overlap
    assert list(tmp_path.glob("concepts.csv.bak-*-pre-promote-1")) == []


def test_promote_survey_primary_404_when_concept_id_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "head", "source_item": "72", "source_survey": "JBIL"}],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "2.1"}},
            "speaker_choices": {},
            "speaker_concept_survey_links": {},
        },
    )
    original_csv = (tmp_path / "concepts.csv").read_bytes()

    with pytest.raises(server.ApiError) as exc_info:
        _post({"survey_id": "klq", "source_item": "2.1"}, concept_id="9999")

    assert exc_info.value.status == HTTPStatus.NOT_FOUND
    assert (tmp_path / "concepts.csv").read_bytes() == original_csv
    assert list(tmp_path.glob("concepts.csv.bak-*-pre-promote-*")) == []


def test_promote_survey_primary_400_when_required_fields_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "head", "source_item": "72", "source_survey": "JBIL"}],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "2.1"}},
            "speaker_choices": {},
            "speaker_concept_survey_links": {},
        },
    )

    with pytest.raises(server.ApiError) as missing_survey:
        _post({"survey_id": "", "source_item": "2.1"})
    assert missing_survey.value.status == HTTPStatus.BAD_REQUEST
    assert list(tmp_path.glob("concepts.csv.bak-*-pre-promote-*")) == []

    with pytest.raises(server.ApiError) as missing_source_item:
        _post({"survey_id": "klq", "source_item": ""})
    assert missing_source_item.value.status == HTTPStatus.BAD_REQUEST
    assert list(tmp_path.glob("concepts.csv.bak-*-pre-promote-*")) == []


def test_promote_survey_primary_preserves_other_sidecar_links(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "head", "source_item": "72", "source_survey": "JBIL"}],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "2.1", "ext": "9"}},
            "speaker_choices": {},
            "speaker_concept_survey_links": {},
        },
    )

    handler = _post({"survey_id": "klq", "source_item": "2.1"})

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["concept"]["surveys"] == {"klq": "2.1", "jbil": "72", "ext": "9"}
    row = _read_concepts(tmp_path)[0]
    assert row["source_survey"] == "KLQ"
    assert row["source_item"] == "2.1"
    assert _read_overlap(tmp_path)["concept_survey_links"]["1"] == {"jbil": "72", "ext": "9"}
    assert len(list(tmp_path.glob("concepts.csv.bak-*-pre-promote-1"))) == 1


def test_promote_survey_primary_400_when_pair_is_not_primary_or_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "head", "source_item": "72", "source_survey": "JBIL"}],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "2.1"}},
            "speaker_choices": {},
            "speaker_concept_survey_links": {},
        },
    )

    with pytest.raises(server.ApiError) as exc_info:
        _post({"survey_id": "hawrami", "source_item": "99"})

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert _read_concepts(tmp_path)[0]["source_survey"] == "JBIL"
    assert _read_overlap(tmp_path)["concept_survey_links"] == {"1": {"klq": "2.1"}}


def test_promote_survey_primary_leaves_csv_unchanged_when_sidecar_write_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "head", "source_item": "72", "source_survey": "JBIL"}],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "2.1"}},
            "speaker_choices": {},
            "speaker_concept_survey_links": {},
        },
    )
    original_csv = (tmp_path / "concepts.csv").read_bytes()

    def fail_sidecar_write(*_args, **_kwargs):
        raise OSError("sidecar unavailable")

    monkeypatch.setattr(project_config_handlers, "update_survey_overlap_state", fail_sidecar_write)

    with pytest.raises(server.ApiError) as exc_info:
        _post({"survey_id": "klq", "source_item": "2.1"})

    assert exc_info.value.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert (tmp_path / "concepts.csv").read_bytes() == original_csv
