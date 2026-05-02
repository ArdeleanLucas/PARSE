from __future__ import annotations

import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.forced_align import DEFAULT_MODEL_NAME, Aligner  # noqa: E402


def test_transcribe_window_structured_wraps_existing_decode_without_normalizing(monkeypatch) -> None:
    raw_ipa = "  ðæɚ oʊ  "
    aligner = Aligner(
        model=object(),
        processor=object(),
        device="cpu",
        vocab={},
        blank_id=0,
        frame_stride_seconds=0.02,
    )

    def fake_transcribe_window(self, audio_16k):
        assert audio_16k == "audio-window"
        return raw_ipa

    monkeypatch.setattr(Aligner, "transcribe_window", fake_transcribe_window)

    result = aligner.transcribe_window_structured("audio-window")

    assert set(result) == {"raw_ipa", "model", "model_version", "decoded_at"}
    assert result["raw_ipa"] == raw_ipa
    assert result["model"] == "wav2vec2-xlsr-53-espeak-cv-ft"
    assert result["model_version"] == DEFAULT_MODEL_NAME
    decoded_at = str(result["decoded_at"])
    assert decoded_at.endswith("Z")
    datetime.fromisoformat(decoded_at.replace("Z", "+00:00"))
