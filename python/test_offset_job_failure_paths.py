"""Failure-path tests for the async offset-detect compute job.

These complement test_offset_detect_monotonic + test_offset_manual_pairs
by covering the *error reporting* surface introduced in the Beta
stability PR: traceback-preserving job state, /api/jobs/<id>/logs tail
reader, and the offset-specific 600 s hard deadline.
"""
from __future__ import annotations

import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server


def _reset_job(job_id: str, status: str = "running") -> None:
    with server._jobs_lock:
        server._jobs[job_id] = {
            "jobId": job_id,
            "status": status,
            "progress": 0.0,
            "result": None,
            "error": None,
            "updated_at": "",
            "updated_ts": time.time(),
        }


def test_set_job_error_stores_traceback_separately_from_reason():
    """The short reason and full traceback must land in distinct fields
    so the UI's crash-log modal renders them separately instead of
    splitting a concatenated blob on newlines."""
    job_id = "fail-job-1"
    _reset_job(job_id)
    server._set_job_error(
        job_id,
        "Offset detection failed: STT missing",
        traceback_str="Traceback (most recent call last):\n  File …\nValueError: STT missing",
    )

    snap = server._get_job_snapshot(job_id)
    assert snap is not None
    assert snap["status"] == "error"
    assert snap["error"] == "Offset detection failed: STT missing"
    assert snap["traceback"].startswith("Traceback (most recent call last)")
    # The short reason must NOT be polluted by the traceback — regressions
    # here would re-introduce the "wall of stderr in a toast" UX.
    assert "Traceback" not in snap["error"]


def test_job_response_payload_exposes_traceback_to_http_clients():
    job_id = "fail-job-2"
    _reset_job(job_id)
    server._set_job_error(
        job_id,
        "BOOM",
        traceback_str="Traceback\n  File\nRuntimeError: BOOM",
    )
    snap = server._get_job_snapshot(job_id)
    payload = server._job_response_payload(snap)
    assert payload["error"] == "BOOM"
    assert payload["traceback"].startswith("Traceback")


def test_tail_log_file_handles_missing_and_empty(tmp_path):
    missing = tmp_path / "does-not-exist.log"
    assert server._tail_log_file(str(missing)) is None

    empty = tmp_path / "empty.log"
    empty.write_text("")
    assert server._tail_log_file(str(empty)) is None

    populated = tmp_path / "pop.log"
    populated.write_text("line1\nline2\nline3\n")
    result = server._tail_log_file(str(populated), max_lines=2)
    assert result is not None
    assert result.splitlines() == ["line2", "line3"]


def test_enforce_offset_deadline_passes_before_expiry():
    # Deadline 10s in the future — must not raise.
    server._enforce_offset_deadline(time.monotonic() + 10.0, "test")


def test_enforce_offset_deadline_raises_after_expiry():
    with pytest.raises(TimeoutError) as excinfo:
        server._enforce_offset_deadline(time.monotonic() - 1.0, "pre-match")
    assert "pre-match" in str(excinfo.value)
    assert "PARSE_OFFSET_DETECT_TIMEOUT_SEC" in str(excinfo.value)
