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


class _RecordingPromptIds:
    def __init__(self, text: str) -> None:
        self.text = text
        self.to_devices: list[str] = []

    def to(self, device: str) -> "_RecordingPromptIds":
        self.to_devices.append(device)
        return self


class _RecordingProcessor:
    def __init__(self, texts: list[str] | None = None) -> None:
        self.texts = texts or [" دەنگ "]
        self.calls: list[dict[str, Any]] = []
        self.decode_calls: list[dict[str, Any]] = []
        self.from_pretrained_calls: list[str] = []
        self.inputs: list[_RecordingInputs] = []
        self.prompt_ids_calls: list[dict[str, Any]] = []
        self.prompt_ids: list[_RecordingPromptIds] = []

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

    def get_prompt_ids(self, text: str, *, return_tensors: str) -> _RecordingPromptIds:
        self.prompt_ids_calls.append({"text": text, "return_tensors": return_tensors})
        prompt_ids = _RecordingPromptIds(text)
        self.prompt_ids.append(prompt_ids)
        return prompt_ids


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


class _FailingGenerateModel(_RecordingModel):
    def generate(self, **kwargs: Any) -> Any:
        self.generate_calls.append(kwargs)
        raise ValueError("synthetic generate failure")


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


def _guard_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs = {
        "compression_ratio_threshold": 1.8,
        "no_repeat_ngram_size": 3,
        "repetition_penalty": 1.2,
        "condition_on_prev_tokens": False,
        "temperature": 0.0,
        "do_sample": False,
    }
    kwargs.update(overrides)
    return kwargs


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


