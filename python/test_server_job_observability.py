import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, path: str = "/api/jobs", body=None):
        self.path = path
        self._body = body or {}
        self.sent = []

    def _read_json_body(self, required: bool = True):
        return self._body

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


def test_job_logs_capture_lifecycle_and_progress() -> None:
    server._jobs.clear()

    job_id = server._create_job("normalize", {"speaker": "Fail01"})
    server._set_job_progress(job_id, 10.0, message="Scanning loudness (pass 1)")
    server._set_job_progress(job_id, 40.0, message="Normalizing audio (pass 2)")
    server._set_job_complete(job_id, {"speaker": "Fail01"}, message="Normalize complete")

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    logs = snapshot.get("logs")
    assert isinstance(logs, list)
    assert len(logs) >= 4
    assert logs[0]["event"] == "job.created"
    assert any(entry["event"] == "job.lock_acquired" for entry in logs)
    assert any(entry["message"] == "Scanning loudness (pass 1)" for entry in logs)
    assert any(entry["message"] == "Normalizing audio (pass 2)" for entry in logs)
    assert logs[-1]["event"] == "job.completed"
    assert logs[-1]["message"] == "Normalize complete"


def test_job_lifecycle_supports_queued_running_and_error_states(monkeypatch) -> None:
    server._jobs.clear()
    monkeypatch.setenv("PARSE_JOB_LOG_MAX_ENTRIES", "20")

    job_id = server._create_job("compute:full_pipeline", {"speaker": "Fail03"}, initial_status="queued")
    server._set_job_running(job_id, message="Dequeued for execution")
    server._set_job_progress(job_id, 15.0, message="Running pipeline")
    server._set_job_error(job_id, "ffmpeg failed with exit code 1")

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "error"
    assert snapshot["error_code"] == "ffmpeg_failed"
    events = [entry["event"] for entry in snapshot["logs"]]
    assert events[0] == "job.queued"
    assert "job.lock_acquired" in events
    assert "job.started" in events
    assert events[-1] == "job.failed"


def test_job_log_ring_buffer_size_is_configurable(monkeypatch) -> None:
    server._jobs.clear()
    monkeypatch.setenv("PARSE_JOB_LOG_MAX_ENTRIES", "10")

    job_id = server._create_job("stt", {"speaker": "Fail04"})
    for idx in range(20):
        server._set_job_progress(job_id, float(idx), message="step-{0}".format(idx))

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert len(snapshot["logs"]) == 10
    assert snapshot["logs"][-1]["message"] == "step-19"


def test_speaker_resource_lock_blocks_concurrent_mutating_jobs_and_releases_on_completion() -> None:
    server._jobs.clear()

    first_job = server._create_job("normalize", {"speaker": "Fail01", "sourceWav": "audio/Fail01.wav"})
    first_snapshot = server._get_job_snapshot(first_job)
    assert first_snapshot is not None
    assert first_snapshot["locks"]["active"] is True
    assert first_snapshot["locks"]["resources"] == [{"kind": "speaker", "id": "Fail01"}]

    with pytest.raises(server.JobResourceConflictError) as exc_info:
        server._create_job("stt", {"speaker": "Fail01", "sourceWav": "audio/Fail01.wav"})

    assert exc_info.value.resource_kind == "speaker"
    assert exc_info.value.resource_id == "Fail01"
    assert exc_info.value.holder_job_id == first_job

    probe_job = server._create_job("compute:offset_detect", {"speaker": "Fail01"})
    assert isinstance(probe_job, str)

    server._set_job_complete(first_job, {"ok": True}, message="Normalize complete")
    finished_snapshot = server._get_job_snapshot(first_job)
    assert finished_snapshot is not None
    assert finished_snapshot["locks"]["active"] is False
    assert finished_snapshot["locks"]["released_at"] is not None

    second_job = server._create_job("stt", {"speaker": "Fail01", "sourceWav": "audio/Fail01.wav"})
    second_snapshot = server._get_job_snapshot(second_job)
    assert second_snapshot is not None
    assert second_snapshot["locks"]["active"] is True
    assert second_snapshot["locks"]["resources"] == [{"kind": "speaker", "id": "Fail01"}]


def test_job_completion_dispatches_callback_payload(monkeypatch) -> None:
    server._jobs.clear()
    delivered = []

    def fake_post(url: str, payload: dict) -> None:
        delivered.append((url, payload))

    monkeypatch.setattr(server, "_post_job_callback", fake_post)
    monkeypatch.setattr(server, "_dispatch_job_callback_async", lambda snapshot: server._dispatch_job_callback(snapshot))

    job_id = server._create_job(
        "stt",
        {"speaker": "Fail01", "callbackUrl": "https://example.test/hooks/job"},
    )
    server._set_job_complete(job_id, {"segments": 12}, message="STT complete")

    assert len(delivered) == 1
    callback_url, payload = delivered[0]
    assert callback_url == "https://example.test/hooks/job"
    assert payload["jobId"] == job_id
    assert payload["status"] == "complete"
    assert payload["result"] == {"segments": 12}
    assert payload["meta"]["speaker"] == "Fail01"



