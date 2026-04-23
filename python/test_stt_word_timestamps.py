"""Regression guard for Tier 1 (word-level STT).

Verifies two things:
  1. LocalWhisperProvider forwards word_timestamps=True to faster-whisper.
  2. Per-word spans coming back on segments land in SegmentWithWords.words,
     surviving the cleaning loop in stt_pipeline.run_stt_pipeline.

Uses the same sys.modules stubbing pattern as test_stt_cuda_fallback.py so
the test runs without a real faster_whisper install.
"""
from __future__ import annotations

import pathlib
import sys
import types
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import provider as provider_module
from ai.provider import LocalWhisperProvider, _extract_word_spans


class _StubWord:
    def __init__(self, word: str, start: float, end: float, probability: float) -> None:
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class _StubSegment:
    def __init__(
        self,
        start: float,
        end: float,
        text: str,
        words: List[_StubWord],
    ) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = -0.25
        self.words = words


class _StubInfo:
    duration = 2.0


class _StubWhisperModel:
    last_call: Dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def transcribe(self, audio: str, **kwargs: Any) -> Tuple[Any, _StubInfo]:
        type(self).last_call = {"audio": audio, **kwargs}
        seg = _StubSegment(
            0.0,
            1.8,
            "یەک دوو",
            [
                _StubWord("یەک", 0.2, 0.5, 0.91),
                _StubWord("دوو", 0.9, 1.3, 0.88),
            ],
        )
        return iter([seg]), _StubInfo()


def _install_stub_faster_whisper(monkeypatch: Any) -> None:
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = _StubWhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(
        provider_module, "_register_cuda_dll_directories", lambda: None, raising=False
    )


def _make_audio(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "clip.wav"
    p.write_bytes(b"RIFF    WAVEfmt ")
    return p


def test_word_timestamps_kwarg_is_forwarded(tmp_path, monkeypatch):
    _install_stub_faster_whisper(monkeypatch)
    provider = LocalWhisperProvider(
        config={"stt": {"language": ""}},
        config_path=tmp_path / "ai_config.json",
    )
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call.get("word_timestamps") is True


def test_word_spans_attached_to_segment(tmp_path, monkeypatch):
    _install_stub_faster_whisper(monkeypatch)
    provider = LocalWhisperProvider(
        config={"stt": {"language": ""}},
        config_path=tmp_path / "ai_config.json",
    )
    segments = provider.transcribe(_make_audio(tmp_path))
    assert len(segments) == 1
    seg = segments[0]
    assert seg["text"] == "یەک دوو"
    assert "words" in seg
    words = seg["words"]
    assert [w["word"] for w in words] == ["یەک", "دوو"]
    assert all(0.0 <= w["prob"] <= 1.0 for w in words)
    assert words[0]["start"] < words[0]["end"] <= words[1]["start"]


def test_extract_word_spans_handles_empty_and_missing():
    assert _extract_word_spans(None) == []
    assert _extract_word_spans(types.SimpleNamespace(words=None)) == []
    assert _extract_word_spans(types.SimpleNamespace(words=[])) == []
    # Drops whitespace-only entries but keeps valid ones.
    stub = types.SimpleNamespace(
        words=[
            _StubWord("", 0.0, 0.1, 0.5),
            _StubWord("پێنج", 0.1, 0.4, 0.77),
        ]
    )
    spans = _extract_word_spans(stub)
    assert len(spans) == 1 and spans[0]["word"] == "پێنج"
