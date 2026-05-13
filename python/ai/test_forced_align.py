"""Regression tests for Tier 2 forced alignment.

These tests exercise the public ``align_word`` / ``align_segments`` flow
without pulling the real torch + transformers stack:

  - Proportional fallback fires when no aligner is supplied, when G2P
    returns nothing, or when the audio slice is too short.
  - ``Aligner.tokens_to_ids`` drops unknown phonemes and retries without
    suprasegmentals.
  - ``align_word`` consumes a stubbed Aligner and produces an AlignedWord
    with refined wav2vec2 boundaries and per-phoneme spans.

The real wav2vec2 path is exercised by the end-to-end Fail02.wav test
added in Tier 3, not here — keeping unit tests hermetic and <1 s.
"""
from __future__ import annotations

import json
import numpy as np
import pathlib
import pytest
import sys
import types
from typing import Any, List, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai import forced_align as fa
from ai.forced_align import (
    AlignedWord,
    Aligner,
    align_segments,
    align_word,
    _proportional_fallback,
)
from ai.provider import WordSpan


# ---------------------------------------------------------------------------
# Fixtures — stub audio tensor, stub Aligner
# ---------------------------------------------------------------------------


class _FakeTensor:
    """Minimal stand-in for torch.Tensor used by align_word.

    Only implements the operations align_word actually touches:
    slicing by ``[a:b]``, ``.numel()``, ``.shape[0]``.
    """

    def __init__(self, n_samples: int) -> None:
        self._n = n_samples

    def __getitem__(self, key: slice) -> "_FakeTensor":
        start, stop, _ = key.indices(self._n)
        return _FakeTensor(max(0, stop - start))

    def numel(self) -> int:
        return self._n

    @property
    def shape(self) -> Tuple[int, ...]:
        return (self._n,)


class _StubAligner:
    """Mimics Aligner without torch. Returns deterministic frame spans."""

    frame_stride_seconds = 0.02  # 20 ms like wav2vec2

    def __init__(
        self,
        *,
        phoneme_tokens_result: List[Tuple[int, int]] | None = None,
        score: float = -0.1,
    ) -> None:
        self._phoneme_spans = phoneme_tokens_result
        self._score = score

    def align_window(
        self, audio_16k: Any, phoneme_tokens: Sequence[str]
    ) -> Any:
        if self._phoneme_spans is None:
            return None
        # Return one span per phoneme token; truncate if fewer spans configured.
        n = min(len(phoneme_tokens), len(self._phoneme_spans))
        return self._phoneme_spans[:n], self._score


# ---------------------------------------------------------------------------
# _proportional_fallback
# ---------------------------------------------------------------------------


def test_proportional_fallback_divides_window_evenly() -> None:
    span: WordSpan = {"word": "یەک", "start": 2.0, "end": 2.6, "prob": 0.9}
    out = _proportional_fallback(span, phoneme_count=3)
    assert out["word"] == "یەک"
    assert out["method"] == "proportional-fallback"
    assert out["start"] == 2.0 and out["end"] == 2.6
    assert len(out["phonemes"]) == 3
    assert abs(out["phonemes"][0]["start"] - 2.0) < 1e-9
    assert abs(out["phonemes"][-1]["end"] - 2.6) < 1e-9


def test_proportional_fallback_empty_when_no_duration() -> None:
    span: WordSpan = {"word": "x", "start": 1.0, "end": 1.0}
    out = _proportional_fallback(span, phoneme_count=3)
    assert "phonemes" not in out
    assert out["method"] == "proportional-fallback"


# ---------------------------------------------------------------------------
# Aligner.tokens_to_ids
# ---------------------------------------------------------------------------


def _make_aligner_with_vocab(vocab: dict) -> Aligner:
    """Build a bare Aligner without calling Aligner.load (which requires torch)."""
    return Aligner.__new__(Aligner)  # type: ignore[call-arg]


def test_tokens_to_ids_drops_unknowns_and_retries_without_stress() -> None:
    vocab = {"<pad>": 0, "j": 5, "ɛ": 7, "k": 9}
    aligner = Aligner(
        model=None,
        processor=None,
        device="cpu",
        vocab=vocab,
        blank_id=0,
        frame_stride_seconds=0.02,
    )
    # "ˈj" is stress-marked and not in vocab; retry strips the stress mark.
    ids = aligner.tokens_to_ids(["ˈj", "ɛ", "q", "k"])
    assert ids == [5, 7, 9], ids


def test_tokens_to_ids_empty_input_returns_empty() -> None:
    aligner = Aligner(
        model=None, processor=None, device="cpu",
        vocab={"<pad>": 0}, blank_id=0, frame_stride_seconds=0.02,
    )
    assert aligner.tokens_to_ids([]) == []
    assert aligner.tokens_to_ids(["", None]) == []  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# align_word — fallback paths
# ---------------------------------------------------------------------------


