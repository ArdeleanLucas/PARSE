from __future__ import annotations

import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server


class _Buffer:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, path: str) -> None:
        self.path = path
        self.headers = {}
        self.wfile = _Buffer()
        self.status: HTTPStatus | None = None
        self.response_headers: list[tuple[str, str]] = []

    def send_response(self, status: HTTPStatus) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        pass


def test_handle_api_bare_exception_returns_class_name_and_logs_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    handler = _HandlerHarness("/api/bare-error")
    monkeypatch.setattr(server, "_cleanup_old_jobs", lambda: None)
    monkeypatch.setattr(server, "_cleanup_old_chat_sessions", lambda: None)

    def raise_bare_exception(_request_path: str) -> None:
        raise RuntimeError()

    handler._dispatch_api_get = raise_bare_exception  # type: ignore[method-assign]

    assert handler._handle_api("GET") is True

    assert handler.status == HTTPStatus.INTERNAL_SERVER_ERROR
    body = json.loads(bytes(handler.wfile.data).decode("utf-8"))
    assert set(body) == {"error"}
    assert "RuntimeError" in body["error"]
    assert "()" in body["error"]
    assert body["error"].strip()

    stderr = capsys.readouterr().err
    assert "Traceback (most recent call last)" in stderr
    assert "RuntimeError" in stderr
