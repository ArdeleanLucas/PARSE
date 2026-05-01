from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import ai.provider as provider_module

from .local_whisper import _normalize_whisper_language

if TYPE_CHECKING:
    from ai.provider import Segment, SegmentWithWords

HF_TRANSFORMERS_IMPORT_ERROR = (
    "transformers is required for the HF ortho backend; install with "
    "'pip install transformers' or set ortho.backend='faster-whisper' in ai_config.json"
)

_CT2_REQUIRED_FILES = frozenset({"model.bin", "config.json", "tokenizer.json"})


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

        self._pipeline: Optional[Any] = None
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
        """Eagerly load the HF ASR pipeline."""
        self._load_model()

    def _load_model(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        try:
            from transformers import pipeline
        except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - exercised via tests
            raise ImportError(HF_TRANSFORMERS_IMPORT_ERROR) from exc

        self._pipeline = pipeline(
            "automatic-speech-recognition",
            model=self.model_path,
            device=self._effective_device,
        )
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
        return self._pipeline

    def _resolved_language(self, language: Optional[str] = None) -> Optional[str]:
        return _normalize_whisper_language((language or self.language) or None)

    def _generate_kwargs(self, language: Optional[str] = None) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"task": self.task}
        resolved_language = self._resolved_language(language)
        if resolved_language:
            kwargs["language"] = resolved_language
        return kwargs

    def _run_pipeline(self, audio: Any, *, language: Optional[str] = None) -> Any:
        pipe = self._load_model()
        return pipe(audio, generate_kwargs=self._generate_kwargs(language))

    @staticmethod
    def _text_from_result(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("text") or "").strip()
        return str(getattr(result, "text", "") or "").strip()

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

        result = self._run_pipeline(str(path), language=language)
        text = self._text_from_result(result)
        duration = provider_module._audio_duration_seconds(path)
        segments: List[Segment] = []
        if text:
            segment: Segment = {
                "start": 0.0,
                "end": duration,
                "text": text,
                "confidence": 1.0,
            }
            segments.append(segment)
            if segment_callback is not None:
                segment_callback(dict(segment))
        if progress_callback is not None:
            progress_callback(100.0, len(segments))
        return segments

    def transcribe_window(
        self,
        audio_array: Any,
        sample_rate: int,
        *,
        language: Optional[str] = None,
    ) -> List["SegmentWithWords"]:
        duration = 0.0
        try:
            duration = max(0.0, float(len(audio_array)) / float(sample_rate or 16000))
        except (TypeError, ValueError, ZeroDivisionError):
            duration = 0.0
        text, confidence = self.transcribe_clip(audio_array, language=language)
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

        try:
            import numpy as _np
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("numpy is required for HF ORTH in-memory transcription") from exc

        if hasattr(audio_array, "numpy") and not isinstance(audio_array, _np.ndarray):
            try:
                audio_np = audio_array.detach().cpu().numpy()
            except AttributeError:
                audio_np = audio_array.numpy()
        else:
            audio_np = audio_array
        audio_np = _np.ascontiguousarray(audio_np, dtype=_np.float32)
        total_samples = int(audio_np.shape[0]) if audio_np.ndim else 0
        if total_samples <= 0:
            return []

        segments_out: List[SegmentWithWords] = []
        total_intervals = len(intervals)
        for index, (start_sec, end_sec) in enumerate(intervals, start=1):
            try:
                start_sec_f = float(start_sec)
                end_sec_f = float(end_sec)
            except (TypeError, ValueError):
                continue
            if end_sec_f <= start_sec_f:
                continue

            start_sample = max(0, int(round(start_sec_f * sample_rate)))
            end_sample = min(total_samples, int(round(end_sec_f * sample_rate)))
            if end_sample <= start_sample:
                continue

            window = audio_np[start_sample:end_sample]
            try:
                result = self._run_pipeline(window, language=language)
            except Exception as exc:
                print(
                    "[WARN] HF transcribe_segments_in_memory: interval {0:.2f}-{1:.2f}s failed: {2}".format(
                        start_sec_f,
                        end_sec_f,
                        exc,
                    ),
                    file=sys.stderr,
                )
                continue
            text = self._text_from_result(result)
            if text:
                segments_out.append(
                    {
                        "start": start_sec_f,
                        "end": end_sec_f,
                        "text": text,
                        "confidence": 1.0,
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
        # HF pipeline's high-level ASR API does not expose avg_logprob. Keep a
        # non-zero confidence placeholder until PARSE needs the lower-level
        # generate(return_dict_in_generate=True, output_scores=True) path.
        _ = initial_prompt
        try:
            result = self._run_pipeline(audio_array, language=language)
        except Exception as exc:
            print("[WARN] HF transcribe_clip failed: {0}".format(exc), file=sys.stderr)
            return ("", 0.0)
        text = self._text_from_result(result)
        return (text, 1.0 if text else 0.0)


__all__ = ["HFWhisperProvider", "HF_TRANSFORMERS_IMPORT_ERROR"]
