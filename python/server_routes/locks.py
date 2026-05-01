"""Admin route and startup hook for stale speaker lock cleanup."""
from __future__ import annotations

import math
import os
from pathlib import Path
import sys
from typing import Any, Dict

import server as _server
from ai.speaker_locks import cleanup_stale_locks


def _locks_dir() -> Path:
    raw = os.environ.get("PARSE_LOCKS_DIR", "").strip() or ".parse-locks"
    configured = Path(raw)
    if configured.is_absolute():
        return configured
    return (_server._project_root() / configured).resolve()


def _stale_lock_age_sec() -> float:
    """Read PARSE_STALE_LOCK_AGE_SEC; default to 1h on missing/invalid values."""
    raw = os.environ.get("PARSE_STALE_LOCK_AGE_SEC", "").strip()
    if not raw:
        return 3600.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 3600.0
    return value if value > 0 and math.isfinite(value) else 3600.0


def _cleanup_stale_locks_on_startup() -> Dict[str, Any]:
    result = cleanup_stale_locks(_locks_dir(), stale_age_sec=_stale_lock_age_sec())
    cleaned = result.get("cleaned") if isinstance(result, dict) else []
    reasons = result.get("reasons") if isinstance(result, dict) else {}
    if cleaned:
        print(
            "[STARTUP] cleaned {0} stale speaker lock(s): {1}".format(
                len(cleaned), ", ".join(str(item) for item in cleaned)
            ),
            file=sys.stderr,
            flush=True,
        )
    if isinstance(reasons, dict):
        manual_review = [speaker for speaker, reason in reasons.items() if "manual review" in str(reason)]
        if manual_review:
            print(
                "[STARTUP] speaker lock(s) need manual review: {0}".format(
                    ", ".join(str(item) for item in manual_review)
                ),
                file=sys.stderr,
                flush=True,
            )
    return result


def _api_post_locks_cleanup(self) -> None:
    try:
        payload = cleanup_stale_locks(_locks_dir(), stale_age_sec=_stale_lock_age_sec())
    except Exception as exc:
        payload = {"cleaned": [], "skipped": [], "reasons": {"__cleanup__": "cleanup failed: {0}".format(exc)}}
    self._send_json(_server.HTTPStatus.OK, payload)


__all__ = ["_api_post_locks_cleanup", "_cleanup_stale_locks_on_startup", "_locks_dir", "_stale_lock_age_sec"]
