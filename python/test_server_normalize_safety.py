import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body):
        self._body = body
        self.sent = []

    def _read_json_body(self, required: bool = True):
        return self._body

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


class _ImmediateThread:
    def __init__(self, target=None, args=(), daemon=None):
        self._target = target
        self._args = args

    def start(self):
        return None


def test_api_post_normalize_does_not_consult_working_root_guard(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail01"})

    monkeypatch.setattr(server, "_annotation_primary_source_wav", lambda speaker: "audio/original/Fail01/input.mp3")
    monkeypatch.setattr(server, "_describe_working_root_issue", lambda project_root=None: (_ for _ in ()).throw(AssertionError("working-root guard should not be consulted")), raising=False)
    monkeypatch.setattr(server, "_create_job", lambda job_type, metadata=None: "job-123")
    monkeypatch.setattr(server.threading, "Thread", _ImmediateThread)

    handler._api_post_normalize()

    assert handler.sent == [
        (
            HTTPStatus.OK,
            {
                "job_id": "job-123",
                "jobId": "job-123",
                "status": "running",
            },
        )
    ]


def test_startup_banner_lines_point_to_built_ui_without_working_root_warning(tmp_path: pathlib.Path) -> None:
    dist_index = tmp_path / "dist" / "index.html"
    dist_index.parent.mkdir(parents=True)
    dist_index.write_text("<html></html>", encoding="utf-8")

    lines = server._startup_banner_lines(
        serve_dir=tmp_path,
        local_ips=["192.168.0.9"],
    )

    banner = "\n".join(lines)

    assert "PARSE - HTTP Server" in banner
    assert "http://192.168.0.9:8766/compare" in banner
    assert ".html" not in banner
    assert "WARNING:" not in banner
    assert "Normalize jobs will refuse to run" not in banner


def test_run_normalize_job_forces_wav_output_for_non_wav_input_without_guard(tmp_path: pathlib.Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    original_dir = project_root / "audio" / "original" / "Fail01"
    working_root = project_root / "audio" / "working"
    original_dir.mkdir(parents=True)
    working_root.mkdir(parents=True)
    source_path = original_dir / "recording.mp3"
    source_path.write_bytes(b"fake")

    completions = []
    progress_updates = []

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        if cmd[:2] == ["ffmpeg", "-version"]:
            return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()
        if any("print_format=json" in str(part) for part in cmd):
            stderr = '{"input_i":"-20.4","input_tp":"-1.1","input_lra":"5.2","input_thresh":"-31.2"}'
            return type("Result", (), {"returncode": 0, "stderr": stderr, "stdout": ""})()

        output_path = pathlib.Path(cmd[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav")
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(server, "_resolve_project_path", lambda raw_path: source_path)
    monkeypatch.setattr(server, "_ensure_safe_working_root", lambda project_root=None: (_ for _ in ()).throw(AssertionError("working-root guard should not run inside normalize job")), raising=False)
    monkeypatch.setattr(server, "_project_root", lambda: project_root)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: progress_updates.append((args, kwargs)))
    monkeypatch.setattr(server, "_set_job_complete", lambda *args, **kwargs: completions.append((args, kwargs)))
    monkeypatch.setattr(server, "_set_job_error", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(f"unexpected error: {args}, {kwargs}")))
    monkeypatch.setattr(server.subprocess, "run", fake_run)

    server._run_normalize_job("job-1", "Fail01", "audio/original/Fail01/recording.mp3")

    assert progress_updates
    assert completions
    result = completions[0][0][1]
    assert result["normalizedPath"].endswith("audio/working/Fail01/recording.wav")
