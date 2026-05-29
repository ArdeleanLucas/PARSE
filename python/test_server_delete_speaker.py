"""Tests for DELETE /api/speakers/{speaker}."""

from __future__ import annotations

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


def _write_json(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_workspace(root: pathlib.Path, speaker: str = "Saha01") -> None:
    _write_json(root / "annotations" / "{0}.parse.json".format(speaker), {"speaker": speaker})
    (root / "audio" / "original" / speaker).mkdir(parents=True, exist_ok=True)
    (root / "audio" / "original" / speaker / "source.wav").write_bytes(b"RIFF")
    _write_json(root / "peaks" / "{0}.json".format(speaker), {"peaks": []})
    _write_json(root / "project.json", {"speakers": {speaker: {}, "Other01": {}}})
    _write_json(root / "source_index.json", {"speakers": {speaker: {"source_wavs": []}}})


def _delete_speaker(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, speaker: str) -> tuple[int, dict]:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setenv("PARSE_LOCKS_DIR", str(tmp_path / ".parse-locks"))
    server._install_route_bindings()
    handler = _FakeHandler("/api/speakers/{0}".format(speaker))
    assert handler._handle_api("DELETE") is True
    assert handler.status is not None
    return int(handler.status), handler.wfile.payload()


def test_delete_speaker_moves_to_trash_and_prunes(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server._jobs.clear()
    _make_workspace(tmp_path)

    status, payload = _delete_speaker(tmp_path, monkeypatch, "Saha01")

    assert status == HTTPStatus.OK
    assert payload["ok"] is True
    assert payload["speaker"] == "Saha01"
    assert not (tmp_path / "annotations" / "Saha01.parse.json").exists()
    assert not (tmp_path / "audio" / "original" / "Saha01").exists()
    trash_dir = tmp_path / payload["trashDir"]
    assert (trash_dir / "annotations" / "Saha01.parse.json").exists()
    project = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert "Saha01" not in project["speakers"]
    assert "Other01" in project["speakers"]


def test_delete_unknown_speaker_returns_404(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server._jobs.clear()
    _make_workspace(tmp_path)

    status, payload = _delete_speaker(tmp_path, monkeypatch, "Ghost42")

    assert status == HTTPStatus.NOT_FOUND
    assert "error" in payload


def test_delete_blocked_by_active_job_returns_409(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server._jobs.clear()
    _make_workspace(tmp_path)
    server._jobs["job-1"] = {
        "jobId": "job-1",
        "type": "normalize",
        "status": "running",
        "locks": {
            "active": True,
            "expires_ts": 0,
            "resources": [{"kind": "speaker", "id": "Saha01"}],
        },
    }
    try:
        status, payload = _delete_speaker(tmp_path, monkeypatch, "Saha01")
    finally:
        server._jobs.clear()

    assert status == HTTPStatus.CONFLICT
    assert payload["error"]
    assert payload["holder"]["jobId"] == "job-1"
    # Nothing deleted while blocked.
    assert (tmp_path / "annotations" / "Saha01.parse.json").exists()
