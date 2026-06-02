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

FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


class _FakeWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def payload(self) -> dict:
        raw = b"".join(self.chunks).decode("utf-8")
        body = raw.split("\r\n\r\n", 1)[-1]
        return json.loads(body)


class _Handler(server.RangeRequestHandler):
    def __init__(self, body: bytes = b"", path: str = "/api/concept-identity") -> None:
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        self.status: int | None = None
        self.sent_headers: dict[str, str] = {}

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, key, value):  # type: ignore[no-untyped-def]
        self.sent_headers[str(key)] = str(value)

    def end_headers(self) -> None:
        pass


def _seed_concepts(root: pathlib.Path) -> None:
    rows = [
        {"id": "52", "concept_en": "salt", "source_item": "3.14", "source_survey": "KLQ"},
        {"id": "352", "concept_en": "salt (eating)", "source_item": "139", "source_survey": "JBIL"},
    ]
    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})
    (root / "survey-overlap.json").write_text(
        json.dumps({"concept_survey_links": {"52": {"jbil": "139"}}}),
        encoding="utf-8",
    )


def test_get_concept_identity_route_returns_frozen_contract(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    handler = _Handler()

    handler._api_get_concept_identity()

    payload = handler.wfile.payload()
    assert handler.status == HTTPStatus.OK
    assert payload["version"] == 1
    assert payload["concepts"][0] == {"uid": "c-52", "label": "salt", "members": ["52", "352"], "origin": "auto"}
    assert payload["uid_by_row"] == {"52": "c-52", "352": "c-52"}
    assert payload["warnings"] == []


def test_get_concept_identity_dispatcher(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    server._install_route_bindings()
    handler = _Handler()

    assert handler._handle_api("GET") is True

    assert handler.status == HTTPStatus.OK
    assert handler.wfile.payload()["uid_by_row"]["52"] == "c-52"


def test_get_enrichments_route_promotes_legacy_keys_to_uid(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps({"cognate_decisions": {"52": {"decision": "accepted"}}}),
        encoding="utf-8",
    )
    handler = _Handler(path="/api/enrichments")

    handler._api_get_enrichments()

    payload = handler.wfile.payload()["enrichments"]
    assert handler.status == HTTPStatus.OK
    assert payload["cognate_decisions"] == {"c-52": {"decision": "accepted"}}


def _post(body: dict) -> _Handler:
    encoded = json.dumps(body).encode("utf-8")
    handler = _Handler(encoded)
    handler._api_post_concept_identity()
    return handler


def test_post_concept_identity_writes_manual_override_and_round_trips(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)

    handler = _post(
        {
            "uid": "c-salt-manual",
            "label": "salt reviewed",
            "members": ["52", "352"],
            "origin": "manual:merge",
        }
    )

    payload = handler.wfile.payload()
    assert handler.status == HTTPStatus.OK
    assert payload["uid_by_row"] == {"52": "c-salt-manual", "352": "c-salt-manual"}
    written = json.loads((tmp_path / "concept-identity.json").read_text(encoding="utf-8"))
    assert written == {
        "version": 1,
        "concepts": [
            {
                "uid": "c-salt-manual",
                "label": "salt reviewed",
                "members": ["52", "352"],
                "origin": "manual:merge",
            }
        ],
    }


def test_post_concept_identity_rejects_invalid_origin_and_member(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)

    with pytest.raises(server.ApiError) as origin_error:
        _post({"members": ["52"], "origin": "auto"})
    assert origin_error.value.status == HTTPStatus.BAD_REQUEST

    with pytest.raises(server.ApiError) as member_error:
        _post({"members": ["999"], "origin": "manual:split"})
    assert member_error.value.status == HTTPStatus.BAD_REQUEST
    assert not (tmp_path / "concept-identity.json").exists()


def test_post_concept_identity_dispatcher(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    server._install_route_bindings()
    body = json.dumps({"members": ["52"], "origin": "manual:split"}).encode("utf-8")
    handler = _Handler(body)

    assert handler._handle_api("POST") is True

    assert handler.status == HTTPStatus.OK
    assert handler.wfile.payload()["uid_by_row"]["52"] == "c-52"
