from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Tuple

import ai.provider as provider_module

from .local_whisper import _normalize_whisper_language

if TYPE_CHECKING:
    from ai.provider import Segment, SegmentWithWords

HF_TRANSFORMERS_IMPORT_ERROR = (
    "transformers is required for the HF ortho backend; install with "
    "'pip install transformers' or set ortho.backend='faster-whisper' in ai_config.json"
)

_CT2_REQUIRED_FILES = frozenset({"model.bin", "config.json", "tokenizer.json"})
_HF_WHISPER_SAMPLE_RATE = 16000
_HF_WHISPER_CHUNK_SECONDS = 30.0
# Whisper's special/control tokens occupy the high-id range; skip them when
# averaging generated-token logprobs so confidence reflects lexical content.
_WHISPER_SPECIAL_TOKEN_MIN_ID = 50257


def _looks_like_ct2_whisper_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    children = {child.name for child in path.iterdir()}
    if not _CT2_REQUIRED_FILES.issubset(children):
        return False
    has_hf_weights = any(
        child.name == "pytorch_model.bin"
        or child.name == "model.safetensors"
        or child.name.startswith("pytorch_model-")
        or child.name.endswith(".safetensors")
        for child in path.iterdir()
    )
    return not has_hf_weights


def _ct2_model_path_error(model_path: str) -> str:
    return (
        "[ORTH config error] ortho.model_path expected HuggingFace repo id like "
        "`razhan/whisper-base-sdh` or a local HF-format directory; got CT2 "
        "directory `{0}` — either change ortho.model_path to the HF id, or "
        "revert ortho.backend='faster-whisper'"
    ).format(model_path)


def _normalize_pipeline_device(device: str) -> str:
    normalized = str(device or "").strip().lower()
    if not normalized:
        return "cpu"
    if normalized == "cuda":
        return "cuda:0"
    if normalized.startswith("cuda:"):
        return normalized
    return normalized


def _tensor_like_to_list(value: Any) -> Any:
    """Return a Python list for torch/numpy/list-like values without importing torch."""
    current = value
    detach = getattr(current, "detach", None)
    if callable(detach):
        current = detach()
    cpu = getattr(current, "cpu", None)
    if callable(cpu):
        current = cpu()
    numpy = getattr(current, "numpy", None)
    if callable(numpy):
        current = numpy()
    tolist = getattr(current, "tolist", None)
    if callable(tolist):
        return tolist()
    return current


def _first_row(value: Any) -> List[Any]:
    data = _tensor_like_to_list(value)
    if data is None:
        return []
    if isinstance(data, (list, tuple)):
        if data and isinstance(data[0], (list, tuple)):
            return list(data[0])
        return list(data)
    try:
        return list(data)
    except TypeError:
        return [data]


def _logprob_for_token(score_row: Iterable[Any], token_id: int) -> Optional[float]:
    row = [float(value) for value in score_row]
    if token_id < 0 or token_id >= len(row) or not row:
        return None
    max_score = max(row)
    log_denom = max_score + math.log(sum(math.exp(value - max_score) for value in row))
    return row[token_id] - log_denom


def _avg_logprob_from_scores(scores: Any, sequences: Any) -> float:
    """Mean log-softmax probability of each generated token's selected id.

    ``scores`` is the tuple returned by ``generate(output_scores=True)`` — one
    tensor per generation step, shape ``(batch, vocab_size)``. ``sequences`` is
    the ``(batch, seq_len)`` tensor of token ids. The decoder prefix is skipped
    by aligning scores against the trailing generated ids, and Whisper special
    token ids are ignored. Returns ``0.0`` if no real tokens were generated.
    """
    if not scores:
        return 0.0
    score_steps = list(scores)
    token_ids = [int(token_id) for token_id in _first_row(sequences)]
    if not token_ids:
        return 0.0

    aligned_tokens = token_ids[-len(score_steps):]
    aligned_scores = score_steps[-len(aligned_tokens):]
    logprobs: List[float] = []
    for score_step, token_id in zip(aligned_scores, aligned_tokens):
        if token_id >= _WHISPER_SPECIAL_TOKEN_MIN_ID:
            continue
        logprob = _logprob_for_token(_first_row(score_step), token_id)
        if logprob is not None:
            logprobs.append(logprob)
    if not logprobs:
        return 0.0
    return sum(logprobs) / float(len(logprobs))


