import json
import os
import pathlib
import sys
import time
from http import HTTPStatus
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server
from ai import speaker_locks
from server_routes import locks as lock_routes


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, path: str = "/api/locks/cleanup"):
        self.path = path
        self.sent = []

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


def _write_lock(locks_dir: pathlib.Path, speaker: str, *, pid: int, created_at: float) -> pathlib.Path:
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_file = locks_dir / f"{speaker}.lock"
    lock_file.write_text(
        json.dumps({"speaker": speaker, "creator_pid": pid, "created_at_unix": created_at}),
        encoding="utf-8",
    )
    return lock_file


def test_acquire_speaker_lock_writes_pid_and_created_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(speaker_locks.os, "getpid", lambda: 4242)
    monkeypatch.setattr(speaker_locks.time, "time", lambda: 1234.5)

    lock_file = speaker_locks.acquire_speaker_lock("Fail01", tmp_path)

    assert lock_file == tmp_path / "Fail01.lock"
    payload = json.loads(lock_file.read_text(encoding="utf-8"))
    assert payload == {"speaker": "Fail01", "creator_pid": 4242, "created_at_unix": 1234.5}


def test_cleanup_removes_lock_with_dead_pid(tmp_path, monkeypatch) -> None:
    lock_file = _write_lock(tmp_path, "Fail01", pid=999999, created_at=time.time())
    monkeypatch.setattr(speaker_locks, "_pid_is_running", lambda pid: False)

    result = speaker_locks.cleanup_stale_locks(tmp_path, stale_age_sec=3600.0)

    assert not lock_file.exists()
    assert result["cleaned"] == ["Fail01"]
    assert result["skipped"] == []
    assert "not running" in result["reasons"]["Fail01"]


def test_cleanup_keeps_lock_with_live_pid(tmp_path, monkeypatch) -> None:
    lock_file = _write_lock(tmp_path, "Fail02", pid=12345, created_at=1000.0)
    monkeypatch.setattr(speaker_locks.time, "time", lambda: 1010.0)
    monkeypatch.setattr(speaker_locks, "_pid_is_running", lambda pid: True)

    result = speaker_locks.cleanup_stale_locks(tmp_path, stale_age_sec=3600.0)

    assert lock_file.exists()
    assert result["cleaned"] == []
    assert result["skipped"] == ["Fail02"]
    assert result["reasons"]["Fail02"].startswith("active PID 12345")


def test_cleanup_removes_lock_older_than_threshold(tmp_path) -> None:
    lock_file = _write_lock(tmp_path, "Fail03", pid=0, created_at=time.time() - 7200.0)

    result = speaker_locks.cleanup_stale_locks(tmp_path, stale_age_sec=3600.0)

    assert not lock_file.exists()
    assert result["cleaned"] == ["Fail03"]


def test_cleanup_keeps_ancient_live_pid_for_manual_review(tmp_path, monkeypatch) -> None:
    lock_file = _write_lock(tmp_path, "Fail04", pid=12345, created_at=1000.0)
    monkeypatch.setattr(speaker_locks.time, "time", lambda: 8200.0)
    monkeypatch.setattr(speaker_locks, "_pid_is_running", lambda pid: True)

    result = speaker_locks.cleanup_stale_locks(tmp_path, stale_age_sec=3600.0)

    assert lock_file.exists()
    assert result["cleaned"] == []
    assert result["skipped"] == ["Fail04"]
    assert "manual review" in result["reasons"]["Fail04"]


def test_cleanup_treats_legacy_touch_file_as_stale(tmp_path) -> None:
    lock_file = tmp_path / "Legacy01.lock"
    lock_file.touch()

    result = speaker_locks.cleanup_stale_locks(tmp_path, stale_age_sec=3600.0)

    assert not lock_file.exists()
    assert result["cleaned"] == ["Legacy01"]
    assert result["reasons"]["Legacy01"] == "legacy/unreadable lock"


def test_cleanup_skips_directory_traversal(tmp_path, monkeypatch) -> None:
    locks_dir = tmp_path / "locks"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_lock = _write_lock(outside_dir, "Outside01", pid=0, created_at=0.0)
    inside_lock = _write_lock(locks_dir, "Inside01", pid=0, created_at=0.0)
    monkeypatch.setattr(speaker_locks, "_pid_is_running", lambda pid: False)

    result = speaker_locks.cleanup_stale_locks(locks_dir, stale_age_sec=3600.0)

    assert not inside_lock.exists()
    assert outside_lock.exists()
    assert result["cleaned"] == ["Inside01"]


def test_cleanup_endpoint_returns_dict_payload(tmp_path, monkeypatch) -> None:
    expected = {"cleaned": ["Saha01"], "skipped": ["Fail02"], "reasons": {"Fail02": "active PID 12345"}}
    observed = {}

    def fake_cleanup(locks_dir, *, stale_age_sec):
        observed["locks_dir"] = pathlib.Path(locks_dir)
        observed["stale_age_sec"] = stale_age_sec
        return expected

    monkeypatch.setenv("PARSE_LOCKS_DIR", str(tmp_path))
    monkeypatch.setenv("PARSE_STALE_LOCK_AGE_SEC", "42")
    monkeypatch.setattr(lock_routes, "cleanup_stale_locks", fake_cleanup)

    handler = _HandlerHarness()
    handler._dispatch_api_post("/api/locks/cleanup")

    assert handler.sent == [(HTTPStatus.OK, expected)]
    assert observed == {"locks_dir": tmp_path, "stale_age_sec": 42.0}


def test_pid_is_running_unix(monkeypatch) -> None:
    calls = []

    def fake_kill(pid: int, sig: int) -> None:
        calls.append((pid, sig))
        if pid == 222:
            raise ProcessLookupError()

    monkeypatch.setattr(speaker_locks.sys, "platform", "linux")
    monkeypatch.setattr(speaker_locks.os, "kill", fake_kill)

    assert speaker_locks._pid_is_running(111) is True
    assert speaker_locks._pid_is_running(222) is False
    assert calls == [(111, 0), (222, 0)]


def test_pid_is_running_windows(monkeypatch) -> None:
    def fake_run(args, capture_output, text, timeout):
        assert args == ["tasklist", "/FI", "PID eq 3408", "/FO", "CSV"]
        assert capture_output is True
        assert text is True
        assert timeout == 5
        return SimpleNamespace(stdout='"python.exe","3408","Console","1","123,456 K"')

    monkeypatch.setattr(speaker_locks.sys, "platform", "win32")
    monkeypatch.setattr(speaker_locks.subprocess, "run", fake_run)

    assert speaker_locks._pid_is_running(3408) is True


def test_startup_hook_calls_cleanup(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_cleanup(locks_dir, *, stale_age_sec):
        calls.append((pathlib.Path(locks_dir), stale_age_sec))
        return {"cleaned": ["Fail01"], "skipped": [], "reasons": {"Fail01": "PID 3408 not running"}}

    monkeypatch.setenv("PARSE_LOCKS_DIR", str(tmp_path))
    monkeypatch.setenv("PARSE_STALE_LOCK_AGE_SEC", "3600")
    monkeypatch.setattr(lock_routes, "cleanup_stale_locks", fake_cleanup)

    result = server._cleanup_stale_locks_on_startup()

    assert result["cleaned"] == ["Fail01"]
    assert calls == [(tmp_path, 3600.0)]
