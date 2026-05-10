from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

from app.http.lexeme_rerun_handlers import LexemeRerunSubprocessError
from server_routes import lexeme_rerun


class _FakeProcess:
    def __init__(
        self,
        *,
        target: Callable[..., None],
        name: str,
        args: tuple[Any, ...],
        daemon: bool,
        exitcode: int | None,
        write_success: bool = False,
        write_log: bool = False,
        stay_alive: bool = False,
    ) -> None:
        self.target = target
        self.name = name
        self.args = args
        self.daemon = daemon
        self.exitcode = exitcode
        self.write_success = write_success
        self.write_log = write_log
        self.stay_alive = stay_alive
        self.pid = 4321
        self.terminated = False
        self.started = False

    def start(self) -> None:
        self.started = True
        if self.write_log:
            kind = str(self.args[0])
            Path(f"/tmp/parse-lexeme-rerun-{kind}-{self.pid}.log").write_text(
                "DIAGNOSTIC_SMOKE_TEST: about to crash on purpose\n",
                encoding="utf-8",
            )
        if self.write_success:
            result_path = Path(self.args[2])
            result_path.write_text(json.dumps({"ok": True, "result": "ʃ"}), encoding="utf-8")

    def join(self, timeout: float | None = None) -> None:
        _ = timeout

    def is_alive(self) -> bool:
        return self.stay_alive and not self.terminated

    def terminate(self) -> None:
        self.terminated = True
        self.exitcode = -9


class _FakeContext:
    def __init__(self, process: _FakeProcess) -> None:
        self.process = process

    def Process(self, *, target: Callable[..., None], name: str, args: tuple[Any, ...], daemon: bool) -> _FakeProcess:
        self.process.target = target
        self.process.name = name
        self.process.args = args
        self.process.daemon = daemon
        return self.process


def _install_fake_process(monkeypatch: pytest.MonkeyPatch, process: _FakeProcess) -> None:
    monkeypatch.setattr("multiprocessing.get_context", lambda method: _FakeContext(process))


class _ForkedProcess:
    """Minimal real child process that preserves monkeypatches via fork()."""

    def __init__(self, *, target: Callable[..., None], name: str, args: tuple[Any, ...], daemon: bool) -> None:
        self.target = target
        self.name = name
        self.args = args
        self.daemon = daemon
        self.pid: int | None = None
        self.exitcode: int | None = None
        self._waited = False

    def start(self) -> None:
        pid = os.fork()
        if pid == 0:
            try:
                self.target(*self.args)
            except BaseException:  # pragma: no cover - defensive child hard-exit path
                os._exit(1)
            os._exit(0)
        self.pid = pid

    def join(self, timeout: float | None = None) -> None:
        _ = timeout
        if self.pid is None or self._waited:
            return
        _, status = os.waitpid(self.pid, 0)
        self._waited = True
        self.exitcode = os.waitstatus_to_exitcode(status)

    def is_alive(self) -> bool:
        if self.pid is None or self._waited:
            return False
        try:
            waited_pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            self._waited = True
            return False
        if waited_pid == 0:
            return True
        self._waited = True
        self.exitcode = os.waitstatus_to_exitcode(status)
        return False

    def terminate(self) -> None:
        if self.pid is not None and not self._waited:
            os.kill(self.pid, 9)


class _ForkedContext:
    def Process(self, *, target: Callable[..., None], name: str, args: tuple[Any, ...], daemon: bool) -> _ForkedProcess:
        return _ForkedProcess(target=target, name=name, args=args, daemon=daemon)


def _install_forked_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("multiprocessing.get_context", lambda method: _ForkedContext())


@contextmanager
def _capture_fd(fd: int) -> Iterator[Callable[[], str]]:
    sys.stdout.flush()
    sys.stderr.flush()
    read_fd, write_fd = os.pipe()
    saved_fd = os.dup(fd)
    os.dup2(write_fd, fd)
    os.close(write_fd)
    output = ""

    def read_output() -> str:
        return output

    try:
        yield read_output
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_fd, fd)
        os.close(saved_fd)
        chunks: list[bytes] = []
        try:
            while True:
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(read_fd)
        output = b"".join(chunks).decode("utf-8", errors="replace")


