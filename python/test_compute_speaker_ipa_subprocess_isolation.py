from __future__ import annotations

import json
import pathlib
import sys
import types
from typing import Any, Callable

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402
from workers import compute_worker  # noqa: E402


@pytest.fixture(autouse=True)
def _install_routes_and_clear_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    monkeypatch.setenv("PARSE_JOB_SNAPSHOT_DIR", str(tmp_path / "job-snapshots"))
    server._jobs.clear()
    yield
    server._jobs.clear()


class _FakeProcess:
    def __init__(
        self,
        *,
        exitcode: int | None = 0,
        result_payload: dict[str, object] | None = None,
        alive: bool = False,
    ) -> None:
        self.exitcode = exitcode
        self.result_payload = result_payload
        self.alive = alive
        self.pid = 4343
        self.started = False
        self.terminated = False
        self.args: tuple[object, ...] = ()
        self.target: Callable[..., object] | None = None
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


def test_speaker_ipa_full_mode_runs_in_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_subprocess(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(f"subprocess:{job_id}:{payload.get('run_mode')}")
        return {"speaker": payload["speaker"], "filled": 1, "total": 1}

    def fake_direct(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(f"direct:{job_id}:{payload.get('run_mode')}")
        return {"speaker": payload["speaker"], "filled": 1, "total": 1}

    monkeypatch.setattr(server, "_compute_speaker_ipa_in_subprocess", fake_subprocess, raising=False)
    monkeypatch.setattr(server, "_compute_speaker_ipa", fake_direct)

    job_id = server._create_job("compute:ipa", {"speaker": "Fail02"})
    server._run_compute_job(job_id, "ipa", {"speaker": "Fail02", "run_mode": "full"})

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "complete"
    assert calls == ["subprocess:{0}:full".format(job_id)]

    calls.clear()
    fake_worker_server = types.SimpleNamespace(
        _normalize_compute_run_mode=server._normalize_compute_run_mode,
        _compute_speaker_ipa_in_subprocess=fake_subprocess,
        _compute_speaker_ipa=fake_direct,
    )
    result = compute_worker._dispatch(fake_worker_server, "ipa", "worker-job", {"speaker": "Fail02", "run_mode": "full"})

    assert result["filled"] == 1
    assert calls == ["subprocess:worker-job:full"]


def test_speaker_ipa_concept_mode_stays_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_subprocess(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(f"subprocess:{job_id}:{payload.get('run_mode')}")
        return {"speaker": payload["speaker"], "filled": 1, "total": 1}

    def fake_direct(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(f"direct:{job_id}:{payload.get('run_mode')}")
        return {"speaker": payload["speaker"], "filled": 1, "total": 1}

    monkeypatch.setattr(server, "_compute_speaker_ipa_in_subprocess", fake_subprocess, raising=False)
    monkeypatch.setattr(server, "_compute_speaker_ipa", fake_direct)

    job_id = server._create_job("compute:ipa", {"speaker": "Fail02"})
    server._run_compute_job(job_id, "ipa", {"speaker": "Fail02", "run_mode": "concept-windows"})

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "complete"
    assert calls == ["direct:{0}:concept-windows".format(job_id)]

    calls.clear()
    fake_worker_server = types.SimpleNamespace(
        _normalize_compute_run_mode=server._normalize_compute_run_mode,
        _compute_speaker_ipa_in_subprocess=fake_subprocess,
        _compute_speaker_ipa=fake_direct,
    )
    result = compute_worker._dispatch(fake_worker_server, "ipa", "worker-job", {"speaker": "Fail02", "run_mode": "concept-windows"})

    assert result["filled"] == 1
    assert calls == ["direct:worker-job:concept-windows"]


def test_speaker_ipa_subprocess_oom_returns_oom_suspect(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    import multiprocessing

    process = _FakeProcess(exitcode=137)
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "1")

    result = server._compute_speaker_ipa_in_subprocess("job-oom", {"speaker": "Fail02"})

    assert process.started is True
    assert process.target is not None
    assert process.target.__module__ == "server_routes.annotate"
    assert process.target.__name__ == "_speaker_ipa_subprocess_entry"
    assert result["status"] == "error"
    assert result["error_code"] == "oom_suspect"
    assert result["exit_code"] == 137
    assert "oom" in result["error"].lower()


def test_speaker_ipa_subprocess_timeout_returns_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    import multiprocessing

    process = _FakeProcess(exitcode=None, alive=True)
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "1")

    result = server._compute_speaker_ipa_in_subprocess("job-timeout", {"speaker": "Fail02"})

    assert process.started is True
    assert process.terminated is True
    assert result["status"] == "error"
    assert result["error_code"] == "timeout"
    assert "timed out" in result["error"].lower() or "exceeded" in result["error"].lower()


def test_speaker_ipa_subprocess_clean_run_returns_result(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    import multiprocessing

    process = _FakeProcess(
        exitcode=0,
        result_payload={"ok": True, "result": {"speaker": "Fail02", "filled": 2, "total": 2}},
    )
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "1")

    result = server._compute_speaker_ipa_in_subprocess("job-ok", {"speaker": "Fail02"})

    assert process.started is True
    assert process.name == "parse-speaker-ipa"
    assert process.target is not None
    assert process.target.__name__ == "_speaker_ipa_subprocess_entry"
    assert result == {"speaker": "Fail02", "filled": 2, "total": 2}


def test_run_in_isolated_subprocess_helper_log_prefix_used(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    import multiprocessing

    events: list[str] = []
    process = _FakeProcess(exitcode=0, result_payload={"ok": True, "result": {"done": True}})
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))
    monkeypatch.setattr(server, "_compute_checkpoint", lambda event, **_kwargs: events.append(event))

    def fake_entry(*_args: Any) -> None:
        return None

    result = server._run_in_isolated_subprocess(
        "job-unit",
        {"speaker": "Fail02"},
        subprocess_entry=fake_entry,
        log_prefix="UNIT_TEST",
        result_file_prefix="parse-unit-test-",
    )

    assert result == {"done": True}
    assert process.started is True
    assert process.name == "parse-unit-test"
    assert process.target is fake_entry
    assert events == ["UNIT_TEST.started", "UNIT_TEST.exited"]
