"""Delete one per-concept annotation interval without deleting the concept row."""

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

    def flush(self) -> None:
        pass

    def payload(self) -> dict:
        raw = b"".join(self.chunks).decode("utf-8")
        body = raw.split("\r\n\r\n", 1)[-1]
        return json.loads(body)


class _Handler(server.RangeRequestHandler):
    def __init__(self, body: bytes) -> None:
        self.rfile = io.BytesIO(body)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        self.status: int | None = None

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        pass

    def end_headers(self) -> None:
        pass


def _seed_annotation(root: pathlib.Path) -> pathlib.Path:
    annotations = root / "annotations"
    annotations.mkdir(parents=True, exist_ok=True)
    path = annotations / "Fail01.parse.json"
    record = {
        "speaker": "Fail01",
        "metadata": {"created": "2026-05-28T00:00:00Z", "modified": "2026-05-28T00:00:00Z"},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 1,
                "intervals": [
                    {"start": 700.0, "end": 701.0, "text": "sar", "concept_id": "247"},
                    {"start": 731.934, "end": 732.612, "text": "kapul", "concept_id": "247"},
                    {"start": 731.950, "end": 732.705, "text": "kapul", "concept_id": "247"},
                ],
            },
            "ipa": {"type": "interval", "display_order": 2, "intervals": [
                {"start": 731.934, "end": 732.612, "text": "kapul-ipa"},
                {"start": 731.950, "end": 732.705, "text": "kapul-ipa-duplicate"},
            ]},
            "ortho": {"type": "interval", "display_order": 3, "intervals": [
                {"start": 731.934, "end": 732.612, "text": "kapul-ortho"},
                {"start": 731.950, "end": 732.705, "text": "kapul-ortho-duplicate"},
            ]},
            "ortho_words": {"type": "interval", "display_order": 4, "intervals": [
                {"start": 731.9345, "end": 732.6124, "text": "kapul-word"},
                {"start": 731.950, "end": 732.705, "text": "kapul-word-duplicate"},
            ]},
            "speaker": {"type": "interval", "display_order": 5, "intervals": [
                {"start": 731.934, "end": 732.612, "text": "Fail01"},
                {"start": 731.950, "end": 732.705, "text": "Fail01"},
            ]},
        },
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _post_delete(body: dict) -> _Handler:
    server._install_route_bindings()
    handler = _Handler(json.dumps(body).encode("utf-8"))
    handler._api_post_annotation_interval_delete()
    return handler


def _read(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_delete_annotation_interval_removes_matching_concept_and_mirror_tier_rows(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    annotation_path = _seed_annotation(tmp_path)

    handler = _post_delete({"speaker": "Fail01", "concept_id": "247", "start": 731.934, "end": 732.612})

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["ok"] is True
    assert payload["speaker"] == "Fail01"
    assert payload["concept_id"] == "247"
    assert payload["removed"] == {"concept": 1, "ipa": 1, "ortho": 1, "ortho_words": 1, "speaker": 1}
    assert payload["backup_path"].startswith("annotations/Fail01.parse.json.bak-")
    assert payload["backup_path"].endswith("-pre-interval-delete")

    backups = list((tmp_path / "annotations").glob("Fail01.parse.json.bak-*-pre-interval-delete"))
    assert len(backups) == 1
    assert backups[0].read_bytes() != annotation_path.read_bytes()

    updated = _read(annotation_path)
    assert [iv["text"] for iv in updated["tiers"]["concept"]["intervals"]] == ["sar", "kapul"]
    assert updated["tiers"]["concept"]["intervals"][-1]["start"] == 731.950
    assert [iv["text"] for iv in updated["tiers"]["ipa"]["intervals"]] == ["kapul-ipa-duplicate"]
    assert [iv["text"] for iv in updated["tiers"]["ortho_words"]["intervals"]] == ["kapul-word-duplicate"]
    assert updated["metadata"]["modified"] != "2026-05-28T00:00:00Z"


def test_delete_annotation_interval_404s_without_mutating_when_concept_time_is_missing(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    annotation_path = _seed_annotation(tmp_path)
    before = annotation_path.read_bytes()

    with pytest.raises(server.ApiError) as exc_info:
        _post_delete({"speaker": "Fail01", "concept_id": "247", "start": 9.0, "end": 10.0})

    assert exc_info.value.status == HTTPStatus.NOT_FOUND
    assert "No matching concept interval" in exc_info.value.message
    assert annotation_path.read_bytes() == before
    assert list((tmp_path / "annotations").glob("Fail01.parse.json.bak-*-pre-interval-delete")) == []
