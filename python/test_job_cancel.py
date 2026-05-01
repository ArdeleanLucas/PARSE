from __future__ import annotations

import threading

from ai.job_cancel import clear_cancel, is_cancelled, make_should_cancel, request_cancel


def test_request_cancel_and_is_cancelled_round_trip() -> None:
    job_id = "job-cancel-round-trip"
    clear_cancel(job_id)

    assert is_cancelled(job_id) is False
    assert request_cancel(job_id) is True
    assert is_cancelled(job_id) is True
    assert request_cancel(job_id) is False

    clear_cancel(job_id)
    assert is_cancelled(job_id) is False


def test_clear_cancel_removes_flag() -> None:
    job_id = "job-cancel-clear"
    request_cancel(job_id)

    clear_cancel(job_id)

    assert is_cancelled(job_id) is False


def test_make_should_cancel_reflects_registry_state() -> None:
    job_id = "job-cancel-callable"
    clear_cancel(job_id)
    should_cancel = make_should_cancel(job_id)

    assert should_cancel() is False
    request_cancel(job_id)
    assert should_cancel() is True
    clear_cancel(job_id)
    assert should_cancel() is False


def test_cancel_registry_is_thread_safe_for_concurrent_requests() -> None:
    job_id = "job-cancel-threaded"
    clear_cancel(job_id)
    errors: list[BaseException] = []
    observations: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            request_cancel(job_id)
            value = is_cancelled(job_id)
            with lock:
                observations.append(value)
        except BaseException as exc:  # pragma: no cover - failure reporting
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2.0)

    assert errors == []
    assert observations
    assert all(observations)
    assert is_cancelled(job_id) is True
    clear_cancel(job_id)
