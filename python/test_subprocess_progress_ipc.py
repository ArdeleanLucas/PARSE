from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_job_state(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    monkeypatch.setenv("PARSE_JOB_SNAPSHOT_DIR", str(tmp_path / "job-snapshots"))
    monkeypatch.delenv("PARSE_COMPUTE_CHECKPOINT_LOG", raising=False)
    monkeypatch.setattr(server, "_COMPUTE_CHECKPOINT_LOG_PATH", None, raising=False)
    monkeypatch.setattr(server, "_COMPUTE_CHECKPOINT_FD", None, raising=False)
    server._jobs.clear()
    yield
    server._jobs.clear()
    monkeypatch.delenv("PARSE_COMPUTE_CHECKPOINT_LOG", raising=False)
    monkeypatch.setattr(server, "_COMPUTE_CHECKPOINT_LOG_PATH", None, raising=False)
    fd = getattr(server, "_COMPUTE_CHECKPOINT_FD", None)
    if isinstance(fd, int):
        try:
            os.close(fd)
        except OSError:
            pass
    monkeypatch.setattr(server, "_COMPUTE_CHECKPOINT_FD", None, raising=False)


def _append_jsonl(path: pathlib.Path, record: dict[str, Any], *, newline: bool = True) -> None:
    with path.open("ab") as handle:
        handle.write(json.dumps(record).encode("utf-8"))
        if newline:
            handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.025)
    return predicate()


def _start_watcher(parent_job_id: str, checkpoint_path: pathlib.Path, *, initial_offset: int = 0):
    stop_event = threading.Event()
    watcher = threading.Thread(
        target=server._watch_progress_file,
        args=(parent_job_id, str(checkpoint_path), stop_event, initial_offset),
        daemon=True,
    )
    watcher.start()
    return stop_event, watcher


def test_progress_record_written_inside_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    monkeypatch.setenv("PARSE_COMPUTE_CHECKPOINT_LOG", str(checkpoint_path))
    monkeypatch.setattr(server, "_COMPUTE_CHECKPOINT_LOG_PATH", None, raising=False)
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: calls.append((args, kwargs)))

    server._publish_progress(
        "child-test",
        42.0,
        "midway",
        segments_processed=7,
        total_segments=12,
    )

    assert calls
    records = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    record = records[0]
    assert record["kind"] == "progress"
    assert record["job_id"] == "child-test"
    assert record["progress"] == 42.0
    assert record["message"] == "midway"
    assert record["segments_processed"] == 7
    assert record["total_segments"] == 12
    assert isinstance(record["ts"], float)


def test_publish_progress_no_op_outside_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.delenv("PARSE_COMPUTE_CHECKPOINT_LOG", raising=False)
    monkeypatch.setattr(server, "_COMPUTE_CHECKPOINT_LOG_PATH", None, raising=False)
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: calls.append((args, kwargs)))

    server._publish_progress("job-parent", 12.5, "local only")

    assert calls == [(('job-parent', 12.5), {'message': 'local only'})]
    assert not list(tmp_path.glob("*.jsonl"))


