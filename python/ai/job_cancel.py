"""Thread-safe cooperative cancellation flags for PARSE background jobs."""
from __future__ import annotations

import threading
from typing import Callable

_CANCELLED_JOBS: set[str] = set()
_CANCEL_LOCK = threading.RLock()


def _normalize_job_id(job_id: str) -> str:
    return str(job_id or "").strip()


def request_cancel(job_id: str) -> bool:
    """Mark ``job_id`` for cancellation.

    Returns True when this call created the flag and False when the job was
    already flagged. Unknown/empty identifiers are ignored safely.
    """
    normalized = _normalize_job_id(job_id)
    if not normalized:
        return False
    with _CANCEL_LOCK:
        already_cancelled = normalized in _CANCELLED_JOBS
        _CANCELLED_JOBS.add(normalized)
        return not already_cancelled


def is_cancelled(job_id: str) -> bool:
    """Return whether ``job_id`` has been flagged for cancellation."""
    normalized = _normalize_job_id(job_id)
    if not normalized:
        return False
    with _CANCEL_LOCK:
        return normalized in _CANCELLED_JOBS


def clear_cancel(job_id: str) -> None:
    """Remove any cancellation flag for ``job_id``."""
    normalized = _normalize_job_id(job_id)
    if not normalized:
        return
    with _CANCEL_LOCK:
        _CANCELLED_JOBS.discard(normalized)


def make_should_cancel(job_id: str) -> Callable[[], bool]:
    """Return a zero-arg predicate bound to ``job_id``."""
    normalized = _normalize_job_id(job_id)

    def _should_cancel() -> bool:
        return is_cancelled(normalized)

    return _should_cancel
