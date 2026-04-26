#!/usr/bin/env python3
"""AI provider abstraction for PARSE.

This module preserves the public provider surface while delegating concrete
implementations into ``ai.providers`` modules.
"""

from __future__ import annotations

import abc
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

from .providers.shared import (
    _CHAT_CONTEXT_WINDOW_DEFAULT,
    _CHAT_MODEL_CONTEXT_WINDOWS,
    _CHAT_OPENAI_ONLY_MODELS,
    _CHAT_PROVIDER_BASE_URLS,
    _CHAT_PROVIDER_DEFAULT_MODELS,
    _CHAT_SUPPORTED_PROVIDERS,
    _DEFAULT_AI_CONFIG,
    _audio_duration_seconds,
    _build_chat_config,
    _coerce_bool,
    _coerce_confidence,
    _coerce_float,
    _coerce_int,
    _collect_nvidia_wheel_bin_dirs,
    _confidence_from_logprob,
    _deep_merge_dicts,
    _dict_or_attr,
    _extract_total_tokens,
    _extract_word_spans,
    _looks_like_cuda_runtime_failure,
    _looks_like_hf_repo_id,
    _normalize_openai_model_name,
    _stt_force_cpu_env,
    load_ai_config,
    resolve_ai_config_path,
    resolve_context_window,
)


class WordSpan(TypedDict, total=False):
    """Per-word timing from faster-whisper word_timestamps=True."""

    word: str
    start: float
    end: float
    prob: float


class Segment(TypedDict):
    """Timestamped STT segment. Always has start/end/text/confidence."""

    start: float
    end: float
    text: str
    confidence: float


class SegmentWithWords(Segment, total=False):
    """Segment enriched with per-word spans (Tier 1 acoustic alignment)."""

    words: List[WordSpan]


def get_chat_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return resolved chat config with provider constraints applied.

    Defined here rather than directly re-exported so monkeypatching
    ``ai.provider.load_ai_config`` in tests still affects the result.
    """
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    return _build_chat_config(merged)


# Cache so repeated _register_cuda_dll_directories calls don't re-walk the filesystem.
_CUDA_DLL_DIRS_REGISTERED: Optional[bool] = None


def _register_cuda_dll_directories() -> None:
    """Register cuBLAS / cuDNN DLL directories on Windows."""
    global _CUDA_DLL_DIRS_REGISTERED
    if _CUDA_DLL_DIRS_REGISTERED is not None:
        return
    _CUDA_DLL_DIRS_REGISTERED = False

    if sys.platform != "win32":
        return

    import os

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return

    candidates: List[Path] = []
    candidates.extend(_collect_nvidia_wheel_bin_dirs())

    for env_key in ("CUDA_PATH", "CUDA_HOME", "CUDNN_PATH"):
        value = os.environ.get(env_key)
        if not value:
            continue
        candidates.append(Path(value) / "bin")
        candidates.append(Path(value))

    extra = os.environ.get("PARSE_CUDA_DLL_DIRS", "")
    for chunk in extra.split(os.pathsep):
        chunk = chunk.strip()
        if chunk:
            candidates.append(Path(chunk))

    seen: set[Path] = set()
    registered_dirs: List[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        try:
            add_dll_directory(str(resolved))
            _CUDA_DLL_DIRS_REGISTERED = True
            registered_dirs.append(resolved)
        except (OSError, FileNotFoundError):
            pass

    if registered_dirs:
        print(
            "[INFO] CUDA DLL search registered {0} dir(s): {1}".format(
                len(registered_dirs),
                ", ".join(str(d) for d in registered_dirs),
            ),
            file=sys.stderr,
        )
    else:
        print(
            "[WARN] No CUDA DLL directories could be registered. If you expect GPU inference, install the NVIDIA runtime wheels: "
            "`pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12`.",
            file=sys.stderr,
        )


class AIProvider(abc.ABC):
    """Abstract AI provider interface used throughout PARSE."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.config_path = resolve_ai_config_path(config_path)
        file_config = load_ai_config(self.config_path)
        self.config = _deep_merge_dicts(file_config, config or {})

    @abc.abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        segment_callback: Optional[Callable[[Segment], None]] = None,
    ) -> List[Segment]:
        """Transcribe an audio file into timestamped segments."""
        raise NotImplementedError


from .providers.local_whisper import LocalWhisperProvider
from .providers.openai import OpenAIChatRuntime, OpenAIProvider
from .providers.ollama import OllamaProvider
from .providers.xai import XAIProvider


