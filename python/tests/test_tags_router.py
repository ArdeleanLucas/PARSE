from __future__ import annotations

import json
import pathlib
import sys
from http import HTTPStatus
from typing import Any

import pytest

PYTHON_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import server
from storage import tags_store


def _tag(
    tag_id: str = "tag_archaic",
    label: str = "archaic",
    color: str = "#3554B8",
    concepts: list[str] | None = None,
    lexeme_targets: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": tag_id,
        "label": label,
        "color": color,
        "concepts": [] if concepts is None else concepts,
        "lexemeTargets": [] if lexeme_targets is None else lexeme_targets,
    }


@pytest.fixture(autouse=True)
def isolated_tags_path(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "tags.json"
    monkeypatch.setenv("PARSE_TAGS_PATH", str(path))
    return path


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, path: str, body: Any | None = None) -> None:
        self.path = path
        self._body = {} if body is None else body
        self.sent_json: list[tuple[HTTPStatus, dict[str, Any]]] = []
        self.sent_errors: list[tuple[HTTPStatus, str]] = []
        self.response_codes: list[HTTPStatus] = []
        self.headers_sent: list[tuple[str, str]] = []
        self.ended = 0

    def _read_json_body(self, required: bool = True) -> Any:
        return self._body

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self.sent_json.append((status, payload))

    def _send_json_error(self, status: HTTPStatus, message: str) -> None:
        self.sent_errors.append((status, message))

    def send_response(self, code: HTTPStatus) -> None:
        self.response_codes.append(code)

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent.append((key, value))

    def end_headers(self) -> None:
        self.ended += 1


def test_get_tags_returns_empty_old_shape() -> None:
    handler = _HandlerHarness("/api/tags")

    assert handler._handle_api("GET") is True

    assert handler.sent_json == [(HTTPStatus.OK, {"tags": []})]
    assert handler.sent_errors == []


def test_put_tags_replaces_full_list_and_echoes_validated_old_shape() -> None:
    tag = _tag(concepts=["water"], lexeme_targets=["Saha01::sister"])
    handler = _HandlerHarness("/api/tags", {"tags": [tag]})

    assert handler._handle_api("PUT") is True

    assert handler.sent_json == [(HTTPStatus.OK, {"tags": [tag]})]
    assert tags_store.fetch_all() == {"version": 2, "tags": [tag]}


def test_put_tags_is_idempotent() -> None:
    payload = {"tags": [_tag(), _tag("tag_uncertain", "uncertain", "#aabbcc")]}

    first = _HandlerHarness("/api/tags", payload)
    second = _HandlerHarness("/api/tags", payload)
    assert first._handle_api("PUT") is True
    assert second._handle_api("PUT") is True

    assert first.sent_json == second.sent_json == [(HTTPStatus.OK, payload)]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"tags": "not-a-list"},
        {"tags": [{"id": "tag_bad", "label": "bad", "color": "blue", "concepts": [], "lexemeTargets": []}]},
        {"tags": [_tag("tag_same", "one"), _tag("tag_same", "two")]},
        {"tags": [_tag("tag_one", "archaic"), _tag("tag_two", "ARCHAIC")]},
        {"tags": [{"id": "tag_bad", "label": "bad", "color": "#3554B8", "concepts": [], "lexemeTargets": ["bad"]}]},
    ],
)
def test_put_tags_rejects_schema_violations(body: dict[str, Any]) -> None:
    handler = _HandlerHarness("/api/tags", body)

    assert handler._handle_api("PUT") is True

    assert handler.sent_json == []
    assert handler.sent_errors
    assert handler.sent_errors[0][0] == HTTPStatus.BAD_REQUEST


def test_post_tags_endpoint_added_by_pr239_is_removed() -> None:
    handler = _HandlerHarness("/api/tags", {"name": "archaic", "color": "#3554B8"})

    assert handler._handle_api("POST") is True

    assert handler.sent_json == []
    assert handler.sent_errors == [(HTTPStatus.NOT_FOUND, "Unknown API endpoint")]
    assert tags_store.fetch_all() == {"version": 2, "tags": []}


@pytest.mark.parametrize(
    "method,path",
    [
        ("DELETE", "/api/tags/tag_archaic"),
        ("POST", "/api/concepts/water/tags/tag_archaic"),
        ("DELETE", "/api/concepts/water/tags/tag_archaic"),
    ],
)
def test_per_tag_and_per_concept_attachment_endpoints_added_by_pr239_are_removed(method: str, path: str) -> None:
    handler = _HandlerHarness(path)

    assert handler._handle_api(method) is True

    assert handler.sent_json == []
    assert handler.sent_errors == [(HTTPStatus.NOT_FOUND, "Unknown API endpoint")]


def test_get_tags_loads_migrated_v1_file_without_attachments_key(isolated_tags_path: pathlib.Path) -> None:
    isolated_tags_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tags": [{"id": "tag_archaic", "name": "archaic", "color": "#3554B8", "createdAt": "2026-05-01T00:00:00Z"}],
                "attachments": {"water": ["tag_archaic"]},
            }
        ),
        encoding="utf-8",
    )
    handler = _HandlerHarness("/api/tags")

    assert handler._handle_api("GET") is True

    assert handler.sent_json == [(HTTPStatus.OK, {"tags": [_tag(concepts=["water"])]})]
