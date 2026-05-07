from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from server_routes.lexeme_rerun import _run_ipa_interval, _run_ortho_interval


def test_run_ortho_interval_calls_renamed_helper(monkeypatch) -> None:
    import ai.stt_pipeline as stt_pipeline

    with pytest.raises(ImportError):
        from ai.stt_pipeline import run_stt_on_interval  # noqa: F401

    calls: list[dict[str, Any]] = []

    def fake_run_ortho_on_interval(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "ریشەم"

    monkeypatch.setattr(stt_pipeline, "run_ortho_on_interval", fake_run_ortho_on_interval)

    result = _run_ortho_interval(audio_path=Path("/tmp/x.wav"), start=1.0, end=2.0, language="sdh")

    assert result == "ریشەم"
    assert len(calls) == 1
    assert calls[0]["audio_path"] == Path("/tmp/x.wav")
    assert calls[0]["start"] == 1.0
    assert calls[0]["end"] == 2.0
    assert calls[0]["language"] == "sdh"
    assert "config_path" in calls[0]


def test_run_ipa_interval_calls_transcribe_intervals_with_single_interval(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_transcribe_intervals(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [{"start": 1.0, "end": 2.0, "ipa": " ʃ "}]

    monkeypatch.setattr("ai.ipa_transcribe.transcribe_intervals", fake_transcribe_intervals)

    result = _run_ipa_interval(audio_path=Path("/tmp/x.wav"), start=1.0, end=2.0, language="sdh")

    assert result == "ʃ"
    assert calls == [
        {
            "audio_path": Path("/tmp/x.wav"),
            "intervals": [{"start": 1.0, "end": 2.0}],
        }
    ]
    assert "language" not in calls[0]
