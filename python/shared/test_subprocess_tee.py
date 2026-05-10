"""Unit tests for python/shared/subprocess_tee.py.

Tests cover:
- fd2 pipe capture: install_child_tee tees sys.stderr to inherited fd 2 AND the logfile.
- fd1 pipe capture: install_child_tee tees sys.stdout to inherited fd 1 AND the logfile.
- _Tee swallows errors on closed streams without raising.
- install_child_tee propagates OSError when the log file cannot be opened.

All tests restore global state (sys.stdout / sys.stderr / fd 1 / fd 2) in finally
blocks so they do not contaminate each other or subsequent tests.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

from shared.subprocess_tee import _Tee, install_child_tee


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_pipe_to_eof(r_fd: int) -> str:
    """Read all available bytes from a pipe fd until EOF, return as str."""
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(r_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# fd2 (stderr) tee test
# ---------------------------------------------------------------------------

def test_install_child_tee_stderr_reaches_parent_fd2_and_log(tmp_path: Path) -> None:
    """install_child_tee rebinds sys.stderr to tee to inherited fd 2 and the logfile."""
    log_path = str(tmp_path / "child-stderr.log")
    marker = "PARSE-TEE-STDERR-MARKER-fd2-abc\n"

    orig_stderr = sys.stderr
    orig_fd2 = os.dup(2)          # save copy of real stderr fd

    r, w = os.pipe()
    os.dup2(w, 2)                 # redirect fd 2 → pipe write end
    os.close(w)                   # drop extra ref; only fd 2 holds the write side

    log_fh = inherited_out = inherited_err = None
    try:
        log_fh, inherited_out, inherited_err = install_child_tee(log_path)
        # sys.stderr is now _Tee(log_fh, inherited_err)
        # inherited_err wraps a dup of fd 2 (= our pipe write end)
        sys.stderr.write(marker)
        sys.stderr.flush()
    finally:
        # Close write-side handles so the pipe reaches EOF on the read side.
        for handle in (inherited_err, log_fh, inherited_out):
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        # Restore fd 2 and sys.stderr before reading the pipe.
        os.dup2(orig_fd2, 2)
        os.close(orig_fd2)
        sys.stderr = orig_stderr

    # Now the pipe write side is fully closed; read until EOF.
    captured = _read_pipe_to_eof(r)
    os.close(r)

    assert marker.strip() in captured, (
        f"Expected marker in pipe capture (parent fd 2); got: {captured!r}"
    )
    log_content = Path(log_path).read_text(encoding="utf-8")
    assert marker.strip() in log_content, (
        f"Expected marker in logfile; got: {log_content!r}"
    )


# ---------------------------------------------------------------------------
# fd1 (stdout) tee test
# ---------------------------------------------------------------------------

def test_install_child_tee_stdout_reaches_parent_fd1_and_log(tmp_path: Path) -> None:
    """install_child_tee rebinds sys.stdout to tee to inherited fd 1 and the logfile."""
    log_path = str(tmp_path / "child-stdout.log")
    marker = "PARSE-TEE-STDOUT-MARKER-fd1-xyz\n"

    orig_stdout = sys.stdout
    orig_fd1 = os.dup(1)          # save copy of real stdout fd

    r, w = os.pipe()
    os.dup2(w, 1)                 # redirect fd 1 → pipe write end
    os.close(w)

    log_fh = inherited_out = inherited_err = None
    try:
        log_fh, inherited_out, inherited_err = install_child_tee(log_path)
        sys.stdout.write(marker)
        sys.stdout.flush()
    finally:
        for handle in (inherited_out, log_fh, inherited_err):
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        os.dup2(orig_fd1, 1)
        os.close(orig_fd1)
        sys.stdout = orig_stdout

    captured = _read_pipe_to_eof(r)
    os.close(r)

    assert marker.strip() in captured, (
        f"Expected marker in pipe capture (parent fd 1); got: {captured!r}"
    )
    log_content = Path(log_path).read_text(encoding="utf-8")
    assert marker.strip() in log_content, (
        f"Expected marker in logfile; got: {log_content!r}"
    )


# ---------------------------------------------------------------------------
# _Tee closed-stream swallow test
# ---------------------------------------------------------------------------

def test_tee_write_swallows_closed_stream_error() -> None:
    """_Tee.write must not raise when one stream is closed; returns len(data)."""
    closed = io.StringIO()
    closed.close()
    live = io.StringIO()

    tee = _Tee(closed, live)
    result = tee.write("hello")

    assert isinstance(result, int) and result > 0
    assert live.getvalue() == "hello"


def test_tee_flush_swallows_closed_stream_error() -> None:
    """_Tee.flush must not raise even if one stream is already closed."""
    closed = io.StringIO()
    closed.close()
    live = io.StringIO()

    tee = _Tee(closed, live)
    tee.flush()  # must not raise


def test_tee_isatty_returns_false() -> None:
    tee = _Tee(io.StringIO())
    assert tee.isatty() is False


def test_tee_fileno_raises_oserror() -> None:
    tee = _Tee(io.StringIO())
    with pytest.raises(OSError):
        tee.fileno()


# ---------------------------------------------------------------------------
# log-open failure propagates OSError
# ---------------------------------------------------------------------------

def test_install_child_tee_bad_log_path_raises_oserror() -> None:
    """install_child_tee propagates OSError when the log file cannot be opened."""
    bad_path = "/no-such-dir/does-not-exist/child.log"
    with pytest.raises(OSError):
        install_child_tee(bad_path)
