from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

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
        stay_alive: bool = False,
    ) -> None:
        self.target = target
        self.name = name
        self.args = args
        self.daemon = daemon
        self.exitcode = exitcode
        self.write_success = write_success
        self.stay_alive = stay_alive
        self.pid = 4321
        self.terminated = False
        self.started = False

    def start(self) -> None:
        self.started = True
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