def _build_provider(provider_name: str, merged_config: Dict[str, Any]) -> AIProvider:
    """Instantiate a provider implementation from a provider name."""
    normalized = str(provider_name or "").strip().lower()

    if normalized in {"faster-whisper", "local-whisper", "whisper", "local"}:
        return LocalWhisperProvider(config=merged_config)
    if normalized == "openai":
        return OpenAIProvider(config=merged_config)
    if normalized in {"xai", "grok", "x.ai"}:
        return XAIProvider(config=merged_config)
    if normalized == "ollama":
        return OllamaProvider(config=merged_config)

    raise ValueError("Unsupported AI provider: {0}".format(normalized))


def _resolve_provider_name(
    merged_config: Dict[str, Any],
    section_priority: List[str],
    default: str = "faster-whisper",
    override_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolve provider name from config sections using priority order."""
    disabled_sections = set()

    if isinstance(override_config, dict):
        for section_name in section_priority:
            section = override_config.get(section_name, {})
            if not isinstance(section, dict) or "provider" not in section:
                continue

            provider_name = str(section.get("provider", "")).strip().lower()
            if provider_name:
                return provider_name

            disabled_sections.add(section_name)

    for section_name in section_priority:
        if section_name in disabled_sections:
            continue

        section = merged_config.get(section_name, {})
        if not isinstance(section, dict):
            continue

        provider_name = str(section.get("provider", "")).strip().lower()
        if provider_name:
            return provider_name

    return default


_PRELOADED_STT_PROVIDER: Optional[AIProvider] = None
_PRELOADED_ORTHO_PROVIDER: Optional[AIProvider] = None


def preload_stt_provider(config: Optional[Dict[str, Any]] = None) -> Optional[AIProvider]:
    """Build the STT provider, warm its Whisper model, and cache it."""
    global _PRELOADED_STT_PROVIDER
    try:
        provider = _build_stt_provider(config)
        if isinstance(provider, LocalWhisperProvider):
            provider.warm_up()
        _PRELOADED_STT_PROVIDER = provider
        return provider
    except Exception as exc:
        print("[provider] STT preload failed: {0}".format(exc), file=sys.stderr, flush=True)
        return None


def preload_ortho_provider(config: Optional[Dict[str, Any]] = None) -> Optional[AIProvider]:
    """Build the ORTH provider, warm its Whisper model, and cache it."""
    global _PRELOADED_ORTHO_PROVIDER
    try:
        provider = _build_ortho_provider(config)
        provider.warm_up()
        _PRELOADED_ORTHO_PROVIDER = provider
        return provider
    except Exception as exc:
        print("[provider] ORTH preload failed: {0}".format(exc), file=sys.stderr, flush=True)
        return None


def _build_stt_provider(config: Optional[Dict[str, Any]]) -> AIProvider:
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(merged, ["stt"], override_config=override)
    return _build_provider(provider_name, merged)


def _build_ortho_provider(config: Optional[Dict[str, Any]]) -> LocalWhisperProvider:
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    return LocalWhisperProvider(config=merged, config_section="ortho")


def get_stt_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    if _PRELOADED_STT_PROVIDER is not None and config is None:
        return _PRELOADED_STT_PROVIDER
    return _build_stt_provider(config)


def get_ortho_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    if _PRELOADED_ORTHO_PROVIDER is not None and config is None:
        return _PRELOADED_ORTHO_PROVIDER
    return _build_ortho_provider(config)


def get_llm_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(merged, ["llm", "stt"], override_config=override)
    return _build_provider(provider_name, merged)


def get_provider(config: Dict[str, Any]) -> AIProvider:
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)

    provider_name = str(override.get("provider", "")).strip().lower()
    if not provider_name:
        provider_name = _resolve_provider_name(merged, ["stt"])

    return _build_provider(provider_name, merged)


__all__ = [
    "WordSpan",
    "Segment",
    "SegmentWithWords",
    "AIProvider",
    "LocalWhisperProvider",
    "OpenAIProvider",
    "XAIProvider",
    "OllamaProvider",
    "OpenAIChatRuntime",
    "get_stt_provider",
    "get_ortho_provider",
    "get_llm_provider",
    "get_chat_config",
    "get_provider",
    "load_ai_config",
    "resolve_ai_config_path",
    "resolve_context_window",
    "preload_stt_provider",
    "preload_ortho_provider",
]
