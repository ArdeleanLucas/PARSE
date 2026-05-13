"""Isolated HTTP smoke for job-tracked tagged lexeme rerun.

This test intentionally uses a temporary project root and mocks the compute
runner so CI never touches Lucas' live workspace or loads HF Whisper/wav2vec2.
"""
from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


@pytest.fixture(autouse=True)
def _block_live_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / "parse-isolation-tagged-rerun-job"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BLOCK_LIVE_PROCESS_ISOLATION", "1")
    monkeypatch.setenv("PARSE_WORKSPACE", str(project_root))


def _write_fixture(project_root: Path) -> None:
    annotations = project_root / "annotations"
    annotations.mkdir(parents=True, exist_ok=True)
    intervals = [
        {"start": 1.0, "end": 1.4, "text": "one", "concept_id": "c1"},
        {"start": 2.0, "end": 2.4, "text": "two", "concept_id": "c2"},
        {"start": 3.0, "end": 3.4, "text": "three", "concept_id": "c3"},
        {"start": 4.0, "end": 4.4, "text": "four", "concept_id": "c4"},
    ]
    (annotations / "Smoke01.parse.json").write_text(
        json.dumps(
            {
                "speaker": "Smoke01",
                "tiers": {"concept": {"type": "interval", "intervals": intervals}},
                "concept_tags": {f"c{i}": ["t-smoke"] for i in range(1, 5)},
            }
        ),
        encoding="utf-8",
    )


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=2.0) as response:  # noqa: S310 - local test server only
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:  # pragma: no cover - retained for clearer assertion failures
        body = exc.read().decode("utf-8")
        raise AssertionError(f"HTTP {exc.code} for {url}: {body}") from exc


def test_tagged_rerun_http_smoke_returns_job_progress_and_result_without_blocking_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import server
    import storage.tags_store as tags_store

    project_root = tmp_path / "parse-isolation-tagged-rerun-job"
    _write_fixture(project_root)

    monkeypatch.setattr(tags_store, "fetch_all", lambda: {"tags": [{"id": "t-smoke", "label": "Smoke", "concepts": [], "lexemeTargets": []}]})
    monkeypatch.setattr(server, "_project_root", lambda: project_root)
    monkeypatch.setattr(server, "_workspace_frontend_config", lambda config=None: {"project_name": "PARSE smoke"})
    monkeypatch.setattr(server, "_resolve_compute_mode", lambda: "thread")

    def fake_launch_compute_runner(job_id: str, compute_type: str, payload: dict[str, Any]) -> None:
        assert compute_type == "lexemes_rerun_by_tag"

        def run() -> None:
            rows: list[dict[str, Any]] = []
            for idx in range(4):
                server._set_job_progress(job_id, 15.0 + idx * 20.0, message=f"{idx + 1}/4: c{idx + 1}")
                time.sleep(0.03)
                rows.append({"speaker": "Smoke01", "conceptId": f"c{idx + 1}", "field": payload["field"], "status": "ok", "text": f"mock-{idx + 1}"})
            server._set_job_complete(
                job_id,
                {
                    "resolved": {"tags": [{"id": "t-smoke", "label": "Smoke"}], "match": "any", "totalConcepts": 4, "concepts": []},
                    "total": 4,
                    "results": rows,
                },
                message="Complete",
            )

        threading.Thread(target=run, daemon=True).start()

    monkeypatch.setattr(server, "_launch_compute_runner", fake_launch_compute_runner)

    httpd = server._BoundedThreadHTTPServer(("127.0.0.1", 0), server.RangeRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        config_status, _ = _json_request("GET", f"{base_url}/api/config")
        assert config_status == HTTPStatus.OK

        status, started = _json_request(
            "POST",
            f"{base_url}/api/lexemes/rerun-by-tag",
            {"speakers": ["Smoke01"], "tagLabels": ["Smoke"], "field": "ortho"},
        )
        assert status == HTTPStatus.ACCEPTED
        job_id = started["jobId"]
        assert job_id

        observed_progress: list[float] = []
        for _ in range(30):
            config_status, _ = _json_request("GET", f"{base_url}/api/config")
            assert config_status == HTTPStatus.OK
            active_status, active = _json_request("GET", f"{base_url}/api/jobs/active")
            assert active_status == HTTPStatus.OK
            active_jobs = active.get("jobs", [])
            matching = [job for job in active_jobs if job.get("jobId") == job_id or job.get("job_id") == job_id]
            if matching:
                observed_progress.append(float(matching[0].get("progress", 0.0)))
            poll_status, snapshot = _json_request("POST", f"{base_url}/api/compute/status", {"jobId": job_id})
            assert poll_status == HTTPStatus.OK
            if snapshot.get("status") == "complete":
                result = snapshot["result"]
                break
            time.sleep(0.02)
        else:  # pragma: no cover - failure path carries current active-job evidence
            raise AssertionError(f"tagged rerun smoke job did not complete; progress={observed_progress}")

        assert observed_progress
        assert observed_progress == sorted(observed_progress)
        assert result["total"] == 4
        assert set(result) == {"resolved", "total", "results"}
        assert [row["conceptId"] for row in result["results"]] == ["c1", "c2", "c3", "c4"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2.0)
