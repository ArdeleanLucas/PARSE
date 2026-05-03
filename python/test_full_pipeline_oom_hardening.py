from __future__ import annotations

import builtins
import io
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


@pytest.fixture(autouse=True)
def _install_routes_and_clear_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    # Route bindings must be installed before monkeypatching server exports;
    # otherwise monkeypatch can restore lazy shims after installation.
    server._install_route_bindings()
    monkeypatch.setenv("PARSE_JOB_SNAPSHOT_DIR", str(tmp_path / "job-snapshots"))
    server._jobs.clear()
    yield
    server._jobs.clear()


def test_full_pipeline_preflight_rejects_low_host_memory_before_any_step(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_FULL_PIPELINE_MIN_MEM_GB", "2.5")
    monkeypatch.setattr(server, "_host_available_memory_gb", lambda: 1.25, raising=False)

    def fail_if_step_runs(*args, **kwargs):  # pragma: no cover - should never run
        raise AssertionError("full-pipeline memory preflight must run before STT")

    monkeypatch.setattr(server, "_compute_speaker_stt", fail_if_step_runs)

    with pytest.raises(RuntimeError) as excinfo:
        server._compute_full_pipeline("job-low-mem", {"speaker": "anon-rss", "steps": ["stt"]})

    message = str(excinfo.value)
    assert "Insufficient host memory for full pipeline" in message
    assert "1.2 GiB available" in message
    assert "2.5 GiB required" in message
    assert "PARSE_FULL_PIPELINE_MIN_MEM_GB" in message


def test_full_pipeline_preflight_error_carries_structured_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_FULL_PIPELINE_MIN_MEM_GB", "3.5")
    monkeypatch.setattr(
        server,
        "_host_memory_info",
        lambda: {"mem_available_gb": 1.25, "swap_total_gb": 0.5},
        raising=False,
    )
    monkeypatch.setattr(server, "_host_available_memory_gb", lambda: 1.25, raising=False)
    job_id = server._create_job("compute:full_pipeline", {"speaker": "anon-rss"})

    server._run_compute_job(
        job_id,
        "full_pipeline",
        {"speaker": "anon-rss", "steps": ["stt"], "run_mode": "concept-windows"},
    )

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "error"
    assert snapshot["mem_available_gb"] == pytest.approx(1.25)
    assert snapshot["required_gb"] == pytest.approx(3.5)
    assert snapshot["swap_total_gb"] == pytest.approx(0.5)
    persisted_error_logs = [
        entry
        for entry in snapshot.get("logs", [])
        if entry.get("event") in {"job.error", "job.failed"}
    ]
    assert len(persisted_error_logs) == 1
    payload = server._job_response_payload(snapshot)
    assert payload["mem_available_gb"] == pytest.approx(1.25)
    assert payload["required_gb"] == pytest.approx(3.5)
    assert payload["swap_total_gb"] == pytest.approx(0.5)


def test_full_pipeline_preflight_marks_job_error_code_as_oom_suspect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_FULL_PIPELINE_MIN_MEM_GB", "4")
    monkeypatch.setattr(
        server,
        "_host_memory_info",
        lambda: {"mem_available_gb": 1.0, "swap_total_gb": 0.0},
        raising=False,
    )
    monkeypatch.setattr(server, "_host_available_memory_gb", lambda: 1.0, raising=False)
    job_id = server._create_job("compute:full_pipeline", {"speaker": "anon-rss"})

    server._run_compute_job(
        job_id,
        "full_pipeline",
        {"speaker": "anon-rss", "steps": ["stt"], "run_mode": "concept-windows"},
    )

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["error_code"] == "oom_suspect"


def test_full_pipeline_preflight_passes_through_when_memory_is_abundant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_FULL_PIPELINE_MIN_MEM_GB", "2")
    monkeypatch.setattr(
        server,
        "_host_memory_info",
        lambda: {"mem_available_gb": 16.0, "swap_total_gb": 1.0},
        raising=False,
    )
    monkeypatch.setattr(server, "_host_available_memory_gb", lambda: 16.0, raising=False)
    calls: list[dict[str, object]] = []

    def fake_stt(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append({"job_id": job_id, "payload": payload})
        return {"speaker": payload["speaker"], "filled": 1, "total": 1}

    monkeypatch.setattr(server, "_compute_speaker_stt", fake_stt)

    result = server._compute_full_pipeline(
        "job-abundant-memory",
        {"speaker": "anon-rss", "steps": ["stt"], "run_mode": "concept-windows"},
    )

    assert len(calls) == 1
    assert result["results"]["stt"]["status"] == "ok"


def test_host_memory_helper_reads_swap_total_from_proc_meminfo(monkeypatch: pytest.MonkeyPatch) -> None:
    meminfo = """MemTotal:       8388608 kB
MemAvailable:   2621440 kB
SwapTotal:      1048576 kB
"""

    def fake_open(path: str, *args, **kwargs):
        if path == "/proc/meminfo":
            return io.StringIO(meminfo)
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    info = server._host_memory_info()
    assert info is not None
    assert info["mem_available_gb"] == pytest.approx(2.5)
    assert info["swap_total_gb"] == pytest.approx(1.0)
    assert server._host_available_memory_gb() == pytest.approx(2.5)


def test_host_memory_helper_returns_none_when_proc_meminfo_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(*args, **kwargs):
        raise FileNotFoundError("no proc meminfo")

    monkeypatch.setattr(builtins, "open", fake_open)
    assert server._host_memory_info() is None

    calls: list[str] = []

    def fake_stt(job_id: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(job_id)
        return {"speaker": payload["speaker"], "filled": 1, "total": 1}

    monkeypatch.setenv("PARSE_FULL_PIPELINE_MIN_MEM_GB", "999")
    monkeypatch.setattr(server, "_compute_speaker_stt", fake_stt)
    result = server._compute_full_pipeline(
        "job-no-proc-meminfo",
        {"speaker": "anon-rss", "steps": ["stt"], "run_mode": "concept-windows"},
    )

    assert calls == ["job-no-proc-meminfo"]
    assert result["results"]["stt"]["status"] == "ok"


def test_running_job_snapshot_survives_restart_as_interrupted_error(tmp_path: pathlib.Path) -> None:
    job_id = server._create_job("compute:full_pipeline", {"speaker": "anon-rss"})
    server._set_job_progress(job_id, 42.0, message="Pipeline step 2/4: ortho", segments_processed=12)

    snapshot_path = pathlib.Path(server._job_snapshot_path(job_id))
    persisted = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "running"
    assert persisted["progress"] == 42.0
    assert persisted["message"] == "Pipeline step 2/4: ortho"

    server._jobs.clear()
    loaded = server._load_job_snapshots()

    assert loaded == 1
    recovered = server._get_job_snapshot(job_id)
    assert recovered is not None
    assert recovered["status"] == "error"
    assert recovered["progress"] == 42.0
    assert recovered["segmentsProcessed"] == 12
    assert recovered["error_code"] == "server_restarted"
    assert "Server restarted before this job reached a terminal state" in recovered["error"]
    assert recovered["recovered_from_disk"] is True
    assert recovered["locks"]["active"] is False

    persisted_after_recovery = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert persisted_after_recovery["status"] == "error"
    assert persisted_after_recovery["error_code"] == "server_restarted"


def test_recovered_from_disk_flag_clears_on_rerun(tmp_path: pathlib.Path) -> None:
    job_id = server._create_job("compute:full_pipeline", {"speaker": "anon-rss"})
    server._set_job_progress(job_id, 12.0, message="Running before crash")
    server._jobs.clear()
    server._load_job_snapshots()
    recovered = server._get_job_snapshot(job_id)
    assert recovered is not None
    assert recovered["recovered_from_disk"] is True

    server._set_job_running(job_id, message="Rerun after restart")

    rerun = server._get_job_snapshot(job_id)
    assert rerun is not None
    assert not rerun.get("recovered_from_disk")


def test_load_job_snapshots_caps_at_200_recent_records() -> None:
    snapshot_dir = pathlib.Path(server._job_snapshot_dir(create=True))
    base_ts = time.time() - 1000.0
    for idx in range(250):
        job_id = f"job-{idx:03d}"
        path = snapshot_dir / f"{job_id}.json"
        path.write_text(
            json.dumps(
                {
                    "jobId": job_id,
                    "type": "compute:full_pipeline",
                    "status": "complete",
                    "progress": 100.0,
                    "result": {"idx": idx},
                    "created_ts": base_ts + idx,
                    "updated_ts": base_ts + idx,
                    "completed_ts": base_ts + idx,
                    "logs": [],
                    "locks": {"active": False, "resources": []},
                }
            ),
            encoding="utf-8",
        )
        os.utime(path, (base_ts + idx, base_ts + idx))

    server._jobs.clear()
    loaded = server._load_job_snapshots()

    assert loaded == 200
    assert len(server._jobs) == 200
    assert not (snapshot_dir / "job-000.json").exists()
    assert not (snapshot_dir / "job-049.json").exists()
    assert (snapshot_dir / "job-050.json").exists()
    assert (snapshot_dir / "job-249.json").exists()


def test_job_snapshot_dir_prefers_workspace_dir_over_project_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.delenv("PARSE_JOB_SNAPSHOT_DIR", raising=False)
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("PARSE_WORKSPACE_DIR", str(workspace))

    assert server._job_snapshot_dir(create=False) == workspace / ".parse-jobs"


def test_job_snapshot_dir_env_override_still_wins_over_workspace_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    override = tmp_path / "explicit-snapshots"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("PARSE_JOB_SNAPSHOT_DIR", str(override))
    monkeypatch.setenv("PARSE_WORKSPACE_DIR", str(workspace))

    assert server._job_snapshot_dir(create=False) == override


def test_sigkill_subprocess_without_result_is_classified_as_oom_suspect() -> None:
    job_id = server._create_job("compute:full_pipeline", {"speaker": "anon-rss"})
    message = server._subprocess_missing_result_message(-9, "/tmp/parse-compute-job.json")

    server._set_job_error(job_id, message)

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "error"
    assert snapshot["error_code"] == "oom_suspect"
    assert "SIGKILL" in snapshot["error"]
    assert "OOM" in snapshot["error"]


def test_parse_run_warns_loudly_when_compute_mode_is_unset() -> None:
    script = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "parse-run.sh"
    env = os.environ.copy()
    env.update(
        {
            "PARSE_RUN_WARNING_ONLY": "1",
            "PARSE_COMPUTE_MODE": "",
            "PARSE_USE_PERSISTENT_WORKER": "",
        }
    )

    result = subprocess.run(
        ["bash", str(script)],
        cwd=script.parents[1],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "WARNING: PARSE_COMPUTE_MODE is unset" in result.stderr
    assert "legacy in-process thread runner" in result.stderr
    assert "does not change the default automatically" in result.stderr
    assert "WARNING: PARSE_COMPUTE_MODE is unset" not in result.stdout


def test_parse_run_warning_is_suppressed_when_compute_mode_is_explicit() -> None:
    script = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "parse-run.sh"
    env = os.environ.copy()
    env.update(
        {
            "PARSE_RUN_WARNING_ONLY": "1",
            "PARSE_COMPUTE_MODE": "subprocess",
            "PARSE_USE_PERSISTENT_WORKER": "",
        }
    )

    result = subprocess.run(
        ["bash", str(script)],
        cwd=script.parents[1],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "PARSE_COMPUTE_MODE is unset" not in result.stdout
    assert "PARSE_COMPUTE_MODE is unset" not in result.stderr
