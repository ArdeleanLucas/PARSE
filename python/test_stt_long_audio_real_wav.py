"""Real-WAV long-audio STT regression coverage for MC-384-O.

These tests are intentionally gated by the ``long_audio`` marker and the
``--run-long-audio`` opt-in because they load the real STT provider and run
minutes-long inference. The asset may be committed later after Lucas selects an
approved redistributable slice, or downloaded on demand via ``PARSE_LONG_AUDIO_URL``.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
from typing import Any

import pytest
import soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402
from server_routes import media  # noqa: E402

pytestmark = pytest.mark.long_audio

LONG_AUDIO_SPEAKER = "LongAudio01"
LONG_AUDIO_LANGUAGE = os.environ.get("PARSE_LONG_AUDIO_LANGUAGE", "ku")


def _stage_asset_under_temp_project(asset_path: pathlib.Path, tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Expose the fixture under a pytest temp project root without copying when possible."""
    project_root = tmp_path / "workspace"
    staged = project_root / "audio" / "working" / LONG_AUDIO_SPEAKER / asset_path.name
    staged.parent.mkdir(parents=True, exist_ok=True)
    if not staged.exists():
        try:
            staged.symlink_to(asset_path)
        except OSError:
            shutil.copy2(asset_path, staged)
    return project_root, staged


def _run_real_stt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    asset_path: pathlib.Path,
    *,
    job_id: str,
    chunk_minutes: str,
) -> tuple[dict[str, Any], float]:
    """Run the real STT path against ``asset_path`` inside a temp-safe root."""
    project_root, staged_asset = _stage_asset_under_temp_project(asset_path, tmp_path)
    server._install_route_bindings()
    server._jobs.clear()
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", chunk_minutes)
    monkeypatch.setattr(server, "_project_root", lambda: project_root)
    monkeypatch.setattr(media._server, "_project_root", lambda: project_root)
    duration_sec = float(sf.info(str(staged_asset)).duration)
    result = media._run_stt_job(
        job_id=job_id,
        speaker=LONG_AUDIO_SPEAKER,
        source_wav=str(staged_asset.relative_to(project_root)),
        language=LONG_AUDIO_LANGUAGE,
    )
    return result, duration_sec


def _coverage_fraction(result: dict[str, Any], duration_sec: float) -> float:
    segments = result.get("segments") or []
    assert isinstance(segments, list), "STT result['segments'] must be a list"
    coverage_end = max(
        (
            float(segment.get("end", 0.0) or 0.0)
            for segment in segments
            if isinstance(segment, dict) and str(segment.get("text", "")).strip()
        ),
        default=0.0,
    )
    return coverage_end / duration_sec if duration_sec > 0 else 0.0


def _assert_monotonic_absolute_timestamps(result: dict[str, Any]) -> None:
    previous_start = -1.0
    previous_end = -1.0
    for idx, segment in enumerate(result.get("segments") or []):
        if not isinstance(segment, dict) or not str(segment.get("text", "")).strip():
            continue
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        assert start >= previous_start, f"segment {idx} start regressed: {start} < {previous_start}"
        assert end >= start, f"segment {idx} ends before it starts: {segment!r}"
        assert end >= previous_end, f"segment {idx} end regressed: {end} < {previous_end}"
        previous_start = start
        previous_end = end


def test_chunked_stt_covers_long_audio_real_wav(
    long_audio_asset_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """Chunked real-WAV STT should cover at least 90% of the approved clip."""
    result, duration_sec = _run_real_stt(
        monkeypatch,
        tmp_path,
        long_audio_asset_path,
        job_id="test-long-audio-chunked",
        chunk_minutes="10",
    )

    chunks = result.get("chunks") or []
    assert len(chunks) >= 1
    assert chunks[0].get("status") == "ok"
    assert result.get("segments"), "no segments produced"
    fraction = _coverage_fraction(result, duration_sec)
    print(
        f"[long_audio] chunked coverage fraction={fraction:.3f} "
        f"duration={duration_sec:.2f}s chunks={len(chunks)}"
    )
    assert fraction >= 0.90, f"chunked coverage too low: {fraction:.3f}"
    _assert_monotonic_absolute_timestamps(result)


def test_unchunked_stt_fails_to_cover_long_audio_real_wav(
    long_audio_asset_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """Unchunked real-WAV STT should expose the long-audio coverage failure."""
    result, duration_sec = _run_real_stt(
        monkeypatch,
        tmp_path,
        long_audio_asset_path,
        job_id="test-long-audio-unchunked",
        chunk_minutes="0",
    )

    assert result.get("chunks") == []
    fraction = _coverage_fraction(result, duration_sec)
    print(f"[long_audio] unchunked coverage fraction={fraction:.3f} duration={duration_sec:.2f}s")
    assert fraction < 0.50, (
        f"unchunked coverage unexpectedly high: {fraction:.3f}. "
        "Either the approved audio no longer reproduces the bug or Whisper improved; "
        "find a harder asset or mark this negative control xfail with a TODO."
    )
    _assert_monotonic_absolute_timestamps(result)
