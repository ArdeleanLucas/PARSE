from __future__ import annotations

import math
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ai.providers.hf_whisper import HF_TRANSFORMERS_IMPORT_ERROR, HFWhisperProvider
from ai.providers.shared import _confidence_from_logprob


class _RecordingInputs(dict):
    def __init__(self, call_index: int) -> None:
        super().__init__({"input_features": f"features-{call_index}"})
        self.to_devices: list[str] = []

    def to(self, device: str) -> "_RecordingInputs":
        self.to_devices.append(device)
        return self


class _RecordingProcessor:
    def __init__(self, texts: list[str] | None = None) -> None:
        self.texts = texts or [" دەنگ "]
        self.calls: list[dict[str, Any]] = []
        self.decode_calls: list[dict[str, Any]] = []
        self.from_pretrained_calls: list[str] = []
        self.inputs: list[_RecordingInputs] = []

    def __call__(self, audio: Any, **kwargs: Any) -> _RecordingInputs:
        self.calls.append({"audio": audio, "kwargs": kwargs})
        inputs = _RecordingInputs(len(self.calls))
        self.inputs.append(inputs)
        return inputs

    def batch_decode(self, sequences: Any, **kwargs: Any) -> list[str]:
        self.decode_calls.append({"sequences": sequences, "kwargs": kwargs})
        if not self.texts:
            return [""]
        return [self.texts.pop(0)]


class _RecordingModel:
    def __init__(self, generated: list[Any] | None = None) -> None:
        self.generated = generated or [_generated_result(selected_token=1, score_row=[0.0, 1.0])]
        self.from_pretrained_calls: list[str] = []
        self.to_devices: list[str] = []
        self.eval_calls = 0
        self.generate_calls: list[dict[str, Any]] = []

    def to(self, device: str) -> "_RecordingModel":
        self.to_devices.append(device)
        return self

    def eval(self) -> "_RecordingModel":
        self.eval_calls += 1
        return self

    def generate(self, **kwargs: Any) -> Any:
        self.generate_calls.append(kwargs)
        if not self.generated:
            return _generated_result(selected_token=1, score_row=[0.0, 1.0])
        return self.generated.pop(0)


def _generated_result(*, selected_token: int, score_row: list[float]) -> Any:
    return types.SimpleNamespace(
        sequences=np.asarray([[0, selected_token]], dtype=np.int64),
        scores=(np.asarray([score_row], dtype=np.float32),),
        token_timestamps=np.asarray([[0.0, 1.0]], dtype=np.float32),
    )


def _expected_confidence(score_row: list[float], selected_token: int) -> float:
    log_denom = math.log(sum(math.exp(value) for value in score_row))
    avg_logprob = float(score_row[selected_token]) - log_denom
    return _confidence_from_logprob(avg_logprob)


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


def _install_transformers_stub(
    monkeypatch: pytest.MonkeyPatch,
    *,
    processor: _RecordingProcessor | None = None,
    model: _RecordingModel | None = None,
) -> tuple[_RecordingProcessor, _RecordingModel]:
    processor = processor or _RecordingProcessor()
    model = model or _RecordingModel()

    class WhisperProcessor:
        @staticmethod
        def from_pretrained(model_path: str) -> _RecordingProcessor:
            processor.from_pretrained_calls.append(model_path)
            return processor

    class WhisperForConditionalGeneration:
        @staticmethod
        def from_pretrained(model_path: str) -> _RecordingModel:
            model.from_pretrained_calls.append(model_path)
            return model

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        types.SimpleNamespace(
            WhisperProcessor=WhisperProcessor,
            WhisperForConditionalGeneration=WhisperForConditionalGeneration,
        ),
    )
    return processor, model


def _install_soundfile_stub(
    monkeypatch: pytest.MonkeyPatch,
    *,
    samples: int,
    sample_rate: int = 16000,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def read(path: str, *, dtype: str, always_2d: bool) -> tuple[np.ndarray, int]:
        calls.append({"path": path, "dtype": dtype, "always_2d": always_2d})
        assert dtype == "float32"
        assert always_2d is True
        return np.zeros((samples, 1), dtype=np.float32), sample_rate

    monkeypatch.setitem(sys.modules, "soundfile", types.SimpleNamespace(read=read))
    return calls


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


def test_transcribe_uses_hf_processor_model_with_resolved_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    _install_soundfile_stub(monkeypatch, samples=16000, sample_rate=16000)
    processor, model = _install_transformers_stub(
        monkeypatch,
        processor=_RecordingProcessor(texts=[" یەک "]),
        model=_RecordingModel(generated=[_generated_result(selected_token=1, score_row=[0.0, 1.0])]),
    )
    provider = HFWhisperProvider(config=_config(language="sdh"))

    result = provider.transcribe(audio_path)

    assert processor.from_pretrained_calls == ["razhan/whisper-base-sdh"]
    assert model.from_pretrained_calls == ["razhan/whisper-base-sdh"]
    assert model.to_devices == ["cuda:0"]
    assert model.eval_calls == 1
    assert len(processor.calls) == 1
    assert processor.calls[0]["kwargs"] == {"sampling_rate": 16000, "return_tensors": "pt"}
    assert processor.calls[0]["audio"].shape == (16000,)
    assert processor.inputs[0].to_devices == ["cuda:0"]
    assert model.generate_calls == [
        {
            "input_features": "features-1",
            "return_dict_in_generate": True,
            "output_scores": True,
            "return_timestamps": True,
            "language": "fa",
            "task": "transcribe",
        }
    ]
    assert result == [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "یەک",
            "confidence": pytest.approx(_expected_confidence([0.0, 1.0], 1)),
        }
    ]
    assert "[ORTH] HFWhisperProvider loaded: model=razhan/whisper-base-sdh device=cuda:0 language=fa" in capsys.readouterr().err