def test_unload_model_drops_loaded_objects_and_clears_cuda(monkeypatch, capsys):
    _processor, model = _install_transformers_stub(monkeypatch)
    cuda_calls: list[str] = []

    monkeypatch.setitem(
        sys.modules,
        "torch",
        types.SimpleNamespace(
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                empty_cache=lambda: cuda_calls.append("empty_cache"),
                synchronize=lambda: cuda_calls.append("synchronize"),
            )
        ),
    )

    provider = HFWhisperProvider(config=_config())
    provider._load_model()

    provider.unload_model()
    provider.unload_model()

    assert provider._processor is None
    assert provider._model is None
    assert "cpu" in model.to_devices
    assert cuda_calls == ["empty_cache", "synchronize", "empty_cache", "synchronize"]
    assert "HFWhisperProvider unloaded model + cleared CUDA cache" in capsys.readouterr().err


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
    assert processor.prompt_ids_calls == [{"text": "ignored by hf", "return_tensors": "pt"}]
    assert len(processor.prompt_ids) == 1
    assert processor.prompt_ids[0].to_devices == ["cuda:0"]
    assert model.generate_calls == [
        {
            "input_features": "features-1",
            "return_dict_in_generate": True,
            "output_scores": True,
            **_guard_kwargs(),
            "prompt_ids": processor.prompt_ids[0],
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


def test_repetition_guards_passed_to_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    processor, model = _install_transformers_stub(monkeypatch, processor=_RecordingProcessor(texts=["یەک"]))
    provider = HFWhisperProvider(
        config=_config(
            compression_ratio_threshold=2.0,
            no_repeat_ngram_size=4,
            repetition_penalty=1.35,
            condition_on_previous_text=True,
            initial_prompt="ABC",
        )
    )

    provider.transcribe_clip(np.zeros(16000, dtype=np.float32))

    assert processor.prompt_ids_calls == [{"text": "ABC", "return_tensors": "pt"}]
    assert len(processor.prompt_ids) == 1
    assert processor.prompt_ids[0].to_devices == ["cuda:0"]
    assert model.generate_calls == [
        {
            "input_features": "features-1",
            "return_dict_in_generate": True,
            "output_scores": True,
            **_guard_kwargs(
                compression_ratio_threshold=2.0,
                no_repeat_ngram_size=4,
                repetition_penalty=1.35,
                condition_on_prev_tokens=True,
            ),
            "prompt_ids": processor.prompt_ids[0],
            "language": "fa",
            "task": "transcribe",
        }
    ]


def test_initial_prompt_empty_skips_prompt_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    processor, model = _install_transformers_stub(monkeypatch, processor=_RecordingProcessor(texts=["یەک"]))
    provider = HFWhisperProvider(config=_config(initial_prompt=""))

    provider.transcribe_clip(np.zeros(16000, dtype=np.float32))

    assert processor.prompt_ids_calls == []
    assert "prompt_ids" not in model.generate_calls[0]


def test_legacy_config_keys_still_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _processor, model = _install_transformers_stub(monkeypatch, processor=_RecordingProcessor(texts=["یەک"]))
    provider = HFWhisperProvider(config=_config(initial_prompt="", condition_on_previous_text=False))

    provider.transcribe_clip(np.zeros(16000, dtype=np.float32))

    assert model.generate_calls[0]["condition_on_prev_tokens"] is False


def test_transcribe_breaks_on_should_cancel_chunked_full_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audio_path = tmp_path / "long.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    _install_soundfile_stub(monkeypatch, samples=16000 * 90, sample_rate=16000)
    _processor, model = _install_transformers_stub(
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
    provider = HFWhisperProvider(config=_config(language="sd"))
    cancel_checks = 0

    def should_cancel() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks >= 3

    result = provider.transcribe(audio_path, should_cancel=should_cancel)

    assert [seg["text"] for seg in result] == ["first chunk", "second chunk"]
    assert len(model.generate_calls) == 2
    stderr = capsys.readouterr().err
    assert "[ORTH] cancel requested at chunk 3/3" in stderr
    assert "returning 2 partial segments" in stderr


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
    assert processor.prompt_ids_calls == [
        {"text": "ignored by hf", "return_tensors": "pt"},
        {"text": "ignored by hf", "return_tensors": "pt"},
    ]
    assert [prompt_ids.to_devices for prompt_ids in processor.prompt_ids] == [["cuda:0"], ["cuda:0"]]
    assert _model.generate_calls == [
        {
            "input_features": "features-1",
            "return_dict_in_generate": True,
            "output_scores": True,
            **_guard_kwargs(),
            "prompt_ids": processor.prompt_ids[0],
            "language": "fa",
            "task": "transcribe",
        },
        {
            "input_features": "features-2",
            "return_dict_in_generate": True,
            "output_scores": True,
            **_guard_kwargs(),
            "prompt_ids": processor.prompt_ids[1],
            "language": "fa",
            "task": "transcribe",
        },
    ]
    assert progress == [(50.0, 1), (100.0, 2)]


def test_transcribe_segments_in_memory_breaks_on_should_cancel(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _processor, model = _install_transformers_stub(
        monkeypatch,
        processor=_RecordingProcessor(texts=["یەک", "دوو", "سێ", "چوار", "پێنج"]),
        model=_RecordingModel(
            generated=[
                _generated_result(selected_token=1, score_row=[0.0, 1.0]),
                _generated_result(selected_token=1, score_row=[0.0, 0.0]),
                _generated_result(selected_token=1, score_row=[0.0, 0.0]),
                _generated_result(selected_token=1, score_row=[0.0, 0.0]),
                _generated_result(selected_token=1, score_row=[0.0, 0.0]),
            ]
        ),
    )
    provider = HFWhisperProvider(config=_config(language="sd"))
    audio = np.arange(16000 * 6, dtype=np.float32)
    cancel_checks = 0

    def should_cancel() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks >= 3

    result = provider.transcribe_segments_in_memory(
        audio,
        [(0.0, 0.5), (1.0, 1.5), (2.0, 2.5), (3.0, 3.5), (4.0, 4.5)],
        sample_rate=16000,
        should_cancel=should_cancel,
    )

    assert [seg["text"] for seg in result] == ["یەک", "دوو"]
    assert len(model.generate_calls) == 2
    stderr = capsys.readouterr().err
    assert "[ORTH] cancel requested at interval 3/5 (2.00-2.50s)" in stderr
    assert "returning 2 partial segments" in stderr


def test_transcribe_segments_in_memory_should_cancel_default_none_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _processor, model = _install_transformers_stub(
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

    result = provider.transcribe_segments_in_memory(
        np.zeros(16000 * 2, dtype=np.float32),
        [(0.0, 0.5), (1.0, 1.5)],
        sample_rate=16000,
        should_cancel=None,
    )

    assert [seg["text"] for seg in result] == ["یەک", "دوو"]
    assert len(model.generate_calls) == 2


def test_transcribe_segments_in_memory_logs_exception_class_on_generate_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_transformers_stub(
        monkeypatch,
        processor=_RecordingProcessor(texts=["unused"]),
        model=_FailingGenerateModel(),
    )
    provider = HFWhisperProvider(config=_config(language="sd"))

    result = provider.transcribe_segments_in_memory(
        np.zeros(16000, dtype=np.float32),
        [(0.0, 1.0)],
        sample_rate=16000,
    )

    assert result == []
    stderr = capsys.readouterr().err
    assert "ValueError" in stderr
    assert "synthetic generate failure" in stderr


def test_transcribe_segments_in_memory_passes_sampling_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor, _model = _install_transformers_stub(monkeypatch, processor=_RecordingProcessor(texts=["یەک"]))
    provider = HFWhisperProvider(config=_config(language="sd"))
    audio = np.arange(22050, dtype=np.float32)

    provider.transcribe_segments_in_memory(audio, [(0.0, 1.0)], sample_rate=22050)

    assert processor.calls[0]["kwargs"]["sampling_rate"] == 16000
    expected_samples = int(round(22050 * 16000 / 22050))
    assert processor.calls[0]["audio"].shape == (expected_samples,)


def test_transcribe_segments_in_memory_resamples_non_16k_to_16k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor, _model = _install_transformers_stub(
        monkeypatch, processor=_RecordingProcessor(texts=["یەک"])
    )
    provider = HFWhisperProvider(config=_config(language="sd"))
    audio = np.zeros(22050, dtype=np.float32)

    provider.transcribe_segments_in_memory(audio, [(0.0, 1.0)], sample_rate=22050)

    forwarded = processor.calls[0]
    assert forwarded["kwargs"]["sampling_rate"] == 16000
    assert forwarded["audio"].shape == (16000,)
    assert forwarded["audio"].dtype == np.float32
    assert forwarded["audio"].flags["C_CONTIGUOUS"]


def test_transcribe_clip_accepts_sampling_rate_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor, _model = _install_transformers_stub(monkeypatch, processor=_RecordingProcessor(texts=["سێ"]))
    provider = HFWhisperProvider(config=_config(language="fa"))

    provider.transcribe_clip({"raw": np.zeros(22050, dtype=np.float32), "sampling_rate": 22050})

    assert processor.calls[0]["kwargs"]["sampling_rate"] == 16000
    expected_samples = int(round(22050 * 16000 / 22050))
    assert processor.calls[0]["audio"].shape == (expected_samples,)


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
