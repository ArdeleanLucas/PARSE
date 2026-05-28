"""Regression tests proving the duplicate-concept route is removed."""

from __future__ import annotations

import io
import json
import pathlib
import sys
from http import HTTPStatus
from typing import cast

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import concepts_io
import server


class _FakeWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def payload(self) -> dict:
        return json.loads(b"".join(self.chunks).decode("utf-8"))


class _FakeHandler(server.RangeRequestHandler):
    def __init__(self, path: str) -> None:
        self.path = path
        self.rfile = io.BytesIO(b"")
        self.wfile = _FakeWfile()
        self.headers = {"Host": "127.0.0.1:8766", "Content-Length": "0"}
        self.status: HTTPStatus | None = None
        self.sent_headers: dict[str, str] = {}

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, key, value):  # type: ignore[no-untyped-def]
        self.sent_headers[str(key)] = str(value)

    def end_headers(self) -> None:
        pass


def test_duplicate_concept_variant_is_removed() -> None:
    assert not hasattr(
        concepts_io,
        "duplicate_concept_variant",
    ), "duplicate_concept_variant should have been removed per MC-418-E"


def test_source_item_variant_suffixes_is_removed() -> None:
    assert not hasattr(
        concepts_io,
        "_source_item_variant_suffixes",
    ), "_source_item_variant_suffixes should have been removed per MC-418-E"


def _assert_route_404(path: str, tmp_path: pathlib.Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    server._install_route_bindings()
    handler = _FakeHandler(path)

    assert handler._handle_api("POST") is True

    assert int(handler.status or 0) == HTTPStatus.NOT_FOUND
    assert cast(_FakeWfile, handler.wfile).payload() == {"error": "Unknown API endpoint"}


def test_concepts_duplicate_route_returns_404(tmp_path: pathlib.Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _assert_route_404("/api/concepts/322/duplicate", tmp_path, monkeypatch)


def test_bare_concepts_duplicate_route_returns_404(tmp_path: pathlib.Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _assert_route_404("/api/concepts/duplicate", tmp_path, monkeypatch)