def test_job_error_dispatches_callback_payload(monkeypatch) -> None:
    server._jobs.clear()
    delivered = []

    def fake_post(url: str, payload: dict) -> None:
        delivered.append((url, payload))

    monkeypatch.setattr(server, "_post_job_callback", fake_post)
    monkeypatch.setattr(server, "_dispatch_job_callback_async", lambda snapshot: server._dispatch_job_callback(snapshot))

    job_id = server._create_job(
        "normalize",
        {"speaker": "Fail02", "callbackUrl": "https://example.test/hooks/job"},
    )
    server._set_job_error(job_id, "ffmpeg failed with exit code 1")

    assert len(delivered) == 1
    callback_url, payload = delivered[0]
    assert callback_url == "https://example.test/hooks/job"
    assert payload["jobId"] == job_id
    assert payload["status"] == "error"
    assert payload["errorCode"] == "ffmpeg_failed"
    assert payload["meta"]["speaker"] == "Fail02"



def test_compute_cancel_route_returns_404_for_unknown_job() -> None:
    from ai.job_cancel import clear_cancel, is_cancelled

    server._jobs.clear()
    clear_cancel("missing-job")
    handler = _HandlerHarness("/api/compute/missing-job/cancel")

    handler._dispatch_api_post("/api/compute/missing-job/cancel")

    status, payload = handler.sent[-1]
    assert status == HTTPStatus.NOT_FOUND
    assert payload == {"cancelled": False, "job_id": "missing-job", "reason": "not found"}
    assert is_cancelled("missing-job") is False


def test_compute_cancel_route_returns_200_for_known_job() -> None:
    from ai.job_cancel import clear_cancel, is_cancelled

    server._jobs.clear()
    job_id = server._create_job("compute:ortho", {"speaker": "Fail01"})
    clear_cancel(job_id)
    handler = _HandlerHarness("/api/compute/{0}/cancel".format(job_id))

    handler._dispatch_api_post("/api/compute/{0}/cancel".format(job_id))

    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload == {"cancelled": True, "job_id": job_id}
    assert is_cancelled(job_id) is True
    clear_cancel(job_id)


def test_compute_cancel_route_is_idempotent_for_known_job() -> None:
    from ai.job_cancel import clear_cancel, is_cancelled

    server._jobs.clear()
    job_id = server._create_job("compute:ortho", {"speaker": "Fail01"})
    clear_cancel(job_id)
    handler = _HandlerHarness("/api/compute/{0}/cancel".format(job_id))

    handler._dispatch_api_post("/api/compute/{0}/cancel".format(job_id))
    handler._dispatch_api_post("/api/compute/{0}/cancel".format(job_id))

    assert handler.sent[-2:] == [
        (HTTPStatus.OK, {"cancelled": True, "job_id": job_id}),
        (HTTPStatus.OK, {"cancelled": True, "job_id": job_id}),
    ]
    assert is_cancelled(job_id) is True
    clear_cancel(job_id)


def test_api_get_jobs_and_job_logs_return_generic_observability_payloads() -> None:
    server._jobs.clear()

    running_job = server._create_job("stt", {"speaker": "Fail01"})
    finished_job = server._create_job("normalize", {"speaker": "Fail02"})
    server._set_job_progress(running_job, 25.0, message="Transcribing")
    server._set_job_complete(finished_job, {"speaker": "Fail02"}, message="Normalize complete")

    handler = _HandlerHarness("/api/jobs")
    handler._api_get_jobs()
    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["count"] == 2
    by_id = {job["jobId"]: job for job in payload["jobs"]}
    assert by_id[running_job]["status"] == "running"
    assert by_id[finished_job]["status"] == "complete"
    assert by_id[running_job]["logCount"] >= 2

    handler._api_get_job(running_job)
    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == running_job
    assert payload["type"] == "stt"
    assert payload["meta"]["speaker"] == "Fail01"
    assert payload["locks"]["active"] is True
    assert payload["locks"]["resources"] == [{"kind": "speaker", "id": "Fail01"}]

    handler.path = "/api/jobs/{0}/logs".format(running_job)
    handler._api_get_job_logs(running_job)
    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == running_job
    assert payload["count"] >= 2
    assert payload["logs"][-1]["message"] == "Transcribing"