def test_align_word_falls_back_when_aligner_is_none() -> None:
    audio = _FakeTensor(16000)
    span: WordSpan = {"word": "یەک", "start": 0.1, "end": 0.5, "prob": 0.88}
    out = align_word(audio, span, aligner=None)
    assert out["method"] == "proportional-fallback"
    assert out["start"] == 0.1 and out["end"] == 0.5


def test_align_word_falls_back_when_g2p_empty(monkeypatch) -> None:
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: [])
    aligner = _StubAligner(phoneme_tokens_result=[(0, 10)])
    audio = _FakeTensor(16000)
    span: WordSpan = {"word": "یەک", "start": 0.1, "end": 0.5}
    out = align_word(audio, span, aligner=aligner)  # type: ignore[arg-type]
    assert out["method"] == "proportional-fallback"


def test_align_word_falls_back_on_too_short_audio(monkeypatch) -> None:
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j", "ɛ", "k"])
    aligner = _StubAligner(phoneme_tokens_result=[(0, 5), (5, 10), (10, 15)])
    audio = _FakeTensor(200)  # ~12 ms — way under the 100ms floor
    span: WordSpan = {"word": "یەک", "start": 0.0, "end": 0.01}
    out = align_word(audio, span, aligner=aligner)  # type: ignore[arg-type]
    assert out["method"] == "proportional-fallback"


# ---------------------------------------------------------------------------
# align_word — success path
# ---------------------------------------------------------------------------


def test_align_word_uses_wav2vec2_boundaries(monkeypatch) -> None:
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j", "ɛ", "k"])
    # Frame spans: phoneme 1 covers frames 5..15, 2: 15..25, 3: 25..40.
    aligner = _StubAligner(
        phoneme_tokens_result=[(5, 15), (15, 25), (25, 40)],
        score=-0.2,
    )
    audio = _FakeTensor(16000 * 3)  # 3s of audio
    # Whisper boundary: 1.0 -> 1.4; +100ms pad both sides -> slice starts at 0.9s
    span: WordSpan = {"word": "یەک", "start": 1.0, "end": 1.4, "prob": 0.9}
    out = align_word(audio, span, aligner=aligner)  # type: ignore[arg-type]

    assert out["method"] == "wav2vec2"
    # First phoneme starts at slice_offset (0.9s) + 5 frames * 20ms = 1.0s
    assert abs(out["start"] - 1.0) < 1e-6
    # Last phoneme ends at slice_offset + 40 frames * 20ms = 1.7s
    assert abs(out["end"] - 1.7) < 1e-6
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["prob"] == 0.9  # Whisper prob preserved
    assert "phonemes" in out and len(out["phonemes"]) == 3
    # Phonemes are labelled with their IPA tokens (internal G2P output).
    assert [p["phoneme"] for p in out["phonemes"]] == ["j", "ɛ", "k"]


# ---------------------------------------------------------------------------
# align_segments
# ---------------------------------------------------------------------------


def test_align_segments_handles_mixed_segments(monkeypatch, tmp_path) -> None:
    # Stub audio loading and _g2p_word so we don't need real torchaudio.
    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda path: _FakeTensor(16000 * 10))
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j"])

    fake_aligner = _StubAligner(phoneme_tokens_result=[(0, 5)])

    fake_audio = tmp_path / "clip.wav"
    fake_audio.write_bytes(b"")

    segments = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "یەک",
            "confidence": 0.8,
            "words": [{"word": "یەک", "start": 0.1, "end": 0.5}],
        },
        {
            "start": 1.5,
            "end": 2.0,
            "text": "silence",
            "confidence": 0.0,
            # no words key — should produce an empty inner list
        },
    ]
    out = align_segments(
        audio_path=fake_audio,
        segments=segments,
        aligner=fake_aligner,  # type: ignore[arg-type]
    )
    assert len(out) == 2
    assert len(out[0]) == 1 and out[0][0]["method"] == "wav2vec2"
    assert out[1] == []


def test_tier2_align_segments_accepts_tensor_audio(monkeypatch, tmp_path) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j"])

    fake_aligner = _StubAligner(phoneme_tokens_result=[(0, 5)])
    fake_audio = tmp_path / "clip.wav"
    fake_audio.write_bytes(b"")
    audio_tensor = torch.zeros(16000 * 2, dtype=torch.float32)

    out = align_segments(
        audio_path=fake_audio,
        segments=[{"words": [{"word": "a", "start": 0.1, "end": 0.5}]}],
        aligner=fake_aligner,  # type: ignore[arg-type]
        audio_tensor=audio_tensor,
    )

    assert len(out) == 1
    assert out[0][0]["method"] == "wav2vec2"