def test_transcribe_emits_multi_segment_for_long_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "long.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    _install_soundfile_stub(monkeypatch, samples=16000 * 90, sample_rate=16000)
    processor, model = _install_transformers_stub(
        monkeypatch,
        processor=_RecordingProcessor(texts=["first chunk", "second chunk", "third chunk"]),
        model=_RecordingModel(
            generated=[
                _generated_result(selected_token=1, score_row=[0.0, 1.0]),
                _generated_result(selected_token=1, score_row=[0.0, 0.0]),
                _generated_result(selected_token=0, score_row=[2.0, 0.0]),
            ]
        ),
    )
    progress: list[tuple[float, int]] = []
    provider = HFWhisperProvider(config=_config(language="sd"))

    result = provider.transcribe(audio_path, progress_callback=lambda pct, done: progress.append((pct, done)))

    assert [call["audio"].shape for call in processor.calls] == [(16000 * 30,), (16000 * 30,), (16000 * 30,)]
    assert len(model.generate_calls) == 3
    assert result == [
        {"start": 0.0, "end": 30.0, "text": "first chunk", "confidence": pytest.approx(_expected_confidence([0.0, 1.0], 1))},
        {"start": 30.0, "end": 60.0, "text": "second chunk", "confidence": pytest.approx(_expected_confidence([0.0, 0.0], 1))},
        {"start": 60.0, "end": 90.0, "text": "third chunk", "confidence": pytest.approx(_expected_confidence([2.0, 0.0], 0))},
    ]
    assert progress == [(pytest.approx(100.0 / 3.0), 1), (pytest.approx(200.0 / 3.0), 2), (100.0, 3)]


def test_transcribe_segments_in_memory_slices_audio_and_reports_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor, _model = _install_transformers_stub(
        monkeypatch,
        processor=_RecordingProcessor(texts=["یەک", "دوو"]),
        model=_RecordingModel(
            generated=[
                _generated_result(selected_token=1, score_row=[0.0, 1.0]),
                _generated_result(selected_token=1, score_row=[0.0, 0.0]),
            ]
        ),
    )
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
    first_window = processor.calls[0]["audio"]
    second_window = processor.calls[1]["audio"]
    assert isinstance(first_window, np.ndarray)
    assert isinstance(second_window, np.ndarray)
    assert first_window.shape == (8000,)
    assert second_window.shape == (20000,)
    assert all(call["kwargs"] == {"sampling_rate": 16000, "return_tensors": "pt"} for call in processor.calls)
    assert progress == [(50.0, 1), (100.0, 2)]


def test_transcribe_segments_in_memory_passes_sampling_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor, _model = _install_transformers_stub(monkeypatch, processor=_RecordingProcessor(texts=["یەک"]))
    provider = HFWhisperProvider(config=_config(language="sd"))
    audio = np.arange(22050, dtype=np.float32)

    provider.transcribe_segments_in_memory(audio, [(0.0, 1.0)], sample_rate=22050)

    assert processor.calls[0]["kwargs"]["sampling_rate"] == 22050
    assert processor.calls[0]["audio"].shape == (22050,)


def test_transcribe_clip_accepts_sampling_rate_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor, _model = _install_transformers_stub(monkeypatch, processor=_RecordingProcessor(texts=["سێ"]))
    provider = HFWhisperProvider(config=_config(language="fa"))

    provider.transcribe_clip({"raw": np.zeros(22050, dtype=np.float32), "sampling_rate": 22050})

    assert processor.calls[0]["kwargs"]["sampling_rate"] == 22050
    assert processor.calls[0]["audio"].shape == (22050,)


def test_transcribe_clip_returns_real_confidence_not_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _processor, _model = _install_transformers_stub(
        monkeypatch,
        processor=_RecordingProcessor(texts=[" سێ "]),
        model=_RecordingModel(generated=[_generated_result(selected_token=0, score_row=[0.0, 1.0])]),
    )
    provider = HFWhisperProvider(config=_config(language="fa"))

    text, confidence = provider.transcribe_clip(np.zeros(16000, dtype=np.float32))

    assert text == "سێ"
    assert confidence == pytest.approx(_expected_confidence([0.0, 1.0], 0))
    assert confidence != 1.0
