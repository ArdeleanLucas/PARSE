"""Regression tests for Tier 3 acoustic IPA transcription.

Tier 3 replaces the old text → IPA path (Epitran / LLM fallbacks) with
wav2vec2 CTC on audio slices. These tests exercise the library surface
without loading real torch/transformers weights:

  - ``transcribe_slice`` honours slice bounds, short-circuits on empty
    or reversed ranges, and hands the Aligner the correct window.
  - ``transcribe_intervals`` coerces dict/tuple interval inputs, invokes
    the aligner once per non-empty interval, and carries progress.
  - ``_load_intervals_json`` accepts the three JSON shapes the CLI can
    be fed (STT artifact, annotation-tier dump, raw list).

The end-to-end wav2vec2 run is validated against Fail02.wav in a
separate script, not here — unit suite stays hermetic.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai import ipa_transcribe as ipa_mod
from ai.ipa_transcribe import (
    _coerce_intervals,
    _load_intervals_json,
    transcribe_intervals,
    transcribe_slice,
)


# ---------------------------------------------------------------------------
# Fake tensor & aligner
# ---------------------------------------------------------------------------


class _FakeTensor:
    """Minimal torch.Tensor stand-in exposing only slice/numel/shape."""

    def __init__(self, n_samples: int, tag: str = "") -> None:
        self._n = n_samples
        self.tag = tag

    def __getitem__(self, key: slice) -> "_FakeTensor":
        start, stop, _ = key.indices(self._n)
        return _FakeTensor(max(0, stop - start), tag="{0}[{1}:{2}]".format(self.tag, start, stop))

    def numel(self) -> int:
        return self._n

    @property
    def shape(self) -> Tuple[int, ...]:
        return (self._n,)


class _RecordingAligner:
    """Records every transcribe_window call so tests can assert on inputs."""

    def __init__(self, output: str = "j ɛ k") -> None:
        self.calls: List[_FakeTensor] = []
        self.output = output

    def transcribe_window(self, window: _FakeTensor) -> str:
        self.calls.append(window)
        return self.output if window.numel() > 0 else ""


# ---------------------------------------------------------------------------
# transcribe_slice
# ---------------------------------------------------------------------------


def test_transcribe_slice_short_circuits_on_reversed_or_zero_range() -> None:
    aligner = _RecordingAligner()
    audio = _FakeTensor(16000 * 5)  # 5s
    assert transcribe_slice(audio, 1.0, 1.0, aligner) == ""
    assert transcribe_slice(audio, 2.0, 1.0, aligner) == ""
    assert aligner.calls == []  # aligner never invoked


def test_transcribe_slice_passes_correct_window() -> None:
    aligner = _RecordingAligner(output="k æ t")
    audio = _FakeTensor(16000 * 5)
    result = transcribe_slice(audio, 1.0, 2.0, aligner)
    assert result == "k æ t"
    assert len(aligner.calls) == 1
    # 1s window @ 16 kHz = 16 000 samples.
    assert aligner.calls[0].numel() == 16000


def test_transcribe_slice_clamps_end_to_audio_length() -> None:
    aligner = _RecordingAligner()
    audio = _FakeTensor(16000 * 2)  # 2s total
    result = transcribe_slice(audio, 1.5, 10.0, aligner)
    assert result == "j ɛ k"
    # Available tail is 0.5s -> 8000 samples.
    assert aligner.calls[0].numel() == 8000


# ---------------------------------------------------------------------------
# _coerce_intervals
# ---------------------------------------------------------------------------


def test_coerce_intervals_accepts_dict_tuple_list_and_ignores_garbage() -> None:
    specs = _coerce_intervals([
        {"start": 0.1, "end": 0.5, "text": "one"},
        [1.0, 1.5],
        (2.0, 2.7, "extra"),
        {"start": 3.0, "end": 3.0},  # zero-width dropped
        {"start": 4.0, "end": 3.5},  # reversed dropped
        "bad", None, 42,              # types dropped
    ])
    assert [(s.start, s.end) for s in specs] == [(0.1, 0.5), (1.0, 1.5), (2.0, 2.7)]


# ---------------------------------------------------------------------------
# transcribe_intervals
# ---------------------------------------------------------------------------


def test_transcribe_intervals_drives_aligner_per_interval(monkeypatch, tmp_path) -> None:
    fake_audio = _FakeTensor(16000 * 10)
    monkeypatch.setattr(ipa_mod, "_load_audio_mono_16k", lambda path: fake_audio)

    aligner = _RecordingAligner(output="phoneme")
    progress: List[Tuple[float, int]] = []

    def _cb(pct: float, idx: int) -> None:
        progress.append((pct, idx))

    audio_file = tmp_path / "clip.wav"
    audio_file.write_bytes(b"")
    intervals = [
        {"start": 0.0, "end": 0.5, "text": "یەک"},
        {"start": 0.5, "end": 1.0, "text": "دوو"},
    ]

    out = transcribe_intervals(
        audio_path=audio_file,
        intervals=intervals,
        aligner=aligner,  # type: ignore[arg-type]
        progress_callback=_cb,
    )
    assert out == [
        {"start": 0.0, "end": 0.5, "ipa": "phoneme"},
        {"start": 0.5, "end": 1.0, "ipa": "phoneme"},
    ]
    assert len(aligner.calls) == 2
    assert progress == [(50.0, 1), (100.0, 2)]


def test_transcribe_intervals_empty_list_returns_empty(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ipa_mod, "_load_audio_mono_16k", lambda path: _FakeTensor(0))
    audio_file = tmp_path / "clip.wav"
    audio_file.write_bytes(b"")
    assert transcribe_intervals(audio_path=audio_file, intervals=[]) == []


# ---------------------------------------------------------------------------
# _load_intervals_json
# ---------------------------------------------------------------------------


def test_load_intervals_json_accepts_three_shapes(tmp_path) -> None:
    artifact = tmp_path / "stt.json"
    artifact.write_text(json.dumps({"segments": [{"start": 0, "end": 1}]}))
    tier_dump = tmp_path / "ortho.json"
    tier_dump.write_text(json.dumps({"intervals": [{"start": 2, "end": 3}]}))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps([{"start": 4, "end": 5}]))
    full_annotation = tmp_path / "full.parse.json"
    full_annotation.write_text(
        json.dumps({"tiers": {"ortho": {"intervals": [{"start": 6, "end": 7}]}}})
    )

    assert _load_intervals_json(artifact) == [{"start": 0, "end": 1}]
    assert _load_intervals_json(tier_dump) == [{"start": 2, "end": 3}]
    assert _load_intervals_json(raw) == [{"start": 4, "end": 5}]
    assert _load_intervals_json(full_annotation) == [{"start": 6, "end": 7}]