def test_align_segments_converts_numpy_audio_loader_to_torch_tensor(monkeypatch, tmp_path) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda path: np.zeros(16000 * 2, dtype=np.float32))
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j"])

    class _RecordingAligner(_StubAligner):
        def __init__(self) -> None:
            super().__init__(phoneme_tokens_result=[(0, 5)])
            self.saw_torch_tensor = False

        def align_window(self, audio_16k: Any, phoneme_tokens: Sequence[str]) -> Any:
            assert isinstance(audio_16k, torch.Tensor)
            assert audio_16k.dtype == torch.float32
            self.saw_torch_tensor = True
            return super().align_window(audio_16k, phoneme_tokens)

    fake_aligner = _RecordingAligner()
    fake_audio = tmp_path / "clip.wav"
    fake_audio.write_bytes(b"")

    out = align_segments(
        audio_path=fake_audio,
        segments=[{"words": [{"word": "a", "start": 0.1, "end": 0.5}]}],
        aligner=fake_aligner,  # type: ignore[arg-type]
    )

    assert fake_aligner.saw_torch_tensor is True
    assert out[0][0]["method"] == "wav2vec2"


def test_align_word_rejects_numpy_before_real_aligner_numel(monkeypatch) -> None:
    pytest.importorskip("torch")
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j"])
    aligner = Aligner(
        model=None,
        processor=None,
        device="cpu",
        vocab={"<pad>": 0, "j": 1},
        blank_id=0,
        frame_stride_seconds=0.02,
    )

    with pytest.raises(AssertionError, match="expected torch.Tensor"):
        align_word(
            np.zeros(16000, dtype=np.float32),
            {"word": "a", "start": 0.1, "end": 0.5},
            aligner=aligner,
        )


# ---------------------------------------------------------------------------
# align_segments — progress_callback (MC-363)
# ---------------------------------------------------------------------------


def test_align_segments_emits_progress_callback_per_segment(monkeypatch, tmp_path) -> None:
    """Tier-2 forced alignment must tick a per-segment callback so callers can
    forward progress to long-running compute jobs. The concept-windows ORTH
    pipeline relies on this to keep the UI moving between 70% and 90%; without
    it the UI freezes on 'ORTH concept window N/N' for the entire alignment
    pass (10–20 min on thesis-corpus WAVs).
    """
    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda path: _FakeTensor(16000 * 10))
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j"])

    fake_aligner = _StubAligner(phoneme_tokens_result=[(0, 5)])

    fake_audio = tmp_path / "clip.wav"
    fake_audio.write_bytes(b"")

    segments = [
        {"start": 0.0, "end": 1.0, "text": "a", "words": [{"word": "a", "start": 0.1, "end": 0.5}]},
        {"start": 1.0, "end": 2.0, "text": "b", "words": [{"word": "b", "start": 1.1, "end": 1.5}]},
        {"start": 2.0, "end": 3.0, "text": "c", "words": [{"word": "c", "start": 2.1, "end": 2.5}]},
    ]
    ticks: list[tuple[int, int]] = []
    align_segments(
        audio_path=fake_audio,
        segments=segments,
        aligner=fake_aligner,  # type: ignore[arg-type]
        progress_callback=lambda done, total: ticks.append((done, total)),
    )
    assert ticks == [(1, 3), (2, 3), (3, 3)]


def test_align_segments_progress_callback_exceptions_are_swallowed(monkeypatch, tmp_path) -> None:
    """A misbehaving progress_callback must not abort alignment — progress is
    observability-only. Compute jobs would otherwise lose results on a UI
    plumbing bug."""
    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda path: _FakeTensor(16000 * 10))
    monkeypatch.setattr(fa, "_g2p_word", lambda word, language=None: ["j"])

    fake_aligner = _StubAligner(phoneme_tokens_result=[(0, 5)])

    fake_audio = tmp_path / "clip.wav"
    fake_audio.write_bytes(b"")

    segments = [
        {"start": 0.0, "end": 1.0, "text": "a", "words": [{"word": "a", "start": 0.1, "end": 0.5}]},
        {"start": 1.0, "end": 2.0, "text": "b", "words": [{"word": "b", "start": 1.1, "end": 1.5}]},
    ]

    def boom(done: int, total: int) -> None:
        raise RuntimeError("UI is on fire")

    out = align_segments(
        audio_path=fake_audio,
        segments=segments,
        aligner=fake_aligner,  # type: ignore[arg-type]
        progress_callback=boom,
    )
    assert len(out) == 2  # both segments processed despite callback exception


# ---------------------------------------------------------------------------
# CLI I/O helpers
# ---------------------------------------------------------------------------


def test_load_segments_accepts_artifact_and_raw_list(tmp_path) -> None:
    artifact = tmp_path / "a.json"
    artifact.write_text(json.dumps({"segments": [{"start": 0, "end": 1}]}))
    raw = tmp_path / "b.json"
    raw.write_text(json.dumps([{"start": 0, "end": 1}]))
    assert fa._load_segments(artifact) == [{"start": 0, "end": 1}]
    assert fa._load_segments(raw) == [{"start": 0, "end": 1}]
