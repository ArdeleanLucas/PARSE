from __future__ import annotations

import builtins
import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


@pytest.fixture(autouse=True)
def _install_routes_and_clear_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    monkeypatch.setenv("PARSE_JOB_SNAPSHOT_DIR", str(tmp_path / "job-snapshots"))
    server._jobs.clear()
    yield
    server._jobs.clear()


def _seed_annotation(tmp_path: pathlib.Path, speaker: str, source_audio: str = "raw/Fail02.wav") -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    (annotations_dir / f"{speaker}.parse.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "t",
                "speaker": speaker,
                "source_audio": source_audio,
                "source_audio_duration_sec": 10.0,
                "tiers": {
                    "ipa": {"type": "interval", "display_order": 1, "intervals": []},
                    "ortho": {"type": "interval", "display_order": 2, "intervals": []},
                    "concept": {"type": "interval", "display_order": 3, "intervals": []},
                    "speaker": {"type": "interval", "display_order": 4, "intervals": []},
                },
                "metadata": {"language_code": "sdh"},
            }
        ),
        encoding="utf-8",
    )


def _write_fake_source_wav(tmp_path: pathlib.Path, rel_path: str) -> pathlib.Path:
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    return path


class _FakeProcess:
    def __init__(self, *, exitcode: int, result_payload: dict[str, object] | None = None) -> None:
        self.exitcode = exitcode
        self.result_payload = result_payload
        self.pid = 4242
        self.started = False
        self.args: tuple[object, ...] = ()
        self.target = None

    def start(self) -> None:
        self.started = True
        if self.result_payload is not None:
            result_path = pathlib.Path(str(self.args[2]))
            result_path.write_text(json.dumps(self.result_payload), encoding="utf-8")

    def join(self, timeout: float | None = None) -> None:
        return None

    def is_alive(self) -> bool:
        return False

    def terminate(self) -> None:  # pragma: no cover - timeout path only
        self.exitcode = -15


class _FakeContext:
    def __init__(self, process: _FakeProcess) -> None:
        self.process = process

    def Process(self, *, target, name, args, daemon):  # noqa: N802 - mirrors multiprocessing API
        assert name == "parse-full-pipeline-ipa"
        assert daemon is True
        self.process.target = target
        self.process.args = args
        return self.process


def test_collect_after_unload_swallows_torch_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("torch unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    server._collect_after_unload()


def test_full_pipeline_preflights_host_memory_before_ipa_step(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_ensure_free_gpu_memory_for_ipa", lambda: None)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: types.SimpleNamespace(unload_model=lambda: None))

    events: list[str] = []

    def fake_preflight(step: str) -> None:
        events.append(f"preflight:{step}")

    def fake_ortho(_job_id: str, _payload: dict[str, object], *, provider=None) -> dict[str, object]:
        events.append("ortho")
        return {"speaker": "Fail02", "filled": 1, "skipped": False}

    def fake_ipa_subprocess(_job_id: str, _payload: dict[str, object]) -> dict[str, object]:
        events.append("ipa")
        return {"status": "ok", "speaker": "Fail02", "filled": 1, "total": 1}

    monkeypatch.setattr(server, "_ensure_host_memory_for_step", fake_preflight)
    monkeypatch.setattr(server, "_compute_speaker_ortho", fake_ortho)
    monkeypatch.setattr(server, "_compute_full_pipeline_ipa_in_subprocess", fake_ipa_subprocess)

    result = server._compute_full_pipeline("job-preflight", {"speaker": "Fail02", "steps": ["ortho", "ipa"]})

    assert events == ["preflight:ortho", "ortho", "preflight:ipa", "ipa"]
    assert result["results"]["ipa"]["status"] == "ok"


def test_full_pipeline_preserves_completed_steps_when_ipa_subprocess_is_killed(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda step: None)
    monkeypatch.setattr(server, "_ensure_free_gpu_memory_for_ipa", lambda: None)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: types.SimpleNamespace(unload_model=lambda: None))
    monkeypatch.setattr(
        server,
        "_compute_speaker_ortho",
        lambda *_args, **_kwargs: {"speaker": "Fail02", "filled": 1, "skipped": False},
    )
    monkeypatch.setattr(
        server,
        "_compute_full_pipeline_ipa_in_subprocess",
        lambda *_args, **_kwargs: server._full_pipeline_ipa_subprocess_error_result(137, None),
    )

    result = server._compute_full_pipeline("job-killed", {"speaker": "Fail02", "steps": ["ortho", "ipa"]})

    assert result["results"]["ortho"]["status"] == "ok"
    assert result["results"]["ipa"]["status"] == "error"
    ipa_error = result["results"]["ipa"]["error"]
    assert "subprocess" in ipa_error.lower()
    assert "oom" in ipa_error.lower()
    assert result["summary"] == {"ok": 1, "skipped": 0, "error": 1}


def test_ipa_subprocess_exit_137_returns_oom_error(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    import multiprocessing

    process = _FakeProcess(exitcode=137)
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "60")

    result = server._compute_full_pipeline_ipa_in_subprocess("job-137", {"speaker": "Fail02"})

    assert process.started is True
    assert process.target.__module__ == "server_routes.annotate"
    assert process.target.__name__ == "_full_pipeline_ipa_subprocess_entry"
    assert result["status"] == "error"
    assert "subprocess" in result["error"].lower()
    assert "oom" in result["error"].lower()
    assert result["exit_code"] == 137


def test_successful_ipa_subprocess_output_is_merged(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    import multiprocessing

    process = _FakeProcess(
        exitcode=0,
        result_payload={"ok": True, "result": {"speaker": "Fail02", "filled": 2, "total": 2}},
    )
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "60")

    result = server._compute_full_pipeline_ipa_in_subprocess("job-ok", {"speaker": "Fail02"})

    assert process.started is True
    assert process.target.__module__ == "server_routes.annotate"
    assert process.target.__name__ == "_full_pipeline_ipa_subprocess_entry"
    assert result == {"status": "ok", "speaker": "Fail02", "filled": 2, "total": 2}
