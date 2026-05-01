from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ai.providers.hf_whisper import HF_TRANSFORMERS_IMPORT_ERROR, HFWhisperProvider


class _RecordingPipeline:
    calls: list[dict[str, Any]] = []

    def __init__(self, *, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = responses or [{"text": " دەنگ "}]

    def __call__(self, audio: Any, **kwargs: Any) -> dict[str, Any]:
        type(self).calls.append({"audio": audio, "kwargs": kwargs})
        if not self.responses:
            return {"text": ""}
        return self.responses.pop(0)


def _config(**overrides: Any) -> dict[str, Any]:
    section = {
        "backend": "hf",
        "model_path": "razhan/whisper-base-sdh",
        "language": "sd",
        "device": "cuda",
        "compute_type": "float16",
        "vad_filter": True,
        "condition_on_previous_text": False,
        "compression_ratio_threshold": 1.8,
        "initial_prompt": "ignored by hf",
        "refine_lexemes": False,
    }
    section.update(overrides)
    return {"ortho": section}


def _install_transformers_stub(monkeypatch: pytest.MonkeyPatch, pipe: _RecordingPipeline) -> list[dict[str, Any]]:
    pipeline_calls: list[dict[str, Any]] = []

    def pipeline(task: str, **kwargs: Any) -> _RecordingPipeline:
        pipeline_calls.append({"task": task, "kwargs": kwargs})
        return pipe

    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(pipeline=pipeline))
    return pipeline_calls


def test_module_import_does_not_require_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "transformers", None)

    provider = HFWhisperProvider(config=_config())

    assert provider.model_path == "razhan/whisper-base-sdh"
    assert provider.language == "sd"
    assert provider.device == "cuda"


def test_missing_transformers_raises_clear_error_on_first_model_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "transformers", None)
    provider = HFWhisperProvider(config=_config())

    with pytest.raises(ImportError, match="HF ortho backend") as excinfo:
        provider.warm_up()

    assert str(excinfo.value) == HF_TRANSFORMERS_IMPORT_ERROR


def test_ct2_directory_is_rejected_with_actionable_message(tmp_path: Path) -> None:
    ct2_dir = tmp_path / "razhan-sdh-ct2"
    ct2_dir.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (ct2_dir / name).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="expected HuggingFace repo id") as excinfo:
        HFWhisperProvider(config=_config(model_path=str(ct2_dir)))

    message = str(excinfo.value)
    assert str(ct2_dir) in message
    assert "ortho.model_path" in message
    assert "ortho.backend='faster-whisper'" in message


def test_transcribe_uses_hf_pipeline_with_resolved_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    pipe = _RecordingPipeline(responses=[{"text": " یەک "}])
    pipeline_calls = _install_transformers_stub(monkeypatch, pipe)
    _RecordingPipeline.calls = []
    provider = HFWhisperProvider(config=_config(language="sdh"))

    result = provider.transcribe(audio_path)

    assert pipeline_calls == [
        {
            "task": "automatic-speech-recognition",
            "kwargs": {"model": "razhan/whisper-base-sdh", "device": "cuda:0"},
        }
    ]
    assert _RecordingPipeline.calls == [
        {
            "audio": str(audio_path),
            "kwargs": {"generate_kwargs": {"language": "fa", "task": "transcribe"}},
        }
    ]
    assert result == [{"start": 0.0, "end": 0.0, "text": "یەک", "confidence": 1.0}]
    assert "[ORTH] HFWhisperProvider loaded: model=razhan/whisper-base-sdh device=cuda:0 language=fa" in capsys.readouterr().err


def test_transcribe_segments_in_memory_slices_audio_and_reports_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipe = _RecordingPipeline(responses=[{"text": "یەک"}, {"text": "دوو"}])
    _install_transformers_stub(monkeypatch, pipe)
    _RecordingPipeline.calls = []
    provider = HFWhisperProvider(config=_config(language="sd"))
    audio = np.arange(16000 * 3, dtype=np.float32)
    progress: list[tuple[float, int]] = []

    result = provider.transcribe_segments_in_memory(
        audio,
        [(0.5, 1.0), (1.0, 2.25)],
        progress_callback=lambda pct, done: progress.append((pct, done)),
        sample_rate=16000,
    )

    assert [seg["text"] for seg in result] == ["یەک", "دوو"]
    assert [seg["start"] for seg in result] == [pytest.approx(0.5), pytest.approx(1.0)]
    assert [seg["end"] for seg in result] == [pytest.approx(1.0), pytest.approx(2.25)]
    first_window = _RecordingPipeline.calls[0]["audio"]
    second_window = _RecordingPipeline.calls[1]["audio"]
    assert isinstance(first_window, np.ndarray)
    assert isinstance(second_window, np.ndarray)
    assert first_window.shape == (8000,)
    assert second_window.shape == (20000,)
    assert all(call["kwargs"] == {"generate_kwargs": {"language": "fa", "task": "transcribe"}} for call in _RecordingPipeline.calls)
    assert progress == [(50.0, 1), (100.0, 2)]


def test_transcribe_clip_returns_text_with_constant_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipe = _RecordingPipeline(responses=[{"text": " سێ "}])
    _install_transformers_stub(monkeypatch, pipe)
    provider = HFWhisperProvider(config=_config(language="fa"))

    text, confidence = provider.transcribe_clip(np.zeros(16000, dtype=np.float32))

    assert text == "سێ"
    assert confidence == 1.0
