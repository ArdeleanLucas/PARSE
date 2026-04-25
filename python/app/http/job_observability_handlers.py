"""Helpers for PARSE job observability and worker-status HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Dict, Optional
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class JsonResponseSpec:
    status: HTTPStatus
    payload: Dict[str, Any]


@dataclass(frozen=True)
class JobObservabilityHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


JobSnapshot = Dict[str, Any]
JobSnapshotGetter = Callable[[str], Optional[JobSnapshot]]
JobsSnapshotLister = Callable[..., list[JobSnapshot]]
ActiveJobsSnapshotLister = Callable[[], list[JobSnapshot]]
JobDetailPayloadBuilder = Callable[[JobSnapshot], Dict[str, Any]]
JobLogsPayloadBuilder = Callable[..., Dict[str, Any]]
TailLogFileReader = Callable[..., Optional[str]]
ComputeModeResolver = Callable[[], str]



def _missing_job_snapshot(_job_id: str) -> Optional[JobSnapshot]:
    return None



def _missing_jobs_list(**_kwargs: Any) -> list[JobSnapshot]:
    return []



def _identity_payload(job: JobSnapshot) -> Dict[str, Any]:
    return dict(job)



def _empty_logs_payload(_job: JobSnapshot, *, offset: int, limit: int) -> Dict[str, Any]:
    return {
        "jobId": "",
        "count": 0,
        "offset": offset,
        "limit": limit,
        "logs": [],
    }



def _no_log_tail(_path: str, *, max_lines: int) -> Optional[str]:
    return None



def _legacy_query_params(raw_path: str) -> Dict[str, list[str]]:
    params: Dict[str, list[str]] = {}
    query = urlparse(raw_path).query
    for piece in query.split("&"):
        if not piece or "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        params.setdefault(key, []).append(unquote(value))
    return params



def build_jobs_response(
    raw_path: str,
    *,
    list_jobs_snapshots: JobsSnapshotLister = _missing_jobs_list,
) -> JsonResponseSpec:
    params = _legacy_query_params(raw_path)
    statuses = params.get("status") or params.get("statuses")
    job_types = params.get("type") or params.get("types")
    speaker = (params.get("speaker") or [None])[0]
    limit_raw = (params.get("limit") or ["100"])[0]
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 100

    rows = list_jobs_snapshots(
        statuses=statuses,
        job_types=job_types,
        speaker=speaker,
        limit=limit,
    )
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobs": rows, "count": len(rows)},
    )



def build_job_detail_response(
    job_id_part: str,
    *,
    get_job_snapshot: JobSnapshotGetter = _missing_job_snapshot,
    job_detail_payload: JobDetailPayloadBuilder = _identity_payload,
) -> JsonResponseSpec:
    job_id = str(job_id_part or "").strip()
    if not job_id:
        raise JobObservabilityHandlerError(HTTPStatus.BAD_REQUEST, "jobId is required")

    job = get_job_snapshot(job_id)
    if job is None:
        raise JobObservabilityHandlerError(HTTPStatus.NOT_FOUND, "Unknown jobId")

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload=job_detail_payload(job),
    )



def build_job_logs_response(
    job_id_part: str,
    raw_path: str,
    *,
    get_job_snapshot: JobSnapshotGetter = _missing_job_snapshot,
    job_logs_payload: JobLogsPayloadBuilder = _empty_logs_payload,
    job_log_limit: Callable[[], int] = lambda: 200,
    job_log_max_entries: int = 200,
) -> JsonResponseSpec:
    job_id = str(job_id_part or "").strip()
    if not job_id:
        raise JobObservabilityHandlerError(HTTPStatus.BAD_REQUEST, "jobId is required")

    job = get_job_snapshot(job_id)
    if job is None:
        raise JobObservabilityHandlerError(HTTPStatus.NOT_FOUND, "Unknown jobId")

    params = _legacy_query_params(raw_path)
    offset = 0
    offset_values = params.get("offset") or []
    if offset_values:
        try:
            offset = int(offset_values[-1])
        except (TypeError, ValueError):
            offset = 0

    limit = job_log_limit()
    limit_values = params.get("limit") or []
    if limit_values:
        try:
            limit = int(limit_values[-1])
        except (TypeError, ValueError):
            limit = job_log_max_entries

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload=job_logs_payload(job, offset=offset, limit=limit),
    )



def build_jobs_active_response(
    *,
    list_active_jobs_snapshots: ActiveJobsSnapshotLister = lambda: [],
) -> JsonResponseSpec:
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobs": list_active_jobs_snapshots()},
    )



def build_job_error_logs_response(
    job_id: str,
    *,
    get_job_snapshot: JobSnapshotGetter = _missing_job_snapshot,
    tail_log_file: TailLogFileReader = _no_log_tail,
) -> JsonResponseSpec:
    snapshot = get_job_snapshot(job_id)
    if snapshot is None:
        raise JobObservabilityHandlerError(HTTPStatus.NOT_FOUND, "Unknown job_id")

    payload: Dict[str, Any] = {
        "jobId": job_id,
        "status": str(snapshot.get("status") or ""),
        "type": str(snapshot.get("type") or ""),
    }
    if snapshot.get("error"):
        payload["error"] = str(snapshot.get("error"))
    if snapshot.get("traceback"):
        payload["traceback"] = str(snapshot.get("traceback"))
    if snapshot.get("message"):
        payload["message"] = str(snapshot.get("message"))

    job_stderr = tail_log_file(
        "/tmp/parse-compute-{0}.stderr.log".format(job_id),
        max_lines=200,
    )
    if job_stderr:
        payload["stderrLog"] = job_stderr

    worker_stderr = tail_log_file(
        "/tmp/parse-compute-worker.stderr.log",
        max_lines=200,
    )
    if worker_stderr:
        payload["workerStderrLog"] = worker_stderr

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload=payload,
    )



def build_worker_status_response(
    *,
    resolve_compute_mode: ComputeModeResolver,
    persistent_worker_handle: Any,
) -> JsonResponseSpec:
    mode = resolve_compute_mode()
    payload: Dict[str, Any] = {"mode": mode}

    if mode != "persistent":
        payload["alive"] = None
        payload["message"] = "Persistent worker mode is not active"
        return JsonResponseSpec(status=HTTPStatus.OK, payload=payload)

    if persistent_worker_handle is None:
        payload["alive"] = False
        payload["message"] = "Persistent worker handle not initialised"
        return JsonResponseSpec(status=HTTPStatus.SERVICE_UNAVAILABLE, payload=payload)

    alive = persistent_worker_handle.is_alive()
    payload["alive"] = alive
    payload["pid"] = persistent_worker_handle.process_pid()
    payload["jobs_in_flight"] = persistent_worker_handle.in_flight_count()
    if alive:
        return JsonResponseSpec(status=HTTPStatus.OK, payload=payload)

    payload["message"] = "Persistent worker process has exited"
    return JsonResponseSpec(status=HTTPStatus.SERVICE_UNAVAILABLE, payload=payload)
