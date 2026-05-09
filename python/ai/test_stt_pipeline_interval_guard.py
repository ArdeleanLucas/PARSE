from __future__ import annotations

from pathlib import Path

import pytest

from ai.stt_pipeline import run_ortho_on_interval


class _Provider:
    def transcribe_segments_in_memory(self, *args, **kwargs):  # pragma: no cover - should not be called for too-short slices
        raise AssertionError("provider should not be called")


def test_run_ortho_on_interval_rejects_sub_80ms_before_provider(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")

    with pytest.raises(ValueError) as exc_info:
        run_ortho_on_interval(
            audio_path,
            1.0,
            1.06,
            provider=_Provider(),
            device="cuda",
            allow_wsl_cuda=True,
        )

    assert "interval_too_short" in str(exc_info.value)
    assert "duration_ms=60.0" in str(exc_info.value)
