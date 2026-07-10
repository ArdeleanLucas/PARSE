"""ffmpeg/ffprobe resolution tests for the video_clip_extract CLI."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import video_clip_extract as mod  # noqa: E402


def test_explicit_valid_path_used_as_is(monkeypatch):
    monkeypatch.setattr(mod, "_verify_ffmpeg_binary", lambda c: c == "/opt/ffmpeg")

    def _fail_discover(*args, **kwargs):
        raise AssertionError("discover_ffmpeg must not run when explicit path is valid")

    monkeypatch.setattr(mod, "discover_ffmpeg", _fail_discover)

    assert mod.resolve_ffmpeg_binary("/opt/ffmpeg") == "/opt/ffmpeg"


def test_explicit_invalid_path_fails_fast(monkeypatch):
    monkeypatch.setattr(mod, "_verify_ffmpeg_binary", lambda c: False)

    def _fail_discover(*args, **kwargs):
        raise AssertionError("discover_ffmpeg must not run when explicit path fails")

    monkeypatch.setattr(mod, "discover_ffmpeg", _fail_discover)

    with pytest.raises(SystemExit):
        mod.resolve_ffmpeg_binary("/no/such/ffmpeg")


def test_omitted_flag_triggers_discovery(monkeypatch):
    called = {}

    def _fake_discover(*args, **kwargs):
        called["hit"] = True
        return "/discovered/ffmpeg"

    monkeypatch.setattr(mod, "discover_ffmpeg", _fake_discover)

    assert mod.resolve_ffmpeg_binary("") == "/discovered/ffmpeg"
    assert called.get("hit") is True


def test_ffprobe_explicit_infers_sibling():
    assert mod._infer_ffprobe_path("/opt/ffmpeg", explicit=True) == "/opt/ffprobe"


def test_ffprobe_discovered_uses_shared_policy(monkeypatch):
    seen = {}

    def _fake_discover_ffprobe(*args, **kwargs):
        seen["ffmpeg_path"] = kwargs.get("ffmpeg_path")
        return "/discovered/ffprobe"

    monkeypatch.setattr(mod, "discover_ffprobe", _fake_discover_ffprobe)

    result = mod._infer_ffprobe_path("/discovered/ffmpeg", explicit=False)
    assert result == "/discovered/ffprobe"
    assert seen["ffmpeg_path"] == "/discovered/ffmpeg"
