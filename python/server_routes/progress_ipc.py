from __future__ import annotations

import json

import server as _server


def _compute_progress(
    job_id: str,
    progress: float,
    message: _server.Optional[str] = None,
    *,
    segments_processed: _server.Optional[int] = None,
    total_segments: _server.Optional[int] = None,
) -> None:
    """Append one subprocess progress JSONL record to the checkpoint log.

    This is a no-op unless ``PARSE_COMPUTE_CHECKPOINT_LOG`` is present. Parent
    processes may have a default checkpoint path for crash diagnostics; progress
    IPC is only active in children whose entry point received the parent's path.
    """
    raw_path = _server.os.environ.get("PARSE_COMPUTE_CHECKPOINT_LOG", "").strip()
    if not raw_path:
        return
    try:
        record: _server.Dict[str, _server.Any] = {
            "kind": "progress",
            "ts": _server.time.time(),
            "job_id": str(job_id),
            "progress": float(progress),
            "message": message,
        }
        if segments_processed is not None:
            record["segments_processed"] = int(segments_processed)
        if total_segments is not None:
            record["total_segments"] = int(total_segments)
        line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        with _server._COMPUTE_CHECKPOINT_LOCK:
            fd = _server.os.open(raw_path, _server.os.O_WRONLY | _server.os.O_APPEND | _server.os.O_CREAT, 0o644)
            try:
                _server.os.write(fd, line)
                try:
                    _server.os.fsync(fd)
                except OSError:
                    pass
            finally:
                try:
                    _server.os.close(fd)
                except OSError:
                    pass
    except Exception as exc:
        try:
            _server.sys.stderr.write("[compute_progress] write failed: {0}\n".format(exc))
            _server.sys.stderr.flush()
        except Exception:
            pass


def _apply_progress_record(parent_job_id: str, record: _server.Dict[str, _server.Any]) -> None:
    if record.get("kind") != "progress":
        return
    try:
        progress = float(record.get("progress") or 0.0)
    except (TypeError, ValueError):
        return
    kwargs: _server.Dict[str, _server.Any] = {}
    if record.get("segments_processed") is not None:
        kwargs["segments_processed"] = record.get("segments_processed")
    if record.get("total_segments") is not None:
        kwargs["total_segments"] = record.get("total_segments")
    try:
        _server._set_job_progress(parent_job_id, progress, message=record.get("message"), **kwargs)
    except Exception:
        # Progress IPC is observability-only; watcher failures must not affect
        # subprocess lifecycle or result handling.
        pass


def _process_progress_chunk(parent_job_id: str, pending: bytes, chunk: bytes) -> bytes:
    data = pending + chunk
    if not data:
        return b""
    lines = data.split(b"\n")
    if data.endswith(b"\n"):
        complete_lines = lines[:-1]
        remainder = b""
    else:
        complete_lines = lines[:-1]
        remainder = lines[-1]
    for raw_line in complete_lines:
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            _apply_progress_record(parent_job_id, record)
    return remainder


def _watch_progress_file(
    parent_job_id: str,
    checkpoint_path: str,
    stop_event: _server.threading.Event,
    initial_offset: int,
) -> None:
    """Tail checkpoint JSONL progress records into the parent's job snapshot."""
    poll_interval = 0.25
    offset = max(0, int(initial_offset or 0))
    pending = b""
    while not stop_event.is_set():
        try:
            size = _server.os.path.getsize(checkpoint_path)
        except OSError:
            stop_event.wait(poll_interval)
            continue
        if size < offset:
            offset = 0
            pending = b""
        if size > offset:
            try:
                with open(checkpoint_path, "rb") as handle:
                    handle.seek(offset)
                    chunk = handle.read(size - offset)
                offset = size
                pending = _process_progress_chunk(parent_job_id, pending, chunk)
            except OSError:
                pass
        stop_event.wait(poll_interval)
    try:
        size = _server.os.path.getsize(checkpoint_path)
        if size < offset:
            offset = 0
            pending = b""
        if size > offset:
            with open(checkpoint_path, "rb") as handle:
                handle.seek(offset)
                chunk = handle.read(size - offset)
            _process_progress_chunk(parent_job_id, pending, chunk)
    except OSError:
        pass


def _publish_progress(
    job_id: str,
    progress: float,
    message: _server.Optional[str] = None,
    *,
    segments_processed: _server.Optional[int] = None,
    total_segments: _server.Optional[int] = None,
) -> None:
    """Set local job progress and mirror it to checkpoint JSONL in children."""
    kwargs: _server.Dict[str, _server.Any] = {}
    if segments_processed is not None:
        kwargs["segments_processed"] = segments_processed
    if total_segments is not None:
        kwargs["total_segments"] = total_segments
    _server._set_job_progress(job_id, progress, message=message, **kwargs)
    if _server.os.environ.get("PARSE_COMPUTE_CHECKPOINT_LOG"):
        _compute_progress(
            job_id,
            progress,
            message,
            segments_processed=segments_processed,
            total_segments=total_segments,
        )


__all__ = [
    "_compute_progress",
    "_watch_progress_file",
    "_publish_progress",
]
