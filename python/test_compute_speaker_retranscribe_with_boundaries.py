"""Unit tests for _compute_speaker_retranscribe_with_boundaries.

The boundary-constrained STT job re-runs faster-whisper on each
``tiers.ortho_words`` interval individually, in memory, and writes the
result to ``coarse_transcripts/<speaker>.json`` with a
``source: "boundary_constrained"`` provenance marker. These tests stub
the audio loader and a fake STT provider so they stay hermetic (no
torch, no real model).
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, List, Tuple

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _FakeAudioTensor:
    def numel(self) -> int:
        return 16000 * 60

    @property
    def shape(self) -> Tuple[int]:
        return (16000 * 60,)


class _StubSttProvider:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def transcribe_segments_in_memory(
        self,
        audio_array: Any,
        intervals: List[Tuple[float, float]],
        *,
        language: str | None = None,
        progress_callback=None,
        sample_rate: int = 16000,
    ) -> List[Dict[str, Any]]:
        self.calls.append({
            "intervals": list(intervals),
            "language": language,
            "sample_rate": sample_rate,
        })
        if progress_callback is not None:
            for index, _interval in enumerate(intervals, start=1):
                progress_callback((index / len(intervals)) * 100.0, index)
        return [
            {
                "start": float(start),
                "end": float(end),
                "text": f"seg_{start:.2f}",
                "confidence": 0.9,
                "words": [{"word": "w", "start": float(start), "end": float(end), "prob": 0.9}],
            }
            for start, end in intervals
        ]


class _LegacyProvider:
    def transcribe(self, *args, **kwargs):
        raise AssertionError("transcribe must not be called by boundary-constrained STT")


def _seed_annotation(
    tmp_path: pathlib.Path,
    speaker: str,
    ortho_words: List[Dict[str, Any]] | None,
    source_audio: str = "raw/Fail02.wav",
) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    tiers: Dict[str, Any] = {
        "ipa": {"type": "interval", "display_order": 1, "intervals": []},
        "ortho": {"type": "interval", "display_order": 2, "intervals": []},
        "concept": {"type": "interval", "display_order": 3, "intervals": []},
        "speaker": {"type": "interval", "display_order": 4, "intervals": []},
    }
    if ortho_words is not None:
        tiers["ortho_words"] = {
            "type": "interval",
            "display_order": 5,
            "intervals": ortho_words,
        }
    annotation = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 60.0,
        "tiers": tiers,
        "metadata": {
            "language_code": "sdh",
            "created": "2026-01-01T00:00:00Z",
            "modified": "2026-01-01T00:00:00Z",
        },
    }
    (annotations_dir / f"{speaker}.parse.json").write_text(json.dumps(annotation), encoding="utf-8")


def _write_fake_source_wav(tmp_path: pathlib.Path, rel_path: str) -> None:
    wav_path = tmp_path / rel_path
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")


def _read_cache(tmp_path: pathlib.Path, speaker: str) -> Dict[str, Any]:
    return json.loads((tmp_path / "coarse_transcripts" / f"{speaker}.json").read_text("utf-8"))


def _install_stubs(tmp_path: pathlib.Path, monkeypatch, provider: Any) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)
    monkeypatch.setattr(server, "get_stt_provider", lambda: provider)
    from ai import forced_align as fa

    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda path: _FakeAudioTensor())


def test_writes_boundary_constrained_cache(tmp_path, monkeypatch):
    provider = _StubSttProvider()
    _install_stubs(tmp_path, monkeypatch, provider)

    ortho_words = [
        {"start": 1.0, "end": 1.4, "text": "one"},
        {"start": 2.0, "end": 2.6, "text": "two"},
        {"start": 3.0, "end": 3.5, "text": "three"},
    ]
    _seed_annotation(tmp_path, "Fail02", ortho_words)
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_retranscribe_with_boundaries(
        "j1",
        {"speaker": "Fail02", "language": "ku"},
    )

    assert result["speaker"] == "Fail02"
    assert result["language"] == "ku"
    assert result["boundary_intervals"] == 3
    assert result["segments_written"] == 3
    assert result["source"] == "boundary_constrained"

    assert len(provider.calls) == 1
    assert provider.calls[0]["language"] == "ku"
    assert provider.calls[0]["intervals"] == [(1.0, 1.4), (2.0, 2.6), (3.0, 3.5)]

    cache = _read_cache(tmp_path, "Fail02")
    assert cache["source"] == "boundary_constrained"
    assert cache["language"] == "ku"
    assert cache["speaker"] == "Fail02"
    assert len(cache["segments"]) == 3
    assert [round(segment["start"], 2) for segment in cache["segments"]] == [1.0, 2.0, 3.0]


def test_skips_zero_and_inverted_bnd_intervals(tmp_path, monkeypatch):
    provider = _StubSttProvider()
    _install_stubs(tmp_path, monkeypatch, provider)

    ortho_words = [
        {"start": 1.0, "end": 1.0, "text": "zero"},
        {"start": 2.0, "end": 1.5, "text": "inv"},
        {"start": 3.0, "end": 3.5, "text": "ok"},
    ]
    _seed_annotation(tmp_path, "Fail02", ortho_words)
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_retranscribe_with_boundaries("j1", {"speaker": "Fail02"})

    assert result["boundary_intervals"] == 1
    assert provider.calls[0]["intervals"] == [(3.0, 3.5)]


def test_empty_language_becomes_none_for_auto_detect(tmp_path, monkeypatch):
    provider = _StubSttProvider()
    _install_stubs(tmp_path, monkeypatch, provider)

    ortho_words = [{"start": 1.0, "end": 1.5, "text": "x"}]
    _seed_annotation(tmp_path, "Fail02", ortho_words)
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_retranscribe_with_boundaries(
        "j1",
        {"speaker": "Fail02", "language": "  "},
    )

    assert result["language"] is None
    assert provider.calls[0]["language"] is None


def test_raises_when_ortho_words_missing(tmp_path, monkeypatch):
    provider = _StubSttProvider()
    _install_stubs(tmp_path, monkeypatch, provider)

    _seed_annotation(tmp_path, "Fail02", ortho_words=None)
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    with pytest.raises(RuntimeError, match="Refine boundaries first"):
        server._compute_speaker_retranscribe_with_boundaries("j1", {"speaker": "Fail02"})

    assert not (tmp_path / "coarse_transcripts" / "Fail02.json").exists()


def test_raises_when_ortho_words_empty(tmp_path, monkeypatch):
    provider = _StubSttProvider()
    _install_stubs(tmp_path, monkeypatch, provider)

    _seed_annotation(tmp_path, "Fail02", ortho_words=[])
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    with pytest.raises(RuntimeError, match="Refine boundaries first"):
        server._compute_speaker_retranscribe_with_boundaries("j1", {"speaker": "Fail02"})


def test_raises_when_provider_lacks_in_memory_method(tmp_path, monkeypatch):
    provider = _LegacyProvider()
    _install_stubs(tmp_path, monkeypatch, provider)

    _seed_annotation(tmp_path, "Fail02", [{"start": 0.0, "end": 1.0, "text": "x"}])
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    with pytest.raises(RuntimeError, match="in-memory segment transcription"):
        server._compute_speaker_retranscribe_with_boundaries("j1", {"speaker": "Fail02"})


@pytest.mark.parametrize(
    "alias",
    [
        "retranscribe_with_boundaries",
        "retranscribe-with-boundaries",
        "boundary_constrained_stt",
        "boundary-constrained-stt",
        "bnd_stt",
    ],
)
def test_run_compute_job_dispatches_all_aliases(tmp_path, monkeypatch, alias):
    provider = _StubSttProvider()
    _install_stubs(tmp_path, monkeypatch, provider)

    speaker = f"Disp_{alias.replace('-', '_')}"
    _seed_annotation(
        tmp_path,
        speaker,
        [{"start": 0.0, "end": 1.0, "text": "x"}],
        source_audio=f"raw/{speaker}.wav",
    )
    _write_fake_source_wav(tmp_path, f"raw/{speaker}.wav")

    captured: Dict[str, Any] = {}

    def fake_complete(job_id, result, **kwargs):
        captured["result"] = result

    def fake_error(job_id, err):
        captured["error"] = err

    monkeypatch.setattr(server, "_set_job_complete", fake_complete)
    monkeypatch.setattr(server, "_set_job_error", fake_error)

    server._run_compute_job(f"j-{alias}", alias, {"speaker": speaker})
    assert "error" not in captured, captured
    assert captured["result"]["source"] == "boundary_constrained"


def test_write_stt_cache_omits_source_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    server._write_stt_cache(
        "Fail02",
        "raw/Fail02.wav",
        "ku",
        [{"start": 0.0, "end": 1.0, "text": "hi"}],
    )

    cache = _read_cache(tmp_path, "Fail02")
    assert "source" not in cache


def test_write_stt_cache_emits_source_when_set(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    server._write_stt_cache(
        "Fail02",
        "raw/Fail02.wav",
        "ku",
        [{"start": 0.0, "end": 1.0, "text": "hi"}],
        source="boundary_constrained",
    )

    cache = _read_cache(tmp_path, "Fail02")
    assert cache["source"] == "boundary_constrained"
