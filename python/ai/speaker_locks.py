"""Filesystem-backed speaker lock helpers for PARSE jobs.

The active server also keeps an in-memory job table, but crashed workers can
leave legacy ``*.lock`` files behind.  This module owns the narrow, safe cleanup
surface: it records lock creator metadata and deletes only stale lock files in a
configured locks directory.  It never terminates processes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict

DEFAULT_STALE_LOCK_AGE_SEC = 3600.0
LOCK_FILE_SUFFIX = ".lock"


class SpeakerLockError(RuntimeError):
    """Raised when a speaker lock cannot be acquired."""


def _lock_path_for_speaker(locks_dir: Path, speaker: str) -> Path:
    speaker_id = str(speaker or "").strip()
    if not speaker_id or speaker_id in {".", ".."}:
        raise ValueError("speaker must be a non-empty filename-safe identifier")
    if "/" in speaker_id or "\\" in speaker_id or Path(speaker_id).name != speaker_id:
        raise ValueError("speaker lock names cannot contain path separators")
    return Path(locks_dir) / f"{speaker_id}{LOCK_FILE_SUFFIX}"


def acquire_speaker_lock(speaker: str, locks_dir: Path) -> Path:
    """Create a JSON speaker lock with creator PID and creation timestamp.

    The file is created with O_EXCL so two server threads/processes cannot both
    acquire the same speaker.  Callers keep their existing release behavior:
    releasing a lock is just unlinking the file.
    """
    lock_file = _lock_path_for_speaker(Path(locks_dir), speaker)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "speaker": str(speaker or "").strip(),
        "creator_pid": os.getpid(),
        "created_at_unix": time.time(),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(lock_file, flags, 0o644)
    except FileExistsError as exc:
        raise SpeakerLockError("speaker {0} already locked".format(payload["speaker"])) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    except Exception:
        try:
            lock_file.unlink()
        except OSError:
            pass
        raise
    return lock_file


def release_speaker_lock(speaker: str, locks_dir: Path) -> None:
    """Release a speaker lock by deleting its lock file if present."""
    try:
        _lock_path_for_speaker(Path(locks_dir), speaker).unlink()
    except FileNotFoundError:
        return


def _read_lock_metadata(lock_file: Path) -> tuple[str, int, float, bool]:
    try:
        payload = json.loads(lock_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("lock payload is not an object")
        speaker = str(payload.get("speaker") or lock_file.stem).strip() or lock_file.stem
        pid = int(payload.get("creator_pid") or 0)
        created_at = float(payload.get("created_at_unix") or 0.0)
        if pid <= 0 and created_at <= 0:
            raise ValueError("legacy lock missing metadata")
        return (speaker, pid, created_at, True)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return (lock_file.stem, 0, 0.0, False)


def cleanup_stale_locks(locks_dir: Path, *, stale_age_sec: float = DEFAULT_STALE_LOCK_AGE_SEC) -> Dict[str, Any]:
    """Remove stale speaker ``*.lock`` files from ``locks_dir`` only.

    Backward compatibility: legacy touch-files or unreadable/non-JSON lock files
    have no trustworthy creator metadata, so they are treated as stale and are
    cleaned on boot.  Cleanup never kills processes.  If a PID is still running
    but the lock is older than ``stale_age_sec``, the lock is kept and marked for
    manual review rather than terminating or deleting under an active process.
    """
    cleaned: list[str] = []
    skipped: list[str] = []
    reasons: dict[str, str] = {}
    root = Path(locks_dir)
    if not root.is_dir():
        return {"cleaned": cleaned, "skipped": skipped, "reasons": reasons}

    try:
        stale_age = float(stale_age_sec)
    except (TypeError, ValueError):
        stale_age = DEFAULT_STALE_LOCK_AGE_SEC
    if stale_age <= 0:
        stale_age = DEFAULT_STALE_LOCK_AGE_SEC

    now = time.time()
    for lock_file in sorted(root.glob(f"*{LOCK_FILE_SUFFIX}")):
        if not lock_file.is_file():
            continue
        speaker, pid, created_at, has_metadata = _read_lock_metadata(lock_file)
        age_sec = max(0.0, now - created_at) if created_at > 0 else 0.0

        if pid > 0 and _pid_is_running(pid):
            skipped.append(speaker)
            if age_sec > stale_age:
                reasons[speaker] = (
                    "active PID {0} but age {1:.0f}s exceeds {2:.0f}s; manual review".format(
                        pid,
                        age_sec,
                        stale_age,
                    )
                )
            else:
                reasons[speaker] = "active PID {0}, age {1:.0f}s".format(pid, age_sec)
            continue

        try:
            lock_file.unlink()
            cleaned.append(speaker)
            if has_metadata:
                reasons[speaker] = "PID {0} not running".format(pid)
            else:
                reasons[speaker] = "legacy/unreadable lock"
        except OSError as exc:
            skipped.append(speaker)
            reasons[speaker] = "unlink failed: {0}".format(exc)

    return {"cleaned": cleaned, "skipped": skipped, "reasons": reasons}


def _pid_is_running(pid: int) -> bool:
    """Return True when ``pid`` exists; cross-platform and non-destructive."""
    try:
        normalized_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if normalized_pid <= 0:
        return False

    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "PID eq {0}".format(normalized_pid), "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.SubprocessError:
            return False
        return str(normalized_pid) in result.stdout

    try:
        os.kill(normalized_pid, 0)
        return True
    except OSError:
        return False


__all__ = [
    "DEFAULT_STALE_LOCK_AGE_SEC",
    "LOCK_FILE_SUFFIX",
    "SpeakerLockError",
    "acquire_speaker_lock",
    "cleanup_stale_locks",
    "release_speaker_lock",
    "_pid_is_running",
]
