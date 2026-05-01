from __future__ import annotations

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


def test_get_tags_returns_empty_store() -> None:
    handler = _HandlerHarness("/api/tags")

    assert handler._handle_api("GET") is True

    assert handler.sent_json == [(HTTPStatus.OK, {"tags": [], "attachments": {}})]
    assert handler.sent_errors == []


def test_post_tags_creates_tag_with_201() -> None:
    handler = _HandlerHarness("/api/tags", {"name": "archaic", "color": "#3554B8"})

    assert handler._handle_api("POST") is True

    assert len(handler.sent_json) == 1
    status, payload = handler.sent_json[0]
    assert status == HTTPStatus.CREATED
    assert payload["id"].startswith("tag_")
    assert payload["name"] == "archaic"
    assert payload["color"] == "#3554B8"
    assert tags_store.fetch_all()["tags"] == [payload]


def test_post_tags_returns_409_on_case_insensitive_name_conflict() -> None:
    tags_store.create_tag("archaic", "#3554B8")
    handler = _HandlerHarness("/api/tags", {"name": "ARCHAIC", "color": "#aabbcc"})

    assert handler._handle_api("POST") is True

    assert handler.sent_json == []
    assert handler.sent_errors == [(HTTPStatus.CONFLICT, "Tag 'ARCHAIC' already exists")]


@pytest.mark.parametrize("color", ["#3554B8", "#aabbcc"])
def test_post_tags_accepts_valid_hex_colors(color: str) -> None:
    handler = _HandlerHarness("/api/tags", {"name": f"tag-{color[-2:]}", "color": color})

    assert handler._handle_api("POST") is True

    assert handler.sent_json[0][0] == HTTPStatus.CREATED
    assert handler.sent_json[0][1]["color"] == color
    assert handler.sent_errors == []


@pytest.mark.parametrize("color", ["3554B8", "#3554B", "#3554B88", "#zzzzzz", "blue"])
def test_post_tags_rejects_invalid_hex_colors(color: str) -> None:
    handler = _HandlerHarness("/api/tags", {"name": "bad-color", "color": color})

    assert handler._handle_api("POST") is True

    assert handler.sent_json == []
    assert handler.sent_errors == [(HTTPStatus.BAD_REQUEST, "Tag color must be a six-digit hex color like #3554B8")]


def test_delete_tag_returns_204_and_cascades_attachments() -> None:
    tag = tags_store.create_tag("archaic", "#3554B8")
    other = tags_store.create_tag("uncertain", "#aabbcc")
    tags_store.attach("concept_a", tag["id"])
    tags_store.attach("concept_a", other["id"])
    tags_store.attach("concept_b", tag["id"])
    handler = _HandlerHarness(f"/api/tags/{tag['id']}")

    assert handler._handle_api("DELETE") is True

    assert handler.response_codes == [HTTPStatus.NO_CONTENT]
    assert ("Content-Length", "0") in handler.headers_sent
    assert handler.ended == 1
    assert tags_store.fetch_all()["attachments"] == {"concept_a": [other["id"]]}


def test_delete_tag_returns_204_even_when_tag_missing() -> None:
    handler = _HandlerHarness("/api/tags/tag_does_not_exist")

    assert handler._handle_api("DELETE") is True

    assert handler.response_codes == [HTTPStatus.NO_CONTENT]
    assert ("Content-Length", "0") in handler.headers_sent
    assert handler.ended == 1


def test_post_concept_tag_attach_is_idempotent() -> None:
    tag = tags_store.create_tag("archaic", "#3554B8")
    path = f"/api/concepts/concept_a/tags/{tag['id']}"

    first = _HandlerHarness(path)
    second = _HandlerHarness(path)
    assert first._handle_api("POST") is True
    assert second._handle_api("POST") is True

    assert first.response_codes == [HTTPStatus.NO_CONTENT]
    assert second.response_codes == [HTTPStatus.NO_CONTENT]
    assert tags_store.fetch_all()["attachments"] == {"concept_a": [tag["id"]]}


def test_post_concept_tag_attach_returns_404_for_unknown_tag() -> None:
    handler = _HandlerHarness("/api/concepts/concept_a/tags/tag_does_not_exist")

    assert handler._handle_api("POST") is True

    assert handler.sent_json == []
    assert handler.sent_errors == [(HTTPStatus.NOT_FOUND, "Unknown tag 'tag_does_not_exist'")]


def test_delete_concept_tag_detach_is_idempotent() -> None:
    tag = tags_store.create_tag("archaic", "#3554B8")
    tags_store.attach("concept_a", tag["id"])
    path = f"/api/concepts/concept_a/tags/{tag['id']}"

    first = _HandlerHarness(path)
    second = _HandlerHarness(path)
    assert first._handle_api("DELETE") is True
    assert second._handle_api("DELETE") is True

    assert first.response_codes == [HTTPStatus.NO_CONTENT]
    assert second.response_codes == [HTTPStatus.NO_CONTENT]
    assert tags_store.fetch_all()["attachments"] == {}
