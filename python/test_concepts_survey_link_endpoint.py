"""Tests for POST/DELETE /api/concepts/{conceptId}/survey-links."""

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
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})


def _seed_overlap(tmp_path: pathlib.Path, payload: dict) -> None:
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_overlap(tmp_path: pathlib.Path) -> dict:
    path = tmp_path / "survey-overlap.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def _post(handler_method: str, body: dict, concept_id: str = "1") -> _Handler:
    raw = json.dumps(body).encode("utf-8")
    handler = _Handler(raw)
    method = getattr(handler, handler_method)
    method(concept_id)
    return handler


def _dispatch(method: str, path: str, body: dict) -> _Handler:
    raw = json.dumps(body).encode("utf-8")
    handler = _Handler(raw, path=path)
    server._install_route_bindings()
    assert handler._handle_api(method) is True
    return handler


def test_post_survey_link_persists_sidecar_and_returns_concept_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "nose", "source_item": "1.5", "source_survey": "klq"}],
    )

    body = json.dumps({"survey_id": "jbil", "source_item": "34"}).encode("utf-8")
    handler = _Handler(body)
    handler._api_post_concept_survey_link("1")

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["id"] == "1"
    assert payload["surveys"]["jbil"] == "34"
    assert payload["surveys"]["klq"] == "1.5"
    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"]["1"]["jbil"] == "34"


def test_survey_link_dispatcher_preserves_comma_separated_speaker_path(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    path = "/api/concepts/53,619/survey-links"
    _seed_concepts(
        tmp_path,
        [
            {"id": "53", "concept_en": "ashes", "source_item": "53", "source_survey": "KLQ"},
            {"id": "619", "concept_en": "ashes (B)", "source_item": "169", "source_survey": "JBIL"},
        ],
    )

    missing_speaker = _dispatch("POST", path, {"survey_id": "jbil", "source_item": "169"})
    assert missing_speaker.status == HTTPStatus.BAD_REQUEST

    post_handler = _dispatch(
        "POST",
        path,
        {"survey_id": "jbil", "source_item": "169", "speaker": "Saha01"},
    )

    assert post_handler.status == HTTPStatus.OK
    overlap = _read_overlap(tmp_path)
    assert overlap["speaker_concept_survey_links"] == {
        "Saha01": {"53": {"jbil": "169"}, "619": {"jbil": "169"}}
    }

    delete_handler = _dispatch("DELETE", path, {"survey_id": "jbil", "speaker": "Saha01"})

    assert delete_handler.status == HTTPStatus.OK
    assert _read_overlap(tmp_path).get("speaker_concept_survey_links", {}) == {}


def test_post_survey_link_normalizes_survey_id_and_trims_source_item(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])

    body = json.dumps({"survey_id": "  JBIL  ", "source_item": "  34  "}).encode("utf-8")
    handler = _Handler(body)
    handler._api_post_concept_survey_link("1")

    assert handler.status == HTTPStatus.OK
    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"]["1"]["jbil"] == "34"


def test_post_survey_link_400_on_empty_source_item(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])

    body = json.dumps({"survey_id": "jbil", "source_item": "  "}).encode("utf-8")
    handler = _Handler(body)
    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_concept_survey_link("1")
    assert exc_info.value.status == HTTPStatus.BAD_REQUEST


def test_post_survey_link_400_on_empty_survey_id(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])

    body = json.dumps({"survey_id": "", "source_item": "34"}).encode("utf-8")
    handler = _Handler(body)
    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_concept_survey_link("1")
    assert exc_info.value.status == HTTPStatus.BAD_REQUEST


def test_post_survey_link_404_when_concept_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])

    body = json.dumps({"survey_id": "jbil", "source_item": "34"}).encode("utf-8")
    handler = _Handler(body)
    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_concept_survey_link("99")
    assert exc_info.value.status == HTTPStatus.NOT_FOUND


def test_delete_survey_link_removes_only_matching_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "1.5", "jbil": "34"}},
            "speaker_choices": {},
        },
    )

    body = json.dumps({"survey_id": "jbil", "source_item": "34"}).encode("utf-8")
    handler = _Handler(body)
    handler._api_delete_concept_survey_link("1")

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["surveys"] == {"klq": "1.5"}
    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"]["1"] == {"klq": "1.5"}


def test_delete_survey_link_optimistic_guard_returns_409_on_mismatch(tmp_path, monkeypatch):
    """When source_item is provided but does not match the stored value the call must 409."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"jbil": "34"}},
            "speaker_choices": {},
        },
    )

    body = json.dumps({"survey_id": "jbil", "source_item": "999"}).encode("utf-8")
    handler = _Handler(body)
    with pytest.raises(server.ApiError) as exc_info:
        handler._api_delete_concept_survey_link("1")
    assert exc_info.value.status == HTTPStatus.CONFLICT
    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"]["1"]["jbil"] == "34"


def test_delete_survey_link_without_source_item_removes_by_survey_id(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"klq": "1.5", "jbil": "34"}},
            "speaker_choices": {},
        },
    )

    body = json.dumps({"survey_id": "jbil"}).encode("utf-8")
    handler = _Handler(body)
    handler._api_delete_concept_survey_link("1")

    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"]["1"] == {"klq": "1.5"}


def test_delete_survey_link_404_when_concept_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "nose"}])

    body = json.dumps({"survey_id": "jbil", "source_item": "34"}).encode("utf-8")
    handler = _Handler(body)
    with pytest.raises(server.ApiError) as exc_info:
        handler._api_delete_concept_survey_link("99")
    assert exc_info.value.status == HTTPStatus.NOT_FOUND


def test_delete_survey_link_409_when_legacy_link_targeted(tmp_path, monkeypatch):
    """Legacy source_item/source_survey on concepts.csv cannot be removed via this endpoint."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [{"id": "1", "concept_en": "nose", "source_item": "1.5", "source_survey": "klq"}],
    )

    body = json.dumps({"survey_id": "klq", "source_item": "1.5"}).encode("utf-8")
    handler = _Handler(body)
    with pytest.raises(server.ApiError) as exc_info:
        handler._api_delete_concept_survey_link("1")
    assert exc_info.value.status == HTTPStatus.CONFLICT
