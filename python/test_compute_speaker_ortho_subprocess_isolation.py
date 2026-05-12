from __future__ import annotations

import json
import os
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402
from server_routes import jobs as jobs_routes  # noqa: E402
from workers import compute_worker  # noqa: E402


@pytest.fixture(autouse=True)
def _install_routes_and_clear_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    monkeypatch.setenv("PARSE_JOB_SNAPSHOT_DIR", str(tmp_path / "job-snapshots"))
    server._jobs.clear()
    yield
    server._jobs.clear()


def _seed_annotation(tmp_path: pathlib.Path, speaker: str, *, source_audio: str = "raw/input.wav") -> None:
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
    audio = tmp_path / source_audio
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")


class _FakeProcess:
    def __init__(self, *, exitcode: int = 0, result_payload: dict[str, object] | None = None, alive: bool = False) -> None:
        self.exitcode = exitcode
        self.result_payload = result_payload
        self.alive = alive
        self.pid = 4384
        self.started = False
        self.terminated = False
        self.args: tuple[object, ...] = ()
        self.target = None
        self.name = ""

    def start(self) -> None:
        self.started = True
        if self.result_payload is not None:
            result_path = pathlib.Path(str(self.args[2]))
            result_path.write_text(json.dumps(self.result_payload), encoding="utf-8")

    def join(self, timeout: float | None = None) -> None:
        return None

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False
        self.exitcode = -15


class _FakeContext:
    def __init__(self, process: _FakeProcess) -> None:
        self.process = process

    def Process(self, *, target, name, args, daemon):  # noqa: N802 - mirrors multiprocessing API
        assert daemon is True
        self.process.target = target
        self.process.name = name
        self.process.args = args
        return self.process


def _patch_spawn(monkeypatch: pytest.MonkeyPatch, process: _FakeProcess) -> None:
    import multiprocessing

    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))


def test_full_pipeline_ortho_step_runs_in_subprocess(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Khan01-fixture")
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda step: None)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    process = _FakeProcess(
        result_payload={"ok": True, "result": {"speaker": "Khan01-fixture", "filled": 1, "skipped": False, "status": "ok"}}
    )
    _patch_spawn(monkeypatch, process)

    result = server._compute_full_pipeline("job-full-ortho", {"speaker": "Khan01-fixture", "steps": ["ortho"]})

    assert process.started is True
    assert process.target.__module__ == "server_routes.annotate"
    assert process.target.__name__ == "_speaker_ortho_subprocess_entry"
    assert process.name == "parse-speaker-ortho"
    assert result["results"]["ortho"]["status"] == "ok"
    assert result["results"]["ortho"]["filled"] == 1