def test_backward_compatible_status_endpoints_still_return_job_payloads() -> None:
    server._jobs.clear()

    stt_job = server._create_job("stt", {"speaker": "Fail01"})
    normalize_job = server._create_job("normalize", {"speaker": "Fail02"})
    server._set_job_progress(stt_job, 35.0, message="Transcribing")
    server._set_job_error(normalize_job, "ffmpeg failed with exit code 1")

    stt_handler = _HandlerHarness("/api/stt/status", {"jobId": stt_job})
    stt_handler._api_post_stt_status()
    status, payload = stt_handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == stt_job
    assert payload["status"] == "running"

    normalize_handler = _HandlerHarness("/api/normalize/status", {"jobId": normalize_job})
    normalize_handler._api_post_normalize_status()
    status, payload = normalize_handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == normalize_job
    assert payload["status"] == "error"
    assert payload["errorCode"] == "ffmpeg_failed"



def test_api_rejects_conflicting_speaker_mutation_jobs_with_409() -> None:
    server._jobs.clear()
    lock_job = server._create_job("normalize", {"speaker": "Fail01", "sourceWav": "audio/Fail01.wav"})

    handler = _HandlerHarness(
        "/api/stt",
        {"speaker": "Fail01", "sourceWav": "audio/Fail01.wav"},
    )

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_stt_start()

    assert exc_info.value.status == HTTPStatus.CONFLICT
    assert lock_job in exc_info.value.message
    assert "Fail01" in exc_info.value.message



def test_api_rejects_invalid_callback_url() -> None:
    server._jobs.clear()
    handler = _HandlerHarness(
        "/api/stt",
        {"speaker": "Fail01", "sourceWav": "audio/Fail01.wav", "callbackUrl": "ftp://example.test/hook"},
    )

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_stt_start()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert "callbackUrl" in exc_info.value.message


class _FakePersistentWorkerHandle:
    def __init__(self, *, alive: bool, pid: int | None = 4242, jobs_in_flight: int = 0) -> None:
        self._alive = alive
        self._pid = pid
        self._jobs_in_flight = jobs_in_flight

    def is_alive(self) -> bool:
        return self._alive

    def process_pid(self) -> int | None:
        return self._pid

    def in_flight_count(self) -> int:
        return self._jobs_in_flight



def test_api_get_jobs_active_returns_active_job_payloads() -> None:
    server._jobs.clear()
    running_job = server._create_job("stt", {"speaker": "Fail08"})
    server._set_job_progress(running_job, 50.0, message="Halfway there")

    handler = _HandlerHarness("/api/jobs/active")
    handler._api_get_jobs_active()

    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobs"]
    assert payload["jobs"][0]["jobId"] == running_job
    assert payload["jobs"][0]["status"] == "running"



def test_api_get_job_error_logs_returns_traceback_and_stderr_tails(monkeypatch) -> None:
    server._jobs.clear()
    job_id = server._create_job("normalize", {"speaker": "Fail09"})
    server._set_job_error(job_id, "ffmpeg failed with exit code 1", traceback_str="traceback lines")

    def fake_tail_log_file(path: str, *, max_lines: int = 200):
        if path.endswith(f"{job_id}.stderr.log"):
            return "per-job stderr"
        if path.endswith("worker.stderr.log"):
            return "worker stderr"
        return None

    monkeypatch.setattr(server, "_tail_log_file", fake_tail_log_file)

    handler = _HandlerHarness(f"/api/jobs/{job_id}/logs")
    handler._api_get_job_error_logs(job_id)

    status, payload = handler.sent[-1]
    assert status == HTTPStatus.OK
    assert payload["jobId"] == job_id
    assert payload["status"] == "error"
    assert payload["error"] == "ffmpeg failed with exit code 1"
    assert payload["traceback"] == "traceback lines"
    assert payload["stderrLog"] == "per-job stderr"
    assert payload["workerStderrLog"] == "worker stderr"



def test_api_get_worker_status_maps_persistent_worker_health(monkeypatch) -> None:
    handler = _HandlerHarness("/api/worker/status")

    monkeypatch.setattr(server, "_resolve_compute_mode", lambda: "persistent")
    monkeypatch.setattr(server, "_PERSISTENT_WORKER_HANDLE", _FakePersistentWorkerHandle(alive=False, pid=1337, jobs_in_flight=2))

    handler._api_get_worker_status()

    status, payload = handler.sent[-1]
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert payload == {
        "mode": "persistent",
        "alive": False,
        "pid": 1337,
        "jobs_in_flight": 2,
        "message": "Persistent worker process has exited",
    }
