import pathlib
import sys
from http import HTTPStatus
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.http.job_observability_handlers import (
    JobObservabilityHandlerError,
    JsonResponseSpec,
    build_job_detail_response,
    build_job_error_logs_response,
    build_job_logs_response,
    build_jobs_active_response,
    build_jobs_response,
    build_worker_status_response,
)


class _FakeWorkerHandle:
    def __init__(self, *, alive: bool, pid: int | None = 4321, jobs_in_flight: int = 0) -> None:
        self._alive = alive
        self._pid = pid
        self._jobs_in_flight = jobs_in_flight

    def is_alive(self) -> bool:
        return self._alive

    def process_pid(self) -> int | None:
        return self._pid

    def in_flight_count(self) -> int:
        return self._jobs_in_flight



def test_build_jobs_response_uses_alias_filters_and_invalid_limit_falls_back_to_100() -> None:
    calls: list[dict[str, Any]] = []

    def fake_list_jobs_snapshots(**kwargs):
        calls.append(kwargs)
        return [{"jobId": "job-1", "status": "running"}]

    response = build_jobs_response(
        "/api/jobs?statuses=complete&status=running&type=stt&type=normalize&speaker=Fail%2001&limit=bogus",
        list_jobs_snapshots=fake_list_jobs_snapshots,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "jobs": [{"jobId": "job-1", "status": "running"}],
            "count": 1,
        },
    )
    assert calls == [
        {
            "statuses": ["running"],
            "job_types": ["stt", "normalize"],
            "speaker": "Fail 01",
            "limit": 100,
        }
    ]



def test_build_jobs_response_preserves_literal_plus_characters_in_query_values() -> None:
    calls: list[dict[str, Any]] = []

    def fake_list_jobs_snapshots(**kwargs):
        calls.append(kwargs)
        return []

    build_jobs_response(
        "/api/jobs?speaker=Fail+01",
        list_jobs_snapshots=fake_list_jobs_snapshots,
    )

    assert calls == [
        {
            "statuses": None,
            "job_types": None,
            "speaker": "Fail+01",
            "limit": 100,
        }
    ]



def test_build_job_detail_response_rejects_missing_job_id() -> None:
    with pytest.raises(JobObservabilityHandlerError) as excinfo:
        build_job_detail_response("   ")

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "jobId is required"



def test_build_job_detail_response_rejects_unknown_job_id() -> None:
    with pytest.raises(JobObservabilityHandlerError) as excinfo:
        build_job_detail_response("missing-job", get_job_snapshot=lambda _: None)

    assert excinfo.value.status == HTTPStatus.NOT_FOUND
    assert excinfo.value.message == "Unknown jobId"



def test_build_job_logs_response_coerces_offset_and_invalid_limit() -> None:
    calls: list[tuple[dict[str, Any], int, int]] = []

    def fake_job_logs_payload(job: dict[str, Any], *, offset: int, limit: int) -> dict[str, Any]:
        calls.append((job, offset, limit))
        return {"jobId": job["jobId"], "offset": offset, "limit": limit, "logs": []}

    response = build_job_logs_response(
        " job-7 ",
        "/api/jobs/job-7/logs?offset=7&limit=bogus",
        get_job_snapshot=lambda _: {"jobId": "job-7", "logs": []},
        job_logs_payload=fake_job_logs_payload,
        job_log_limit=lambda: 25,
        job_log_max_entries=200,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": "job-7", "offset": 7, "limit": 200, "logs": []},
    )
    assert calls == [({"jobId": "job-7", "logs": []}, 7, 200)]



def test_build_jobs_active_response_wraps_active_snapshots() -> None:
    response = build_jobs_active_response(
        list_active_jobs_snapshots=lambda: [
            {"jobId": "job-1", "status": "running"},
            {"jobId": "job-2", "status": "queued"},
        ]
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "jobs": [
                {"jobId": "job-1", "status": "running"},
                {"jobId": "job-2", "status": "queued"},
            ]
        },
    )



def test_build_job_error_logs_response_includes_available_fields_and_stderr_tails() -> None:
    calls: list[tuple[str, int]] = []

    def fake_tail_log_file(path: str, *, max_lines: int) -> str | None:
        calls.append((path, max_lines))
        if path.endswith("job-9.stderr.log"):
            return "job stderr tail"
        if path.endswith("worker.stderr.log"):
            return "worker stderr tail"
        return None

    response = build_job_error_logs_response(
        "job-9",
        get_job_snapshot=lambda _: {
            "status": "error",
            "type": "compute:offset_detect",
            "error": "boom",
            "traceback": "traceback text",
            "message": "Pipeline failed",
        },
        tail_log_file=fake_tail_log_file,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "jobId": "job-9",
            "status": "error",
            "type": "compute:offset_detect",
            "error": "boom",
            "traceback": "traceback text",
            "message": "Pipeline failed",
            "stderrLog": "job stderr tail",
            "workerStderrLog": "worker stderr tail",
        },
    )
    assert calls == [
        ("/tmp/parse-compute-job-9.stderr.log", 200),
        ("/tmp/parse-compute-worker.stderr.log", 200),
    ]



def test_build_job_error_logs_response_rejects_unknown_job() -> None:
    with pytest.raises(JobObservabilityHandlerError) as excinfo:
        build_job_error_logs_response("missing-job", get_job_snapshot=lambda _: None)

    assert excinfo.value.status == HTTPStatus.NOT_FOUND
    assert excinfo.value.message == "Unknown job_id"



def test_build_worker_status_response_returns_ok_when_not_in_persistent_mode() -> None:
    response = build_worker_status_response(
        resolve_compute_mode=lambda: "thread",
        persistent_worker_handle=None,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "mode": "thread",
            "alive": None,
            "message": "Persistent worker mode is not active",
        },
    )



def test_build_worker_status_response_returns_503_when_handle_is_missing() -> None:
    response = build_worker_status_response(
        resolve_compute_mode=lambda: "persistent",
        persistent_worker_handle=None,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        payload={
            "mode": "persistent",
            "alive": False,
            "message": "Persistent worker handle not initialised",
        },
    )



def test_build_worker_status_response_returns_alive_payload_when_worker_is_running() -> None:
    response = build_worker_status_response(
        resolve_compute_mode=lambda: "persistent",
        persistent_worker_handle=_FakeWorkerHandle(alive=True, pid=9876, jobs_in_flight=3),
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "mode": "persistent",
            "alive": True,
            "pid": 9876,
            "jobs_in_flight": 3,
        },
    )



def test_build_worker_status_response_returns_503_when_worker_has_exited() -> None:
    response = build_worker_status_response(
        resolve_compute_mode=lambda: "persistent",
        persistent_worker_handle=_FakeWorkerHandle(alive=False, pid=2222, jobs_in_flight=1),
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        payload={
            "mode": "persistent",
            "alive": False,
            "pid": 2222,
            "jobs_in_flight": 1,
            "message": "Persistent worker process has exited",
        },
    )