def test_standalone_ortho_full_mode_runs_in_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    completed: list[dict[str, object]] = []
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_set_job_complete", lambda _job_id, result, **_kwargs: completed.append(result))
    monkeypatch.setattr(server, "_compute_speaker_ortho", lambda *_args, **_kwargs: pytest.fail("full-mode ORTH must not run in process"))

    def fake_subprocess(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((job_id, payload))
        return {"speaker": payload["speaker"], "filled": 1, "skipped": False}

    monkeypatch.setattr(server, "_compute_speaker_ortho_in_subprocess", fake_subprocess)

    server._run_compute_job("job-ortho", "ortho", {"speaker": "Khan01", "run_mode": "full"})

    assert calls == [("job-ortho", {"speaker": "Khan01", "run_mode": "full"})]
    assert completed == [{"speaker": "Khan01", "filled": 1, "skipped": False}]


def test_standalone_ortho_concept_mode_stays_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    completed: list[dict[str, object]] = []
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_set_job_complete", lambda _job_id, result, **_kwargs: completed.append(result))
    monkeypatch.setattr(server, "_compute_speaker_ortho_in_subprocess", lambda *_args, **_kwargs: pytest.fail("concept ORTH must stay in process"))

    def fake_in_process(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((job_id, payload))
        return {"speaker": payload["speaker"], "filled": 1, "run_mode": payload["run_mode"]}

    monkeypatch.setattr(server, "_compute_speaker_ortho", fake_in_process)

    server._run_compute_job("job-ortho-concept", "ortho", {"speaker": "Khan01", "run_mode": "concept-windows"})

    assert calls == [("job-ortho-concept", {"speaker": "Khan01", "run_mode": "concept-windows"})]
    assert completed == [{"speaker": "Khan01", "filled": 1, "run_mode": "concept-windows"}]


def test_compute_subprocess_entry_routes_standalone_ortho_full_mode_to_wrapper(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    result_path = tmp_path / "result.json"
    monkeypatch.setattr(server, "_compute_checkpoint", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_compute_speaker_ortho", lambda *_args, **_kwargs: pytest.fail("nested compute child must use ORTH wrapper"))

    def fake_subprocess(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((job_id, payload))
        return {"speaker": payload["speaker"], "filled": 2}

    monkeypatch.setattr(server, "_compute_speaker_ortho_in_subprocess", fake_subprocess)

    jobs_routes._compute_subprocess_entry(
        "outer-job", "ortho", {"speaker": "Khan01", "run_mode": "full"}, str(result_path), str(tmp_path / "checkpoint.log")
    )

    assert calls == [("child-outer-job", {"speaker": "Khan01", "run_mode": "full"})]
    assert json.loads(result_path.read_text("utf-8")) == {"ok": True, "result": {"speaker": "Khan01", "filled": 2}}


def test_persistent_worker_routes_standalone_ortho_by_run_mode() -> None:
    calls: list[str] = []
    server_mod = types.SimpleNamespace(
        _normalize_compute_run_mode=lambda value: "full" if value in (None, "full") else str(value),
        _compute_speaker_ortho_in_subprocess=lambda job_id, payload: calls.append(f"subprocess:{job_id}") or {"mode": "full"},
        _compute_speaker_ortho=lambda job_id, payload: calls.append(f"inprocess:{job_id}") or {"mode": payload.get("run_mode")},
    )

    full = compute_worker._dispatch(server_mod, "ortho", "job-full", {"speaker": "Khan01", "run_mode": "full"})
    concept = compute_worker._dispatch(server_mod, "ortho", "job-concept", {"speaker": "Khan01", "run_mode": "concept"})

    assert full == {"mode": "full"}
    assert concept == {"mode": "concept"}
    assert calls == ["subprocess:job-full", "inprocess:job-concept"]


def test_ortho_subprocess_timeout_returns_timeout_error_code(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    process = _FakeProcess(alive=True)
    _patch_spawn(monkeypatch, process)
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "1")
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))

    result = server._compute_speaker_ortho_in_subprocess("job-timeout", {"speaker": "Khan01"})

    assert process.started is True
    assert process.terminated is True
    assert result["status"] == "error"
    assert result["error_code"] == "timeout"
    assert "ORTH" in result["error"] or "ortho" in result["error"].lower()


def test_ortho_subprocess_clean_run_passes_through_result(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    expected = {
        "speaker": "Khan01",
        "status": "ok",
        "filled": 3,
        "skipped": False,
        "ortho_words": 9,
        "total": 3,
    }
    process = _FakeProcess(exitcode=0, result_payload={"ok": True, "result": expected})
    _patch_spawn(monkeypatch, process)
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))

    result = server._compute_speaker_ortho_in_subprocess("job-ok", {"speaker": "Khan01"})

    assert process.started is True
    assert process.target.__name__ == "_speaker_ortho_subprocess_entry"
    assert result == expected


def test_ortho_oom_does_not_kill_parent_khan01_shape(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Khan01-fixture")
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda step: None)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    parent_pid = os.getpid()
    process = _FakeProcess(
        exitcode=0,
        result_payload={
            "ok": False,
            "error": "simulated peak memory",
            "traceback": "Traceback (most recent call last):\nMemoryError: simulated peak memory\n",
        },
    )
    _patch_spawn(monkeypatch, process)

    result = server._compute_full_pipeline("job-khan01", {"speaker": "Khan01-fixture", "steps": ["ortho"]})

    assert os.getpid() == parent_pid
    assert pathlib.Path("/proc/self/status").read_text("utf-8")
    assert process.started is True
    assert result["results"]["ortho"]["status"] == "error"
    assert result["results"]["ortho"]["error_code"] == "oom_suspect"
    assert result["summary"] == {"ok": 0, "skipped": 0, "error": 1}
