"""
Hermetic tests for the cross-platform ffmpeg/ffprobe discovery policy.

These tests never require a real ffmpeg binary: a fake `verify` predicate that
recognises specific candidate paths is injected everywhere, so they exercise
the ORDERING policy (env override > bundled/frozen > PATH > common locations)
without spawning subprocesses.
"""

import os
import platform
from pathlib import Path

import pytest

from shared import ffmpeg_discovery as fd
from shared.ffmpeg_discovery import (
    BUNDLED_BIN_ENV,
    FFMPEG_OVERRIDE_ENV,
    FFPROBE_OVERRIDE_ENV,
    LEGACY_FFMPEG_ENV,
    FfmpegNotFoundError,
    discover_ffmpeg,
    discover_ffprobe,
)


# --- helpers ---------------------------------------------------------------


def _clear_env(monkeypatch):
    """Remove every env var the resolver reads, for a clean baseline."""
    for key in (
        FFMPEG_OVERRIDE_ENV,
        FFPROBE_OVERRIDE_ENV,
        BUNDLED_BIN_ENV,
        LEGACY_FFMPEG_ENV,
    ):
        monkeypatch.delenv(key, raising=False)


def _verify_only(*good_paths):
    """Return a verify predicate that accepts exactly the given paths."""
    good = set(good_paths)

    def _verify(candidate: str) -> bool:
        return candidate in good

    return _verify