def test_lexeme_subprocess_success_returns_child_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    process = _FakeProcess(target=lambda: None, name="", args=(), daemon=True, exitcode=0, write_success=True)
    _install_fake_process(monkeypatch, process)

    result = lexeme_rerun._run_ipa_interval_in_subprocess(
        audio_path=audio_path,
        start=1.0,
        end=1.2,
        language="sdh",
    )

    assert result == "ʃ"
    assert process.started is True
    assert process.name == "parse-lexeme-rerun-ipa"


def test_child_stderr_reaches_parent_fd2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    line = "[ORTH] concept-window 1/1 concept='c1' → 'hello'"

    def fake_ortho_interval(**kwargs: Any) -> str:
        _ = kwargs
        print(line, file=sys.stderr)
        return "hello"

    monkeypatch.setattr(lexeme_rerun, "_run_ortho_interval", fake_ortho_interval)
    _install_forked_process(monkeypatch)

    with _capture_fd(2) as captured:
        result = lexeme_rerun._run_ortho_interval_in_subprocess(audio_path=audio_path, start=1.0, end=1.2)

    assert result == "hello"
    assert line in captured()


def test_child_stdout_reaches_parent_fd1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    line = "[ORTH] stdout concept-window 1/1 concept='c1' → 'hello'"

    def fake_ortho_interval(**kwargs: Any) -> str:
        _ = kwargs
        print(line)
        return "hello"

    monkeypatch.setattr(lexeme_rerun, "_run_ortho_interval", fake_ortho_interval)
    _install_forked_process(monkeypatch)

    with _capture_fd(1) as captured:
        result = lexeme_rerun._run_ortho_interval_in_subprocess(audio_path=audio_path, start=1.0, end=1.2)

    assert result == "hello"
    assert line in captured()


def test_child_log_still_captured_on_failure_and_tee_reaches_parent_fd2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    line_1 = "[ORTH] failure diagnostic before model call"
    line_2 = "[ORTH] failure diagnostic after model call"

    def fake_ortho_interval(**kwargs: Any) -> str:
        _ = kwargs
        print(line_1, file=sys.stderr)
        print(line_2, file=sys.stderr)
        raise RuntimeError("boom")

    monkeypatch.setattr(lexeme_rerun, "_run_ortho_interval", fake_ortho_interval)
    _install_forked_process(monkeypatch)

    with _capture_fd(2) as captured:
        with pytest.raises(LexemeRerunSubprocessError) as exc_info:
            lexeme_rerun._run_ortho_interval_in_subprocess(audio_path=audio_path, start=1.0, end=1.2)

    assert exc_info.value.code == "subprocess_failed"
    assert "boom" in exc_info.value.message
    assert line_1 in (exc_info.value.stderr_tail or "")
    assert line_2 in (exc_info.value.stderr_tail or "")
    assert line_1 in captured()
    assert line_2 in captured()


@pytest.mark.parametrize(
    ("runner", "kind"),
    [
        (lexeme_rerun._run_ipa_interval_in_subprocess, "ipa"),
        (lexeme_rerun._run_ortho_interval_in_subprocess, "ortho"),
    ],
)
def test_lexeme_subprocess_success_cleans_child_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: Callable[..., str],
    kind: str,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    process = _FakeProcess(target=lambda: None, name="", args=(), daemon=True, exitcode=0, write_success=True, write_log=True)
    _install_fake_process(monkeypatch, process)

    assert runner(audio_path=audio_path, start=1.0, end=1.2) == "ʃ"

    assert not Path(f"/tmp/parse-lexeme-rerun-{kind}-{process.pid}.log").exists()


