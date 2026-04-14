import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def _make_dir_symlink_or_skip(link_path: pathlib.Path, target_path: pathlib.Path) -> None:
    try:
        link_path.symlink_to(target_path, target_is_directory=True)
    except (NotImplementedError, OSError, PermissionError) as exc:
        pytest.skip(f"directory symlink creation unavailable in this test environment: {exc}")


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body):
        self._body = body
        self.sent = []

    def _read_json_body(self, required: bool = True):
        return self._body

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


def test_ensure_safe_working_root_raises_runtime_error(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    working_root = tmp_path / "audio" / "working"
    original_root.mkdir(parents=True)
    _make_dir_symlink_or_skip(working_root, original_root)

    with pytest.raises(RuntimeError, match="Normalize jobs are disabled"):
        server._ensure_safe_working_root(tmp_path)


def test_api_post_normalize_rejects_unsafe_working_root(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail01"})

    monkeypatch.setattr(server, "_annotation_primary_source_wav", lambda speaker: "audio/original/Fail01/input.mp3")
    monkeypatch.setattr(server, "_describe_working_root_issue", lambda project_root=None: "audio/working is a symlink")

    with pytest.raises(server.ApiError) as excinfo:
        handler._api_post_normalize()

    assert excinfo.value.status == HTTPStatus.CONFLICT
    assert "Fix audio/working before starting normalization jobs" in excinfo.value.message


def test_startup_banner_lines_include_working_root_warning(tmp_path: pathlib.Path) -> None:
    lines = server._startup_banner_lines(
        serve_dir=tmp_path,
        local_ips=["192.168.0.9"],
        working_root_issue="audio/working is a symlink",
    )

    banner = "\n".join(lines)

    assert "PARSE - HTTP Server" in banner
    assert "WARNING: audio/working is a symlink" in banner
    assert "Normalize jobs will refuse to run" in banner
    assert "http://192.168.0.9:8766/compare.html" in banner


def test_run_normalize_job_forces_wav_output_for_non_wav_input(tmp_path: pathlib.Path, monkeypatch) -> None:
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
    monkeypatch.setattr(server, "_ensure_safe_working_root", lambda project_root=None: working_root)
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
