"""Unit tests for LocalWhisperProvider.transcribe_segments_in_memory.

This is the in-memory windowed transcribe path used by the BND-anchored
re-transcription job. The tests stub faster-whisper's WhisperModel so
they stay hermetic (no model download, no torch CUDA).
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List, Tuple

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import provider as provider_module
from ai.provider import LocalWhisperProvider


class _StubWord:
    def __init__(self, word: str, start: float, end: float, prob: float = 0.9) -> None:
        self.word = word
        self.start = start
        self.end = end
        self.probability = prob


class _StubSegment:
    def __init__(
        self,
        start: float,
        end: float,
        text: str,
        words: List[_StubWord] | None = None,
        avg_logprob: float = -0.3,
    ) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob
        if words is not None:
            self.words = words


class _StubInfo:
    def __init__(self, duration: float = 1.0) -> None:
        self.duration = duration


class _RecordingWhisperModel:
    calls: List[Dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def transcribe(self, audio: Any, **kwargs: Any) -> Tuple[Any, _StubInfo]:
        length = int(np.asarray(audio).shape[0]) if audio is not None else 0
        type(self).calls.append({"length": length, **kwargs})
        segment = _StubSegment(
            start=0.10,
            end=0.40,
            text="ok",
            words=[_StubWord("ok", 0.12, 0.38, prob=0.9)],
        )
        return iter([segment]), _StubInfo()


def _make_provider(tmp_path: pathlib.Path, monkeypatch: Any) -> LocalWhisperProvider:
    _RecordingWhisperModel.calls = []
    monkeypatch.setattr(provider_module, "_register_cuda_dll_directories", lambda: None, raising=False)
    import faster_whisper  # type: ignore

    monkeypatch.setattr(faster_whisper, "WhisperModel", _RecordingWhisperModel, raising=True)
    return LocalWhisperProvider(
        config={"stt": {"language": ""}},
        config_path=tmp_path / "ai_config.json",
    )


def test_offsets_segments_and_words_into_global_timeline(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000 * 5, dtype=np.float32)

    out = provider.transcribe_segments_in_memory(audio, [(3.0, 4.0)])

    assert len(out) == 1
    segment = out[0]
    assert segment["start"] == 3.10
    assert segment["end"] == 3.40
    assert segment["text"] == "ok"
    assert "words" in segment
    assert segment["words"][0]["start"] == 3.12
    assert segment["words"][0]["end"] == 3.38


def test_skips_zero_and_inverted_intervals(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000 * 5, dtype=np.float32)
    intervals = [
        (1.0, 1.0),
        (2.0, 1.5),
        (3.0, 3.5),
    ]

    out = provider.transcribe_segments_in_memory(audio, intervals)

    assert len(_RecordingWhisperModel.calls) == 1
    assert len(out) == 1


def test_clamps_segment_end_to_interval_end(tmp_path, monkeypatch):
    class _OvershootModel(_RecordingWhisperModel):
        def transcribe(self, audio, **kwargs):
            type(self).calls.append({"length": int(np.asarray(audio).shape[0]), **kwargs})
            segment = _StubSegment(start=0.0, end=0.6, text="x", words=[])
            return iter([segment]), _StubInfo()

    monkeypatch.setattr(provider_module, "_register_cuda_dll_directories", lambda: None, raising=False)
    import faster_whisper  # type: ignore

    monkeypatch.setattr(faster_whisper, "WhisperModel", _OvershootModel, raising=True)
    provider = LocalWhisperProvider(config={"stt": {}}, config_path=tmp_path / "x.json")

    audio = np.zeros(16000, dtype=np.float32)
    out = provider.transcribe_segments_in_memory(audio, [(0.0, 0.5)])

    assert len(out) == 1
    assert out[0]["end"] == 0.5


def test_kwargs_force_word_timestamps_and_disable_vad(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000, dtype=np.float32)
    provider.transcribe_segments_in_memory(audio, [(0.0, 0.5)], language="ku")

    assert _RecordingWhisperModel.calls[0]["word_timestamps"] is True
    assert _RecordingWhisperModel.calls[0]["vad_filter"] is False
    assert _RecordingWhisperModel.calls[0]["condition_on_previous_text"] is False
    assert _RecordingWhisperModel.calls[0]["language"] == "ku"


def test_empty_intervals_returns_empty(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000, dtype=np.float32)

    assert provider.transcribe_segments_in_memory(audio, []) == []
    assert _RecordingWhisperModel.calls == []


def test_progress_callback_fires_per_interval(tmp_path, monkeypatch):
    provider = _make_provider(tmp_path, monkeypatch)
    audio = np.zeros(16000 * 3, dtype=np.float32)
    intervals = [(0.0, 0.5), (1.0, 1.5), (2.0, 2.5)]

    progress_calls: List[Tuple[float, int]] = []

    def _on_progress(pct: float, count: int) -> None:
        progress_calls.append((pct, count))

    provider.transcribe_segments_in_memory(audio, intervals, progress_callback=_on_progress)

    assert len(progress_calls) == 3
    assert progress_calls[-1][1] == 3
    assert abs(progress_calls[-1][0] - 100.0) < 0.01