@pytest.mark.parametrize(
    ("exitcode", "code"),
    [
        (139, "subprocess_segfault"),
        (-11, "subprocess_segfault"),
        (137, "subprocess_oom"),
        (-9, "subprocess_oom"),
        (2, "subprocess_failed"),
    ],
)
def test_lexeme_subprocess_exit_codes_map_to_structured_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exitcode: int,
    code: str,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    process = _FakeProcess(target=lambda: None, name="", args=(), daemon=True, exitcode=exitcode)
    _install_fake_process(monkeypatch, process)

    with pytest.raises(LexemeRerunSubprocessError) as exc_info:
        lexeme_rerun._run_ipa_interval_in_subprocess(audio_path=audio_path, start=1.0, end=1.2)

    assert exc_info.value.code == code
    assert exc_info.value.exit_code == exitcode
    assert "lexeme IPA subprocess" in exc_info.value.message


@pytest.mark.parametrize(
    ("runner", "kind", "tier_label"),
    [
        (lexeme_rerun._run_ipa_interval_in_subprocess, "ipa", "IPA"),
        (lexeme_rerun._run_ortho_interval_in_subprocess, "ortho", "ORTH"),
    ],
)
def test_lexeme_subprocess_exit_error_includes_child_log_tail_and_cleans_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: Callable[..., str],
    kind: str,
    tier_label: str,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    process = _FakeProcess(target=lambda: None, name="", args=(), daemon=True, exitcode=139, write_log=True)
    _install_fake_process(monkeypatch, process)

    with pytest.raises(LexemeRerunSubprocessError) as exc_info:
        runner(audio_path=audio_path, start=1.0, end=1.2)

    assert exc_info.value.code == "subprocess_segfault"
    assert exc_info.value.exit_code == 139
    assert f"lexeme {tier_label} subprocess" in exc_info.value.message
    assert exc_info.value.stderr_tail == "DIAGNOSTIC_SMOKE_TEST: about to crash on purpose"
    assert not Path(f"/tmp/parse-lexeme-rerun-{kind}-{process.pid}.log").exists()


def test_lexeme_subprocess_missing_child_log_leaves_stderr_tail_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    process = _FakeProcess(target=lambda: None, name="", args=(), daemon=True, exitcode=139)
    _install_fake_process(monkeypatch, process)

    with pytest.raises(LexemeRerunSubprocessError) as exc_info:
        lexeme_rerun._run_ipa_interval_in_subprocess(audio_path=audio_path, start=1.0, end=1.2)

    assert exc_info.value.code == "subprocess_segfault"
    assert exc_info.value.stderr_tail is None


def test_lexeme_subprocess_timeout_terminates_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    process = _FakeProcess(target=lambda: None, name="", args=(), daemon=True, exitcode=None, stay_alive=True)
    _install_fake_process(monkeypatch, process)
    monkeypatch.setenv("PARSE_LEXEME_RERUN_SUBPROCESS_TIMEOUT_SEC", "0.01")

    with pytest.raises(LexemeRerunSubprocessError) as exc_info:
        lexeme_rerun._run_ortho_interval_in_subprocess(audio_path=audio_path, start=1.0, end=1.2)

    assert exc_info.value.code == "subprocess_timeout"
    assert exc_info.value.exit_code == -9
    assert process.terminated is True


def test_lexeme_subprocess_child_reported_failure_is_503_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")

    class _FailureProcess(_FakeProcess):
        def start(self) -> None:
            self.started = True
            result_path = Path(self.args[2])
            result_path.write_text(json.dumps({"ok": False, "error": "model exploded"}), encoding="utf-8")

    process = _FailureProcess(target=lambda: None, name="", args=(), daemon=True, exitcode=0)
    _install_fake_process(monkeypatch, process)

    with pytest.raises(LexemeRerunSubprocessError) as exc_info:
        lexeme_rerun._run_ortho_interval_in_subprocess(audio_path=audio_path, start=1.0, end=1.2)

    assert exc_info.value.code == "subprocess_failed"
    assert exc_info.value.exit_code == 0
    assert "model exploded" in exc_info.value.message
