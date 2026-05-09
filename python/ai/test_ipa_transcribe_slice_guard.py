from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai import ipa_transcribe


class _FakeAudio:
    shape = (48000,)

    def __getitem__(self, key: Any) -> list[float]:
        return [0.0]


class _FakeAligner:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe_window(self, _window: Any) -> str:
        self.calls += 1
        return "ʃ"


def test_transcribe_slice_rejects_sub_80ms_without_calling_aligner() -> None:
    aligner = _FakeAligner()

    with pytest.raises(ValueError) as exc_info:
        ipa_transcribe.transcribe_slice(_FakeAudio(), 1.0, 1.06, aligner)  # 60 ms

    assert "Audio slice too short for IPA" in str(exc_info.value)
    assert "minimum 80 ms" in str(exc_info.value)
    assert aligner.calls == 0


def test_transcribe_slice_structured_rejects_sub_80ms() -> None:
    with pytest.raises(ValueError) as exc_info:
        ipa_transcribe.transcribe_slice_structured(_FakeAudio(), 1.0, 1.079, _FakeAligner())

    assert "Audio slice too short for IPA" in str(exc_info.value)


def test_transcribe_intervals_emits_per_interval_error_for_too_short_slice(tmp_path: Path, monkeypatch) -> None:
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"fake")
    fake_aligner = _FakeAligner()

    monkeypatch.setattr(ipa_transcribe, "_load_audio_mono_16k", lambda _path: _FakeAudio())
    monkeypatch.setattr(ipa_transcribe.Aligner, "load", lambda **_kwargs: fake_aligner)

    results = ipa_transcribe.transcribe_intervals(
        audio_path=audio_path,
        intervals=[{"start": 1.0, "end": 1.06}],
    )

    assert results == [
        {
            "start": 1.0,
            "end": 1.06,
            "ipa": "",
            "error": "interval_too_short",
            "duration_ms": pytest.approx(60.0),
        }
    ]
    assert fake_aligner.calls == 0


def test_transcribe_intervals_forwards_allow_wsl_cuda_to_aligner_load(tmp_path: Path, monkeypatch) -> None:
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"fake")
    load_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(ipa_transcribe, "_load_audio_mono_16k", lambda _path: _FakeAudio())

    def fake_load(**kwargs: Any) -> _FakeAligner:
        load_calls.append(kwargs)
        return _FakeAligner()

    monkeypatch.setattr(ipa_transcribe.Aligner, "load", fake_load)

    results = ipa_transcribe.transcribe_intervals(
        audio_path=audio_path,
        intervals=[{"start": 1.0, "end": 1.2}],
        device="cuda",
        allow_wsl_cuda=True,
    )

    assert results == [{"start": 1.0, "end": 1.2, "ipa": "ʃ"}]
    assert load_calls == [
        {
            "model_name": ipa_transcribe.DEFAULT_MODEL_NAME,
            "device": "cuda",
            "allow_wsl_cuda": True,
        }
    ]


def test_cli_keeps_default_allow_wsl_cuda_false(tmp_path: Path, monkeypatch) -> None:
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"fake")
    intervals_path = tmp_path / "intervals.json"
    intervals_path.write_text(json.dumps([{"start": 1.0, "end": 1.2}]), encoding="utf-8")
    output_path = tmp_path / "out.json"
    load_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(ipa_transcribe, "_load_audio_mono_16k", lambda _path: _FakeAudio())
    monkeypatch.setattr(ipa_transcribe.Aligner, "load", lambda **kwargs: load_calls.append(kwargs) or _FakeAligner())
    monkeypatch.setattr(
        "sys.argv",
        ["ipa_transcribe", "--audio", str(audio_path), "--intervals", str(intervals_path), "--output", str(output_path)],
    )

    assert ipa_transcribe.main() == 0
    assert load_calls[0]["allow_wsl_cuda"] is False