def _make_fake_exe(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / name
    exe.write_text("#!/bin/sh\necho fake\n")
    exe.chmod(0o755)
    return exe


# --- env override (highest of the auto-discovered sources) -----------------


def test_env_override_wins(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(FFMPEG_OVERRIDE_ENV, "/custom/ffmpeg")
    # Even if PATH would resolve something, the env override is tried first.
    monkeypatch.setattr(fd.shutil, "which", lambda tool: "/usr/bin/ffmpeg")

    result = discover_ffmpeg(verify=_verify_only("/custom/ffmpeg", "/usr/bin/ffmpeg"))
    assert result == "/custom/ffmpeg"


def test_explicit_argument_beats_env(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(FFMPEG_OVERRIDE_ENV, "/custom/ffmpeg")

    result = discover_ffmpeg(
        explicit="/explicit/ffmpeg",
        verify=_verify_only("/explicit/ffmpeg", "/custom/ffmpeg"),
    )
    assert result == "/explicit/ffmpeg"


def test_legacy_env_alias_lower_than_new_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(FFMPEG_OVERRIDE_ENV, "/new/ffmpeg")
    monkeypatch.setenv(LEGACY_FFMPEG_ENV, "/legacy/ffmpeg")

    result = discover_ffmpeg(verify=_verify_only("/new/ffmpeg", "/legacy/ffmpeg"))
    assert result == "/new/ffmpeg"


def test_legacy_env_used_when_new_override_absent(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(LEGACY_FFMPEG_ENV, "/legacy/ffmpeg")
    monkeypatch.setattr(fd.shutil, "which", lambda tool: None)

    result = discover_ffmpeg(verify=_verify_only("/legacy/ffmpeg"))
    assert result == "/legacy/ffmpeg"


# --- bundled desktop directory ---------------------------------------------


def test_bundled_dir_found(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    bundled = _make_fake_exe(tmp_path / "bundle", exe_name)
    monkeypatch.setenv(BUNDLED_BIN_ENV, str(tmp_path / "bundle"))
    monkeypatch.setattr(fd.shutil, "which", lambda tool: None)

    result = discover_ffmpeg(verify=_verify_only(str(bundled)))
    assert result == str(bundled)


def test_bundled_beats_path(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    bundled = _make_fake_exe(tmp_path / "bundle", exe_name)
    monkeypatch.setenv(BUNDLED_BIN_ENV, str(tmp_path / "bundle"))
    monkeypatch.setattr(fd.shutil, "which", lambda tool: "/usr/bin/ffmpeg")

    # Both verify; policy order must prefer the bundled one over PATH.
    result = discover_ffmpeg(verify=_verify_only(str(bundled), "/usr/bin/ffmpeg"))
    assert result == str(bundled)


def test_frozen_meipass_dir(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    exe = _make_fake_exe(tmp_path / "meipass", exe_name)
    monkeypatch.setattr(fd.sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: None)

    result = discover_ffmpeg(verify=_verify_only(str(exe)))
    assert result == str(exe)


# --- PATH fallback ---------------------------------------------------------


def test_path_fallback(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: "/usr/bin/ffmpeg")

    result = discover_ffmpeg(verify=_verify_only("/usr/bin/ffmpeg"))
    assert result == "/usr/bin/ffmpeg"


# --- common per-OS install locations ---------------------------------------


def test_common_location_fallback(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: None)

    # Pick a common dir appropriate to this OS and force it to verify.
    system = platform.system()
    if system == "Darwin":
        common = "/opt/homebrew/bin/ffmpeg"
    elif system == "Windows":
        common = "C:/ProgramData/chocolatey/bin/ffmpeg.exe"
    else:
        common = "/usr/bin/ffmpeg"

    result = discover_ffmpeg(verify=_verify_only(common))
    assert result == common


# --- nothing found ---------------------------------------------------------


def test_nothing_found_raises_actionable(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: None)

    with pytest.raises(FfmpegNotFoundError) as excinfo:
        discover_ffmpeg(verify=lambda candidate: False)

    message = str(excinfo.value)
    assert FFMPEG_OVERRIDE_ENV in message
    assert "install ffmpeg" in message.lower()


def test_invalid_override_falls_through(monkeypatch):
    _clear_env(monkeypatch)
    # Env override is set but does NOT verify; discovery must continue to PATH.
    monkeypatch.setenv(FFMPEG_OVERRIDE_ENV, "/broken/ffmpeg")
    monkeypatch.setattr(fd.shutil, "which", lambda tool: "/usr/bin/ffmpeg")

    result = discover_ffmpeg(verify=_verify_only("/usr/bin/ffmpeg"))
    assert result == "/usr/bin/ffmpeg"


# --- ffprobe ---------------------------------------------------------------


def test_ffprobe_env_override_wins(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(FFPROBE_OVERRIDE_ENV, "/custom/ffprobe")
    monkeypatch.setattr(fd.shutil, "which", lambda tool: "/usr/bin/ffprobe")

    result = discover_ffprobe(verify=_verify_only("/custom/ffprobe", "/usr/bin/ffprobe"))
    assert result == "/custom/ffprobe"


def test_ffprobe_prefers_sibling_of_ffmpeg(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: "/usr/bin/ffprobe")

    sibling = "/custom/bin/ffprobe"
    result = discover_ffprobe(
        ffmpeg_path="/custom/bin/ffmpeg",
        verify=_verify_only(sibling, "/usr/bin/ffprobe"),
    )
    assert result == sibling


def test_ffprobe_path_fallback(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: "/usr/bin/ffprobe")

    result = discover_ffprobe(verify=_verify_only("/usr/bin/ffprobe"))
    assert result == "/usr/bin/ffprobe"


def test_ffprobe_nothing_found_raises(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: None)

    with pytest.raises(FfmpegNotFoundError) as excinfo:
        discover_ffprobe(verify=lambda candidate: False)
    assert FFPROBE_OVERRIDE_ENV in str(excinfo.value)


# --- normalize_audio integration (still hermetic) --------------------------


def test_normalize_resolver_uses_policy(monkeypatch):
    """normalize_audio.resolve_ffmpeg_binary delegates to the shared policy."""
    import normalize_audio

    _clear_env(monkeypatch)
    monkeypatch.setenv(FFMPEG_OVERRIDE_ENV, "/custom/ffmpeg")
    # Stub the real -version probe so no subprocess runs.
    monkeypatch.setattr(
        normalize_audio,
        "verify_ffmpeg_binary",
        lambda candidate: candidate == "/custom/ffmpeg",
    )

    result = normalize_audio.resolve_ffmpeg_binary("")
    assert result == "/custom/ffmpeg"


def test_normalize_cli_flag_highest_priority(monkeypatch):
    import normalize_audio

    _clear_env(monkeypatch)
    monkeypatch.setenv(FFMPEG_OVERRIDE_ENV, "/env/ffmpeg")
    monkeypatch.setattr(
        normalize_audio,
        "verify_ffmpeg_binary",
        lambda candidate: candidate in ("/cli/ffmpeg", "/env/ffmpeg"),
    )

    result = normalize_audio.resolve_ffmpeg_binary("/cli/ffmpeg")
    assert result == "/cli/ffmpeg"


def test_normalize_bad_cli_flag_fails_fast(monkeypatch):
    import normalize_audio

    _clear_env(monkeypatch)
    monkeypatch.setattr(
        normalize_audio, "verify_ffmpeg_binary", lambda candidate: False
    )

    with pytest.raises(SystemExit):
        normalize_audio.resolve_ffmpeg_binary("/nonexistent/ffmpeg")


def test_normalize_no_ffmpeg_exits(monkeypatch):
    import normalize_audio

    _clear_env(monkeypatch)
    monkeypatch.setattr(fd.shutil, "which", lambda tool: None)
    monkeypatch.setattr(
        normalize_audio, "verify_ffmpeg_binary", lambda candidate: False
    )

    with pytest.raises(SystemExit):
        normalize_audio.resolve_ffmpeg_binary("")