class HFWhisperProvider(provider_module.AIProvider):
    """ORTH provider backed by Hugging Face Transformers Whisper FP32.

    This provider intentionally accepts the same section knobs as the legacy
    faster-whisper ORTH config, but decoder-side CT2 mitigations are not applied
    on the HF path. Empirical Saha01 runs showed FP32 Transformers avoids the
    CT2 contamination without VAD/temperature/prompt workarounds.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
        *,
        config_section: str = "ortho",
    ) -> None:
        super().__init__(config=config, config_path=config_path)
        self.config_section = str(config_section or "ortho").strip() or "ortho"
        section_config = self.config.get(self.config_section, {})
        if not isinstance(section_config, dict):
            section_config = {}

        self.model_path = str(section_config.get("model_path", "")).strip()
        if not self.model_path:
            raise ValueError(
                "[ORTH config error] ortho.model_path expected HuggingFace repo id "
                "like `razhan/whisper-base-sdh` or a local HF-format directory; got empty value"
            )
        self._reject_ct2_model_path_if_present()

        self.language = str(section_config.get("language", "")).strip() or None
        self.device = str(section_config.get("device", "cuda")).strip() or "cuda"
        task_raw = str(section_config.get("task", "transcribe") or "transcribe").strip().lower()
        self.task = task_raw if task_raw in {"transcribe", "translate"} else "transcribe"
        self.refine_lexemes: bool = provider_module._coerce_bool(
            section_config.get("refine_lexemes", False), default=False
        )
        self.ignored_legacy_options: Dict[str, Any] = {
            key: section_config.get(key)
            for key in (
                "compute_type",
                "vad_filter",
                "vad_parameters",
                "condition_on_previous_text",
                "compression_ratio_threshold",
                "initial_prompt",
            )
            if key in section_config
        }

        self._processor: Optional[Any] = None
        self._model: Optional[Any] = None
        self._effective_device = _normalize_pipeline_device(self.device)

    def _reject_ct2_model_path_if_present(self) -> None:
        candidate = Path(self.model_path).expanduser()
        try:
            exists = candidate.exists()
        except OSError:
            exists = False
        if not exists:
            return
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if _looks_like_ct2_whisper_directory(resolved):
            raise ValueError(_ct2_model_path_error(str(resolved)))

    def warm_up(self) -> None:
        """Eagerly load the HF Whisper processor/model pair."""
        self._load_model()

    def _load_model(self) -> Tuple[Any, Any]:
        if self._processor is not None and self._model is not None:
            return self._processor, self._model

        try:
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
        except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - exercised via tests
            raise ImportError(HF_TRANSFORMERS_IMPORT_ERROR) from exc

        processor = WhisperProcessor.from_pretrained(self.model_path)
        model = WhisperForConditionalGeneration.from_pretrained(self.model_path)
        to_device = getattr(model, "to", None)
        if callable(to_device):
            model = to_device(self._effective_device)
        eval_model = getattr(model, "eval", None)
        if callable(eval_model):
            model = eval_model()

        self._processor = processor
        self._model = model
        if self.ignored_legacy_options:
            print(
                "[ORTH] HFWhisperProvider ignoring legacy faster-whisper options: {0}".format(
                    ", ".join(sorted(self.ignored_legacy_options.keys()))
                ),
                file=sys.stderr,
                flush=True,
            )
        print(
            "[ORTH] HFWhisperProvider loaded: model={0} device={1} language={2}".format(
                self.model_path,
                self._effective_device,
                self._resolved_language() or "<auto-detect>",
            ),
            file=sys.stderr,
            flush=True,
        )
        return self._processor, self._model

    def _resolved_language(self, language: Optional[str] = None) -> Optional[str]:
        return _normalize_whisper_language((language or self.language) or None)

    def _generate_kwargs(self, language: Optional[str] = None) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"task": self.task}
        resolved_language = self._resolved_language(language)
        if resolved_language:
            kwargs["language"] = resolved_language
        return kwargs

    @staticmethod
    def _coerce_audio_array(audio_array: Any) -> Any:
        try:
            import numpy as _np
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("numpy is required for HF ORTH transcription") from exc

        if hasattr(audio_array, "numpy") and not isinstance(audio_array, _np.ndarray):
            try:
                audio_np = audio_array.detach().cpu().numpy()
            except AttributeError:
                audio_np = audio_array.numpy()
        else:
            audio_np = audio_array
        audio_np = _np.asarray(audio_np, dtype=_np.float32)
        if audio_np.ndim == 0:
            return _np.ascontiguousarray(_np.zeros(0, dtype=_np.float32))
        if audio_np.ndim > 1:
            if audio_np.shape[0] <= 8 and audio_np.shape[0] <= audio_np.shape[-1]:
                audio_np = audio_np.mean(axis=0)
            else:
                audio_np = audio_np.mean(axis=-1)
        return _np.ascontiguousarray(audio_np.reshape(-1), dtype=_np.float32)

    @classmethod
    def _audio_payload(cls, audio_input: Any, sample_rate: int = _HF_WHISPER_SAMPLE_RATE) -> Dict[str, Any]:
        if isinstance(audio_input, dict):
            raw_audio = audio_input.get("raw")
            sample_rate = int(audio_input.get("sampling_rate") or sample_rate or _HF_WHISPER_SAMPLE_RATE)
        else:
            raw_audio = audio_input
            sample_rate = int(sample_rate or _HF_WHISPER_SAMPLE_RATE)
        return {"raw": cls._coerce_audio_array(raw_audio), "sampling_rate": sample_rate}

    @staticmethod
    def _resample_audio(audio_np: Any, source_rate: int, target_rate: int = _HF_WHISPER_SAMPLE_RATE) -> Any:
        if int(source_rate) == int(target_rate):
            return audio_np
        try:
            import numpy as _np
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("numpy is required for HF ORTH audio resampling") from exc
        source_rate_i = int(source_rate)
        target_rate_i = int(target_rate)
        if source_rate_i <= 0 or target_rate_i <= 0:
            raise ValueError("sample_rate must be positive for HF ORTH audio resampling")
        total_samples = int(audio_np.shape[0]) if getattr(audio_np, "ndim", 0) else 0
        if total_samples <= 0:
            return audio_np
        target_samples = max(1, int(round(total_samples * target_rate_i / float(source_rate_i))))
        if total_samples == 1:
            return _np.ascontiguousarray(_np.full(target_samples, float(audio_np[0]), dtype=_np.float32))
        source_positions = _np.linspace(0.0, float(total_samples - 1), num=total_samples, dtype=_np.float64)
        target_positions = _np.linspace(0.0, float(total_samples - 1), num=target_samples, dtype=_np.float64)
        return _np.ascontiguousarray(_np.interp(target_positions, source_positions, audio_np).astype(_np.float32))

    @classmethod
    def _load_audio_mono_16k(cls, path: Path) -> Any:
        try:
            import soundfile as sf  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "HF ORTH audio loading requires the 'soundfile' package. Install with: pip install soundfile"
            ) from exc
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        audio_np = cls._coerce_audio_array(data)
        return cls._resample_audio(audio_np, int(sample_rate), _HF_WHISPER_SAMPLE_RATE)

    @staticmethod
    def _model_input_dict(inputs: Any) -> Dict[str, Any]:
        if isinstance(inputs, dict):
            return dict(inputs)
        items = getattr(inputs, "items", None)
        if callable(items):
            return dict(items())
        try:
            return dict(inputs)
        except (TypeError, ValueError) as exc:
            raise TypeError("HF Whisper processor output must be dict-like") from exc

    def _transcribe_audio_payload(
        self,
        audio_payload: Dict[str, Any],
        *,
        language: Optional[str] = None,
    ) -> Tuple[str, float]:
        processor, model = self._load_model()
        sample_rate = int(audio_payload.get("sampling_rate") or _HF_WHISPER_SAMPLE_RATE)
        raw_audio = audio_payload.get("raw")
        if sample_rate != _HF_WHISPER_SAMPLE_RATE:
            raw_audio = self._resample_audio(raw_audio, sample_rate, _HF_WHISPER_SAMPLE_RATE)
            sample_rate = _HF_WHISPER_SAMPLE_RATE
        inputs = processor(raw_audio, sampling_rate=sample_rate, return_tensors="pt")
        move_inputs = getattr(inputs, "to", None)
        if callable(move_inputs):
            inputs = move_inputs(self._effective_device)
        model_inputs = self._model_input_dict(inputs)
        generated = model.generate(
            **model_inputs,
            return_dict_in_generate=True,
            output_scores=True,
            **self._generate_kwargs(language),
        )
        decoded = processor.batch_decode(
            getattr(generated, "sequences", []),
            skip_special_tokens=True,
        )
        text = str(decoded[0] if decoded else "").strip()
        if not text:
            return "", 0.0
        avg_logprob = _avg_logprob_from_scores(
            getattr(generated, "scores", None),
            getattr(generated, "sequences", None),
        )
        confidence = provider_module._confidence_from_logprob(avg_logprob)
        return text, confidence

    def transcribe(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        segment_callback: Optional[Callable[["Segment"], None]] = None,
    ) -> List["Segment"]:
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(path))

        audio_np = self._load_audio_mono_16k(path)
        total_samples = int(audio_np.shape[0]) if getattr(audio_np, "ndim", 0) else 0
        if total_samples <= 0:
            if progress_callback is not None:
                progress_callback(100.0, 0)
            return []

        sample_rate = _HF_WHISPER_SAMPLE_RATE
        chunk_samples = max(1, int(round(_HF_WHISPER_CHUNK_SECONDS * sample_rate)))
        total_chunks = int(math.ceil(total_samples / float(chunk_samples)))
        segments: List[Segment] = []
        for chunk_index, start_sample in enumerate(range(0, total_samples, chunk_samples), start=1):
            end_sample = min(total_samples, start_sample + chunk_samples)
            window = audio_np[start_sample:end_sample]
            text, confidence = self._transcribe_audio_payload(
                self._audio_payload(window, sample_rate),
                language=language,
            )
            if text:
                segment: Segment = {
                    "start": float(start_sample) / float(sample_rate),
                    "end": float(end_sample) / float(sample_rate),
                    "text": text,
                    "confidence": confidence,
                }
                segments.append(segment)
                if segment_callback is not None:
                    segment_callback(dict(segment))
            if progress_callback is not None:
                progress_callback((chunk_index / total_chunks) * 100.0, len(segments))
        return segments

    def transcribe_window(
        self,
        audio_array: Any,
        sample_rate: int,
        *,
        language: Optional[str] = None,
    ) -> List["SegmentWithWords"]:
        audio_np = self._coerce_audio_array(audio_array)
        total_samples = int(audio_np.shape[0]) if getattr(audio_np, "ndim", 0) else 0
        if total_samples <= 0:
            return []
        duration = max(0.0, float(total_samples) / float(sample_rate or _HF_WHISPER_SAMPLE_RATE))
        try:
            text, confidence = self.transcribe_clip(
                {"raw": audio_np, "sampling_rate": int(sample_rate or _HF_WHISPER_SAMPLE_RATE)},
                language=language,
            )
        except Exception as exc:
            print(
                "[WARN] HF transcribe_window failed: {0}: {1}".format(type(exc).__name__, exc),
                file=sys.stderr,
            )
            return []
        if not text:
            return []
        return [{"start": 0.0, "end": duration, "text": text, "confidence": confidence}]

    def transcribe_segments_in_memory(
        self,
        audio_array: Any,
        intervals: List[Tuple[float, float]],
        *,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        sample_rate: int = 16000,
    ) -> List["SegmentWithWords"]:
        if audio_array is None or not intervals:
            return []

        audio_np = self._coerce_audio_array(audio_array)
        total_samples = int(audio_np.shape[0]) if getattr(audio_np, "ndim", 0) else 0
        if total_samples <= 0:
            return []

        segments_out: List[SegmentWithWords] = []
        total_intervals = len(intervals)
        sample_rate_i = int(sample_rate or _HF_WHISPER_SAMPLE_RATE)
        for index, (start_sec, end_sec) in enumerate(intervals, start=1):
            try:
                start_sec_f = float(start_sec)
                end_sec_f = float(end_sec)
            except (TypeError, ValueError):
                continue
            if end_sec_f <= start_sec_f:
                continue

            start_sample = max(0, int(round(start_sec_f * sample_rate_i)))
            end_sample = min(total_samples, int(round(end_sec_f * sample_rate_i)))
            if end_sample <= start_sample:
                continue

            window = audio_np[start_sample:end_sample]
            try:
                text, confidence = self._transcribe_audio_payload(
                    self._audio_payload(window, sample_rate_i),
                    language=language,
                )
            except Exception as exc:
                print(
                    "[WARN] HF transcribe_segments_in_memory: interval {0:.2f}-{1:.2f}s failed: {2}: {3}".format(
                        start_sec_f,
                        end_sec_f,
                        type(exc).__name__,
                        exc,
                    ),
                    file=sys.stderr,
                )
                continue
            if text:
                segments_out.append(
                    {
                        "start": start_sec_f,
                        "end": end_sec_f,
                        "text": text,
                        "confidence": confidence,
                    }
                )
            if progress_callback is not None:
                progress_callback((index / total_intervals) * 100.0, index)

        segments_out.sort(key=lambda seg: (float(seg.get("start", 0.0)), float(seg.get("end", 0.0))))
        return segments_out

    def transcribe_clip(
        self,
        audio_array: Any,
        *,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Tuple[str, float]:
        if audio_array is None:
            return ("", 0.0)
        _ = initial_prompt
        payload = self._audio_payload(audio_array)
        audio_np = payload["raw"]
        total_samples = int(audio_np.shape[0]) if getattr(audio_np, "ndim", 0) else 0
        if total_samples <= 0:
            return ("", 0.0)
        try:
            return self._transcribe_audio_payload(
                payload,
                language=language,
            )
        except Exception as exc:
            print(
                "[WARN] HF transcribe_clip failed: {0}: {1}".format(type(exc).__name__, exc),
                file=sys.stderr,
            )
            return ("", 0.0)


__all__ = ["HFWhisperProvider", "HF_TRANSFORMERS_IMPORT_ERROR"]
