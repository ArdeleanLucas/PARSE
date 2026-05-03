from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

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
    assert recovered["locks"]["active"] is False

    persisted_after_recovery = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert persisted_after_recovery["status"] == "error"
    assert persisted_after_recovery["error_code"] == "server_restarted"


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
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert result.returncode == 0
    assert "WARNING: PARSE_COMPUTE_MODE is unset" in result.stdout
    assert "legacy in-process thread runner" in result.stdout
    assert "does not change the default automatically" in result.stdout


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
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert result.returncode == 0
    assert "PARSE_COMPUTE_MODE is unset" not in result.stdout
