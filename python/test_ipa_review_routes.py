from __future__ import annotations

import json
import pathlib
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402


@contextmanager
def _serve_parse_http(project_root: pathlib.Path, monkeypatch):
    monkeypatch.setenv("PARSE_WORKSPACE_DIR", str(project_root))
    monkeypatch.setattr(server, "_project_root", lambda: project_root)
    server._chat_tools_runtime = None
    server._chat_orchestrator_runtime = None
    httpd = server._BoundedThreadHTTPServer(("127.0.0.1", 0), server.RangeRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{0}".format(httpd.server_port)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        server._chat_tools_runtime = None
        server._chat_orchestrator_runtime = None


def _seed_annotation(project_root: pathlib.Path, speaker: str = "Saha01", *, sidecars: dict[str, object] | None = None) -> None:
    annotations_dir = project_root / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "version": 1,
        "project_id": "parse-test",
        "speaker": speaker,
        "source_audio": "audio/raw/Saha01.wav",
        "source_audio_duration_sec": 12.0,
        "tiers": {
            "concept": {"type": "interval", "display_order": 3, "intervals": []},
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "confirmed_anchors": {},
        "metadata": {"language_code": "sdh"},
    }
    if sidecars:
        payload.update(sidecars)
    (annotations_dir / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")


def _request_json(base_url: str, path: str, *, method: str = "GET", payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=base_url + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_get_ipa_candidates_defaults_empty_for_existing_speaker(tmp_path: pathlib.Path, monkeypatch) -> None:
    _seed_annotation(tmp_path, "Saha01")

    with _serve_parse_http(tmp_path, monkeypatch) as base_url:
        status, payload = _request_json(base_url, "/api/annotations/Saha01/ipa-candidates")

    assert status == 200
    assert payload == {"candidates": {}, "review": {}}


def test_put_ipa_review_round_trips_and_get_reads_back(tmp_path: pathlib.Path, monkeypatch) -> None:
    _seed_annotation(tmp_path, "Saha01")
    key = "101::concept::0"
    encoded_key = urllib.parse.quote(key, safe="")

    with _serve_parse_http(tmp_path, monkeypatch) as base_url:
        status, put_payload = _request_json(
            base_url,
            f"/api/annotations/Saha01/ipa-review/{encoded_key}",
            method="PUT",
            payload={"status": "accepted", "suggested_ipa": "foo"},
        )
        get_status, get_payload = _request_json(base_url, "/api/annotations/Saha01/ipa-candidates")

    assert status == 200
    assert put_payload == {
        "review": {
            "status": "accepted",
            "suggested_ipa": "foo",
            "resolution_type": "",
            "evidence_sources": [],
            "notes": "",
        }
    }
    assert get_status == 200
    assert get_payload["review"] == {key: put_payload["review"]}

    saved = json.loads((tmp_path / "annotations" / "Saha01.parse.json").read_text("utf-8"))
    assert saved["ipa_review"][key] == put_payload["review"]


def test_put_ipa_review_rejects_invalid_status(tmp_path: pathlib.Path, monkeypatch) -> None:
    _seed_annotation(tmp_path, "Saha01")
    encoded_key = urllib.parse.quote("101::concept::0", safe="")

    with _serve_parse_http(tmp_path, monkeypatch) as base_url:
        status, payload = _request_json(
            base_url,
            f"/api/annotations/Saha01/ipa-review/{encoded_key}",
            method="PUT",
            payload={"status": "bogus"},
        )

    assert status == 400
    assert "status" in payload["error"]


def test_ipa_review_routes_return_404_for_missing_speaker(tmp_path: pathlib.Path, monkeypatch) -> None:
    with _serve_parse_http(tmp_path, monkeypatch) as base_url:
        get_status, _get_payload = _request_json(base_url, "/api/annotations/Missing/ipa-candidates")
        put_status, _put_payload = _request_json(
            base_url,
            "/api/annotations/Missing/ipa-review/101%3A%3Aconcept%3A%3A0",
            method="PUT",
            payload={"status": "accepted"},
        )

    assert get_status == 404
    assert put_status == 404
