from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import ai.provider as provider_module

if TYPE_CHECKING:
    from ai.provider import Segment, SegmentWithWords


# Razhan SDH models (razhan/whisper-base-sdh, razhan/whisper-*-me) were fine-tuned
# by Razhan Hameed and Sina Ahmadi et al. on the DOLMA-NLP/asr pipeline with
# `--language="persian"`, so the decoder expects the `<|fa|>` language token at
# inference even though the speech is Southern Kurdish. PARSE annotations carry
# the linguistically-correct ISO 639-3 code `sdh`; this normalizer maps it (and
# the Whisper-supported `sd` Sindhi code, which earlier configs used as a stand-in)
# to `fa` so faster-whisper accepts the request. References:
#   - https://huggingface.co/razhan/whisper-base-sdh
#   - https://huggingface.co/razhan/whisper-small-me
#   - https://github.com/DOLMA-NLP/asr (finetune_whisper.py uses --language="persian")
_RAZHAN_SDH_LANGUAGE_ALIASES = frozenset({"sd", "sdh"})


def _normalize_whisper_language(code: Optional[str]) -> Optional[str]:
    if isinstance(code, str) and code.strip().lower() in _RAZHAN_SDH_LANGUAGE_ALIASES:
        return "fa"
    return code

class LocalWhisperProvider(provider_module.AIProvider):
    """Local provider backed by faster-whisper.

    Used by both STT (``config_section="stt"``) and ORTH
    (``config_section="ortho"``, razhan/whisper-base-sdh). The section
    selects which ai_config block supplies model_path/device/compute_type.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
        language: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        config_section: str = "stt",
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        self.config_section = str(config_section or "stt").strip() or "stt"
        section_config = self.config.get(self.config_section, {})
        self.model_path = str(section_config.get("model_path", "")).strip()

        # ORTH must not silently swap its model_path. Earlier revisions
        # fell back to ``stt.model_path`` when ``ortho.model_path`` was
        # empty or looked like a HuggingFace repo id (faster-whisper needs
        # CT2, not HF transformers format). In practice that meant the
        # ORTH pass ran with the STT model and nobody noticed — no error,
        # no banner, just wrong tier output. Hard-fail instead so the
        # misconfiguration lands as an error in the logs and a visible
        # job failure in the UI.
        if self.config_section == "ortho":
            if not self.model_path:
                raise ValueError(
                    "[ORTH config error] ortho.model_path is empty in ai_config.json. "
                    "ORTH will not fall back to stt.model_path — set an explicit CT2 "
                    "model path under 'ortho.model_path' (convert razhan/whisper-base-sdh "
                    "with `ct2-transformers-converter --model razhan/whisper-base-sdh "
                    "--output_dir /path/to/razhan-ct2` if that's the model you want)."
                )
            if provider_module._looks_like_hf_repo_id(self.model_path):
                raise ValueError(
                    "[ORTH config error] ortho.model_path '{0}' looks like a "
                    "HuggingFace repo id. faster-whisper requires CTranslate2 "
                    "format, not HF Transformers — convert first with "
                    "`ct2-transformers-converter --model {0} --output_dir "
                    "/path/to/<name>-ct2` and point ortho.model_path at the "
                    "CT2 output directory. ORTH will not fall back to "
                    "stt.model_path silently.".format(self.model_path)
                )
        self.language = str(language or section_config.get("language", "")).strip() or None
        self.device = str(device or section_config.get("device", "cpu")).strip() or "cpu"
        self.compute_type = (
            str(compute_type or section_config.get("compute_type", "int8")).strip() or "int8"
        )

        try:
            self.beam_size = max(1, int(section_config.get("beam_size", 5) or 5))
        except (TypeError, ValueError):
            self.beam_size = 5
        task_raw = str(section_config.get("task", "transcribe") or "transcribe").strip().lower()
        self.task = task_raw if task_raw in {"transcribe", "translate"} else "transcribe"
        # VAD + condition_on_previous_text defaults differ by section.
        # ``config_section="ortho"`` drives the ORTH pipeline step — the
        # key is historical, but every comment and print below refers to
        # ORTH to match the tier label in the UI and annotation JSON.
        #
        # * STT — default VAD **True**, condition_on_previous_text
        #   **True** (Whisper default). STT is a coarse sentence-level
        #   transcript; VAD gates long silences; cross-segment
        #   conditioning helps with coherent multi-sentence chunks.
        #
        # * ORTH — default VAD **True** with tuned params
        #   (``min_silence_duration_ms=500, threshold=0.35``) and
        #   condition_on_previous_text **False**. Flipped on
        #   2026-04-23 to fix the Fail02 regression where razhan on
        #   a 66-minute recording collapsed from 131 intervals to 38,
        #   ending in the classic whisper repetition loop
        #   ("ئە ئە ئە ئە ئە ..."). Without VAD, razhan can hallucinate
        #   on long silence; with VAD + default Silero threshold, the
        #   same recording used to collapse to 2 intervals. The tuned
        #   values in _DEFAULT_AI_CONFIG["ortho"] above split the
        #   difference. condition_on_previous_text=False is the
        #   critical piece — even one bad segment can no longer
        #   poison every segment after it.
        #
        # Users can override either knob via their ai_config.json
        # section.
        vad_default = True if self.config_section in {"ortho", "stt"} else False
        self.vad_filter = bool(section_config.get("vad_filter", vad_default))
        vad_params_raw = section_config.get("vad_parameters")
        # Only forward a dict when the user has set explicit parameters;
        # an empty {} falls through to faster-whisper's Silero defaults.
        self.vad_parameters: Optional[Dict[str, Any]] = (
            dict(vad_params_raw) if isinstance(vad_params_raw, dict) and vad_params_raw else None
        )

        # condition_on_previous_text: False disables Whisper's
        # cross-segment prompt chaining. Default is True for STT
        # (coherent sentences), False for ORTH (prevents the
        # repetition cascade on long fieldwork audio).
        cond_default = False if self.config_section == "ortho" else True
        self.condition_on_previous_text = bool(
            section_config.get("condition_on_previous_text", cond_default)
        )

        # compression_ratio_threshold: Whisper rejects segments whose
        # decoded text compresses above this ratio (usually a
        # repetition-loop hallucination). Defaults: 2.4 for STT
        # (Whisper's default), 1.8 for ORTH (stricter, catches
        # repetition earlier). Pass None to disable.
        ratio_default = 1.8 if self.config_section == "ortho" else 2.4
        ratio_raw = section_config.get("compression_ratio_threshold", ratio_default)
        try:
            self.compression_ratio_threshold: Optional[float] = (
                float(ratio_raw) if ratio_raw is not None else None
            )
        except (TypeError, ValueError):
            self.compression_ratio_threshold = ratio_default

        # initial_prompt: optional Whisper decoder priming string. Useful for
        # ORTH on elicited word-list recordings to bias decoding toward known
        # concepts and spellings. Empty string = not passed to faster-whisper.
        prompt_raw = section_config.get("initial_prompt", "")
        self.initial_prompt: str = (
            str(prompt_raw).strip() if isinstance(prompt_raw, str) else ""
        )

        # refine_lexemes: ORTH-only hook read by the compute runner. When True,
        # the ORTH job runs a short-clip Whisper fallback for concepts whose
        # forced-alignment match is weak or missing. Default False so existing
        # users aren't surprised by the extra ~1-2 min on thesis-scale audio.
        self.refine_lexemes: bool = provider_module._coerce_bool(
            section_config.get("refine_lexemes", False), default=False
        )

        if provider_module._stt_force_cpu_env() and self.device.lower().startswith("cuda"):
            print(
                "[WARN] PARSE_STT_FORCE_CPU set; overriding stt.device "
                "'{0}' → 'cpu' and compute_type → 'int8' before model load.".format(self.device),
                file=sys.stderr,
            )
            self.device = "cpu"
            self.compute_type = "int8"

        self._whisper_model: Optional[Any] = None
        self._model_source: Optional[str] = None
        self._effective_device: Optional[str] = None
        self._effective_compute_type: Optional[str] = None

    def warm_up(self) -> None:
        """Force the faster-whisper model to load now.

        Call once at persistent-worker startup so the first
        ``transcribe()`` call doesn't pay the ~1-5 s cold-load cost.
        Safe to call from non-worker contexts — just an eager version
        of the normal lazy load.
        """
        self._load_whisper_model()

    def _load_whisper_model(self) -> Any:
        """Lazy-load faster-whisper model.

        On Windows the CUDA backend needs cuBLAS / cuDNN DLLs visible to the
        process. Since Python 3.8, ``PATH`` is no longer searched for DLLs, so
        even a correct CUDA install can fail with
        ``Library cublas64_12.dll is not found or cannot be loaded``. We
        proactively register every plausible DLL directory before importing
        ``faster_whisper`` (it's the import that triggers the CTranslate2
        load), then fall back to CPU if the GPU model still won't initialize.
        """
        if self._whisper_model is not None:
            return self._whisper_model

        provider_module._register_cuda_dll_directories()

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            print(
                "[ERROR] faster-whisper is not installed. Install it to use LocalWhisperProvider.",
                file=sys.stderr,
            )
            raise RuntimeError("faster-whisper dependency missing") from exc

        model_source = self.model_path
        if not model_source:
            model_source = "base"
            print(
                "[WARN] stt.model_path is empty in ai_config.json; falling back to model 'base'",
                file=sys.stderr,
            )

        self._model_source = model_source
        wants_gpu = str(self.device or "").strip().lower() in {"cuda", "auto"} or \
            self.device.lower().startswith("cuda")

        try:
            self._whisper_model = WhisperModel(
                model_source,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._effective_device = self.device
            self._effective_compute_type = self.compute_type
            return self._whisper_model
        except Exception as exc:
            message = str(exc)
            cuda_failure = wants_gpu and provider_module._looks_like_cuda_runtime_failure(message)
            if not cuda_failure:
                print(
                    "[ERROR] Failed to load faster-whisper model '{0}': {1}".format(
                        model_source, exc
                    ),
                    file=sys.stderr,
                )
                raise

            print(
                "[WARN] CUDA backend unavailable for faster-whisper "
                "(device='{0}', compute_type='{1}'): {2}. "
                "Falling back to CPU (compute_type='int8'). To use GPU, install "
                "the matching cuDNN / cuBLAS runtime — typically "
                "`pip install nvidia-cudnn-cu12 nvidia-cublas-cu12` — and ensure "
                "their `bin` directories are reachable.".format(
                    self.device, self.compute_type, message
                ),
                file=sys.stderr,
            )

            try:
                self._whisper_model = WhisperModel(
                    model_source, device="cpu", compute_type="int8"
                )
                self._effective_device = "cpu"
                self._effective_compute_type = "int8"
            except Exception as cpu_exc:
                print(
                    "[ERROR] CPU fallback for faster-whisper also failed: {0}".format(cpu_exc),
                    file=sys.stderr,
                )
                raise RuntimeError(
                    "STT initialization failed on both GPU and CPU. "
                    "Original GPU error: {0}. CPU fallback error: {1}".format(message, cpu_exc)
                ) from cpu_exc

            return self._whisper_model

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        segment_callback: Optional[Callable[[Segment], None]] = None,
    ) -> List[Segment]:
        """Run full-file STT with faster-whisper."""
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(path))

        model = self._load_whisper_model()
        # Auto-detect when the user hasn't forced a language (empty/None).
        # faster-whisper treats language=None as auto-detect; language=""
        # would error.
        selected_language = _normalize_whisper_language((language or self.language) or None)

        def _run_transcription(m: Any) -> List[Segment]:
            segs_out: List[Segment] = []
            # Tier 1 acoustic alignment: word_timestamps=True enriches each
            # segment with per-word (start, end, probability) spans used by
            # Tier 2 forced alignment. The extra cost is a DTW pass on
            # cross-attention and is negligible relative to decoding.
            transcribe_kwargs: Dict[str, Any] = {
                "language": selected_language,
                "beam_size": self.beam_size,
                "task": self.task,
                "vad_filter": self.vad_filter,
                "word_timestamps": True,
                # Configurable per section; see __init__ for defaults.
                # ORTH defaults to False to break the repetition cascade.
                "condition_on_previous_text": self.condition_on_previous_text,
            }
            if self.vad_filter and self.vad_parameters is not None:
                transcribe_kwargs["vad_parameters"] = self.vad_parameters
            if self.compression_ratio_threshold is not None:
                transcribe_kwargs["compression_ratio_threshold"] = self.compression_ratio_threshold
            if self.initial_prompt:
                transcribe_kwargs["initial_prompt"] = self.initial_prompt
            segs_iter, info = m.transcribe(str(path), **transcribe_kwargs)
            total_duration = float(getattr(info, "duration", 0.0) or 0.0)
            for segment in segs_iter:
                start = float(provider_module._dict_or_attr(segment, "start", 0.0) or 0.0)
                end = float(provider_module._dict_or_attr(segment, "end", start) or start)
                text = str(provider_module._dict_or_attr(segment, "text", "") or "").strip()
                avg_logprob = provider_module._dict_or_attr(segment, "avg_logprob", None)
                words_out = provider_module._extract_word_spans(segment)
                seg_dict: SegmentWithWords = {
                    "start": start,
                    "end": end,
                    "text": text,
                    "confidence": provider_module._confidence_from_logprob(avg_logprob),
                }
                if words_out:
                    seg_dict["words"] = words_out
                segs_out.append(seg_dict)
                if segment_callback is not None:
                    segment_callback(copy.deepcopy(seg_dict))
                if progress_callback is not None and total_duration > 0.0:
                    progress = provider_module._coerce_confidence(end / total_duration) * 100.0
                    progress_callback(progress, len(segs_out))
            return segs_out

        try:
            segments_out = _run_transcription(model)
        except Exception as exc:
            on_cuda = (
                self._effective_device is not None
                and self._effective_device.lower().startswith("cuda")
            )
            cuda_failure = on_cuda or provider_module._looks_like_cuda_runtime_failure(str(exc))
            if not cuda_failure:
                raise

            print(
                "[WARN] CUDA inference failed mid-transcription: {0}. "
                "Rebuilding model on CPU/int8 and retrying. To use GPU, install "
                "the matching cuDNN / cuBLAS runtime — typically "
                "`pip install nvidia-cudnn-cu12 nvidia-cublas-cu12`.".format(exc),
                file=sys.stderr,
            )
            os.environ["CUDA_VISIBLE_DEVICES"] = ""

            from faster_whisper import WhisperModel as _WM
            cpu_source = self._model_source or self.model_path or "base"
            try:
                cpu_model = _WM(cpu_source, device="cpu", compute_type="int8")
            except Exception as cpu_exc:
                print(
                    "[ERROR] CPU fallback rebuild failed for model '{0}': {1}".format(
                        cpu_source, cpu_exc
                    ),
                    file=sys.stderr,
                )
                raise RuntimeError(
                    "STT mid-transcription CUDA failure and CPU fallback both failed. "
                    "Original GPU error: {0}. CPU fallback error: {1}".format(exc, cpu_exc)
                ) from cpu_exc

            self._whisper_model = cpu_model
            self._effective_device = "cpu"
            self._effective_compute_type = "int8"
            segments_out = _run_transcription(cpu_model)

        if progress_callback is not None:
            progress_callback(100.0, len(segments_out))

        return segments_out

    def transcribe_segments_in_memory(
        self,
        audio_array: Any,
        intervals: List[Tuple[float, float]],
        *,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        sample_rate: int = 16000,
    ) -> List[SegmentWithWords]:
        """Transcribe pre-sliced windows from a loaded mono waveform."""
        if audio_array is None or not intervals:
            return []

        try:
            import numpy as _np
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("numpy is required for boundary-constrained STT") from exc

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

        model = self._load_whisper_model()
        selected_language = _normalize_whisper_language((language or self.language) or None)
        kwargs: Dict[str, Any] = {
            "language": selected_language,
            "beam_size": self.beam_size,
            "task": self.task,
            "vad_filter": False,
            "word_timestamps": True,
            "condition_on_previous_text": False,
        }
        if self.compression_ratio_threshold is not None:
            kwargs["compression_ratio_threshold"] = self.compression_ratio_threshold
        if self.initial_prompt:
            kwargs["initial_prompt"] = self.initial_prompt

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
                segs_iter, _info = model.transcribe(window, **kwargs)
            except Exception as exc:
                print(
                    "[WARN] transcribe_segments_in_memory: interval {0:.2f}-{1:.2f}s failed: {2}".format(
                        start_sec_f,
                        end_sec_f,
                        exc,
                    ),
                    file=sys.stderr,
                )
                continue

            for segment in segs_iter:
                local_start = float(provider_module._dict_or_attr(segment, "start", 0.0) or 0.0)
                local_end = float(provider_module._dict_or_attr(segment, "end", local_start) or local_start)
                text = str(provider_module._dict_or_attr(segment, "text", "") or "").strip()
                avg_logprob = provider_module._dict_or_attr(segment, "avg_logprob", None)
                global_start = start_sec_f + local_start
                global_end = min(end_sec_f, start_sec_f + local_end)
                if global_end < global_start:
                    global_end = global_start
                seg_dict: SegmentWithWords = {
                    "start": global_start,
                    "end": global_end,
                    "text": text,
                    "confidence": provider_module._confidence_from_logprob(avg_logprob),
                }
                words_local = provider_module._extract_word_spans(segment)
                if words_local:
                    words_global = []
                    for word in words_local:
                        try:
                            word_start = float(word.get("start", 0.0) or 0.0)
                            word_end = float(word.get("end", word_start) or word_start)
                        except (TypeError, ValueError):
                            continue
                        words_global.append(
                            {
                                **word,
                                "start": start_sec_f + word_start,
                                "end": min(end_sec_f, start_sec_f + word_end),
                            }
                        )
                    if words_global:
                        seg_dict["words"] = words_global
                segments_out.append(seg_dict)

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
        """Transcribe a preloaded mono-16kHz numpy array.

        Returns ``(text: str, confidence: float)`` where ``text`` is the
        concatenation of all decoded segments (usually one for a short clip)
        and ``confidence`` is in ``[0, 1]`` derived from the best segment
        ``avg_logprob`` via the same formula used by :meth:`transcribe`.
        Empty or ``None`` input yields ``("", 0.0)``.

        Unlike :meth:`transcribe` this accepts an in-memory audio array
        rather than a file path, so the caller can reuse an already-loaded
        waveform (e.g. from ``ai.forced_align._load_audio_mono_16k``) and
        slice ±0.8 s windows without re-reading the file per concept.
        """
        if audio_array is None:
            return ("", 0.0)

        model = self._load_whisper_model()
        selected_language = _normalize_whisper_language((language or self.language) or None)
        prompt = initial_prompt if initial_prompt is not None else self.initial_prompt

        kwargs: Dict[str, Any] = {
            "language": selected_language,
            "beam_size": self.beam_size,
            "task": self.task,
            "vad_filter": False,
            "word_timestamps": False,
            "condition_on_previous_text": False,
        }
        if self.compression_ratio_threshold is not None:
            kwargs["compression_ratio_threshold"] = self.compression_ratio_threshold
        if prompt:
            kwargs["initial_prompt"] = prompt

        try:
            segs_iter, _info = model.transcribe(audio_array, **kwargs)
        except Exception as exc:
            print(
                "[WARN] transcribe_clip failed: {0}".format(exc),
                file=sys.stderr,
            )
            return ("", 0.0)

        parts: List[str] = []
        best_conf = 0.0
        for seg in segs_iter:
            text = str(provider_module._dict_or_attr(seg, "text", "") or "").strip()
            if text:
                parts.append(text)
                conf = provider_module._confidence_from_logprob(provider_module._dict_or_attr(seg, "avg_logprob", None))
                if conf and conf > best_conf:
                    best_conf = conf
        return (" ".join(parts).strip(), float(best_conf))

__all__ = ["LocalWhisperProvider"]