def test_watcher_bridges_progress_to_parent_snapshot(tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    parent_job_id = server._create_job("compute:stt", {"speaker": "Fail01"})
    stop_event, watcher = _start_watcher(parent_job_id, checkpoint_path)

    _append_jsonl(checkpoint_path, {"kind": "progress", "job_id": "child-a", "progress": 15.0, "message": "first"})
    time.sleep(0.1)
    _append_jsonl(
        checkpoint_path,
        {
            "kind": "progress",
            "job_id": "child-a",
            "progress": 37.5,
            "message": "second",
            "segments_processed": 4,
            "total_segments": 10,
        },
    )

    assert _wait_for(lambda: server._get_job_snapshot(parent_job_id)["progress"] == pytest.approx(37.5))
    snapshot = server._get_job_snapshot(parent_job_id)
    assert snapshot["message"] == "second"
    assert snapshot["segmentsProcessed"] == 4
    assert snapshot["totalSegments"] == 10
    stop_event.set()
    watcher.join(timeout=2.0)
    assert not watcher.is_alive()


def test_watcher_ignores_non_progress_records(tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    parent_job_id = server._create_job("compute:stt", {"speaker": "Fail01"})
    stop_event, watcher = _start_watcher(parent_job_id, checkpoint_path)

    _append_jsonl(checkpoint_path, {"label": "STT_CHILD.entry", "job_id": "child-a", "progress": 80.0})
    _append_jsonl(checkpoint_path, {"kind": "checkpoint", "job_id": "child-a", "progress": 90.0})
    time.sleep(0.35)

    snapshot = server._get_job_snapshot(parent_job_id)
    assert snapshot["progress"] == 0.0
    assert snapshot.get("message") is None
    stop_event.set()
    watcher.join(timeout=2.0)
    assert not watcher.is_alive()


def test_watcher_translates_child_job_id_to_parent(tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    parent_job_id = server._create_job("compute:stt", {"speaker": "Fail01"})
    child_job_id = "child-XYZ-stt"
    stop_event, watcher = _start_watcher(parent_job_id, checkpoint_path)

    _append_jsonl(checkpoint_path, {"kind": "progress", "job_id": child_job_id, "progress": 55.0, "message": "child tick"})

    assert _wait_for(lambda: server._get_job_snapshot(parent_job_id)["progress"] == pytest.approx(55.0))
    assert server._get_job_snapshot(child_job_id) is None
    stop_event.set()
    watcher.join(timeout=2.0)
    assert not watcher.is_alive()


def test_watcher_handles_partial_line_at_eof(tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    parent_job_id = server._create_job("compute:stt", {"speaker": "Fail01"})
    stop_event, watcher = _start_watcher(parent_job_id, checkpoint_path)
    record = {"kind": "progress", "job_id": "child-a", "progress": 22.0, "message": "partial"}

    _append_jsonl(checkpoint_path, record, newline=False)
    time.sleep(0.35)
    assert server._get_job_snapshot(parent_job_id)["progress"] == 0.0

    with checkpoint_path.open("ab") as handle:
        handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())

    assert _wait_for(lambda: server._get_job_snapshot(parent_job_id)["progress"] == pytest.approx(22.0))
    stop_event.set()
    watcher.join(timeout=2.0)
    assert not watcher.is_alive()


def test_watcher_torndown_on_join(tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    parent_job_id = server._create_job("compute:stt", {"speaker": "Fail01"})
    stop_event, watcher = _start_watcher(parent_job_id, checkpoint_path)

    def writer() -> None:
        for idx in range(3):
            _append_jsonl(
                checkpoint_path,
                {"kind": "progress", "job_id": "child-a", "progress": 10.0 + idx, "message": f"tick-{idx}"},
            )
            time.sleep(0.05)

    child = threading.Thread(target=writer)
    child.start()
    child.join(timeout=2.0)
    stop_event.set()
    watcher.join(timeout=2.0)

    assert not child.is_alive()
    assert not watcher.is_alive()
    assert server._get_job_snapshot(parent_job_id)["progress"] == pytest.approx(12.0)


def test_watcher_torndown_on_timeout(tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    parent_job_id = server._create_job("compute:stt", {"speaker": "Fail01"})
    stop_event, watcher = _start_watcher(parent_job_id, checkpoint_path)
    child_stop = threading.Event()

    def writer() -> None:
        _append_jsonl(checkpoint_path, {"kind": "progress", "job_id": "child-a", "progress": 66.0, "message": "before timeout"})
        child_stop.wait(5.0)

    child = threading.Thread(target=writer)
    child.start()
    assert _wait_for(lambda: server._get_job_snapshot(parent_job_id)["progress"] == pytest.approx(66.0))
    child_stop.set()
    stop_event.set()
    child.join(timeout=2.0)
    watcher.join(timeout=2.0)

    assert not child.is_alive()
    assert not watcher.is_alive()


def test_e2e_stt_chunked_progress_visible_to_parent(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    monkeypatch.setenv("PARSE_COMPUTE_CHECKPOINT_LOG", str(checkpoint_path))
    monkeypatch.setattr(server, "_COMPUTE_CHECKPOINT_LOG_PATH", None, raising=False)
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "5")

    import multiprocessing

    class _ThreadProcess:
        def __init__(self, target, name=None, args=(), daemon=None):
            self._target = target
            self._args = args
            self.name = name
            self.daemon = daemon
            self.pid = 12345
            self.exitcode: int | None = None
            self._thread = threading.Thread(target=self._run, daemon=True)

        def _run(self) -> None:
            try:
                self._target(*self._args)
                self.exitcode = 0
            except BaseException:
                self.exitcode = 1
                raise

        def start(self) -> None:
            self._thread.start()

        def join(self, timeout=None) -> None:
            self._thread.join(timeout=timeout)

        def is_alive(self) -> bool:
            return self._thread.is_alive()

        def terminate(self) -> None:
            self.exitcode = -15

    class _ThreadContext:
        Process = _ThreadProcess

    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _ThreadContext())

    def fake_stt(child_job_id: str, payload: dict[str, Any], result_path: str, checkpoint: str) -> None:
        os.environ["PARSE_COMPUTE_CHECKPOINT_LOG"] = checkpoint
        server._publish_progress(child_job_id, 20.0, "STT chunk 1/2", segments_processed=3)
        time.sleep(0.35)
        with open(result_path, "w", encoding="utf-8") as handle:
            json.dump({"ok": True, "result": {"speaker": payload["speaker"], "segments": [], "chunks": []}}, handle)

    parent_job_id = server._create_job("compute:stt", {"speaker": "Fail01"})
    result_holder: dict[str, Any] = {}

    def run_parent() -> None:
        result_holder["result"] = server._run_in_isolated_subprocess(
            parent_job_id,
            {"speaker": "Fail01"},
            subprocess_entry=fake_stt,
            log_prefix="STT_SUBPROCESS",
            result_file_prefix="parse-stt-test-",
        )

    parent_thread = threading.Thread(target=run_parent)
    parent_thread.start()

    assert _wait_for(lambda: server._get_job_snapshot(parent_job_id)["progress"] == pytest.approx(20.0))
    mid_snapshot = server._get_job_snapshot(parent_job_id)
    assert mid_snapshot["message"] == "STT chunk 1/2"
    assert mid_snapshot["segmentsProcessed"] == 3
    parent_thread.join(timeout=2.0)
    assert not parent_thread.is_alive()
    assert result_holder["result"]["speaker"] == "Fail01"
