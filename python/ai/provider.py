#!/usr/bin/env python3
"""AI provider abstraction for PARSE.

This module defines a shared provider interface plus concrete providers for:
- local faster-whisper (STT + local IPA fallback)
- OpenAI API
- Ollama local LLM
"""

import abc
import copy
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict


class Segment(TypedDict):
    """Timestamped STT segment."""

    start: float
    end: float
    text: str
    confidence: float


_DEFAULT_AI_CONFIG: Dict[str, Any] = {
    "stt": {
        "provider": "faster-whisper",
        "model_path": "",
        # Empty string = let Whisper auto-detect the language. We used to
        # default to "sd" (Sindhi), but the project's Southern Kurdish audio
        # isn't in Whisper's supported language list and forcing Sindhi made
        # the decoder hallucinate (produced 'ايقIt is not legal'-style
        # garbage). Auto-detect lands on Persian (fa) — a close relative —
        # and produces coherent Kurdish-script output.
        "language": "",
        "device": "cuda",
        "compute_type": "float16",
        "beam_size": 5,
        # "transcribe" preserves the detected language. Set to "translate"
        # if you want an English gloss of the speech.
        "task": "transcribe",
        # VAD gates silence out of the audio before decoding. Keep it on —
        # vad_filter=False produces hallucination loops in long silences
        # (e.g. repeating 'شوال' 5x during a 10s pause). Parameters below
        # are tunable; leave as {} to use faster-whisper's Silero defaults.
        "vad_filter": True,
        "vad_parameters": {},
    },
    "ipa": {
        "provider": "local",
        "model": "epitran",
    },
    "ortho": {
        "provider": "faster-whisper",
        "model_path": "razhan/whisper-base-sdh",
        "language": "sd",
        "device": "cuda",
        "compute_type": "float16",
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-5.4",
        "api_key_env": "OPENAI_API_KEY",
    },
    "chat": {
        "enabled": True,
        "read_only": False,
        "attachments_supported": False,
        "provider": "openai",
        "model": "gpt-5.4",
        "api_key_env": "OPENAI_API_KEY",
        "reasoning_effort": "high",
        "temperature": 0.1,
        "max_tool_rounds": 4,
        "max_history_messages": 24,
        "max_output_tokens": 1400,
        "max_tool_result_chars": 24000,
        "max_user_message_chars": 8000,
        "max_session_messages": 200,
    },
    "specialized_layers": [],
}

_CHAT_PROVIDER_BASE_URLS: Dict[str, str] = {
    "xai": "https://api.x.ai/v1",
    "grok": "https://api.x.ai/v1",
    "x.ai": "https://api.x.ai/v1",
}

_CHAT_PROVIDER_DEFAULT_MODELS: Dict[str, str] = {
    "xai": "grok-4.20-0309-reasoning",
    "grok": "grok-4.20-0309-reasoning",
    "x.ai": "grok-4.20-0309-reasoning",
    "openai": "gpt-5.4",
}

_LEGACY_OPENAI_MODEL_NAMES = {
    "gpt54": "gpt-5.4",
}

_CHAT_OPENAI_ONLY_MODELS = {
    "gpt54",
    "gpt-4o",
    "gpt-5.4",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
}

_CHAT_SUPPORTED_PROVIDERS = {"openai", "xai", "grok", "x.ai"}

# Approximate context windows in tokens. Values are conservative — the usable
# window is smaller than the absolute model ceiling because we reserve room
# for tool results, system instructions, and the assistant reply.
_CHAT_MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "gpt-5.4": 128000,
    "gpt-4o": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16384,
    "o1": 200000,
    "o1-mini": 128000,
    "o1-preview": 128000,
    "o3": 200000,
    "o3-mini": 200000,
    "grok-4.20-0309-reasoning": 131072,
}
_CHAT_CONTEXT_WINDOW_DEFAULT = 32000


def resolve_context_window(model_name: Any) -> int:
    """Return the approximate context window (in tokens) for a chat model."""
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return _CHAT_CONTEXT_WINDOW_DEFAULT
    if normalized in _CHAT_MODEL_CONTEXT_WINDOWS:
        return _CHAT_MODEL_CONTEXT_WINDOWS[normalized]
    for prefix, window in _CHAT_MODEL_CONTEXT_WINDOWS.items():
        if normalized.startswith(prefix):
            return window
    return _CHAT_CONTEXT_WINDOW_DEFAULT


def _extract_total_tokens(response: Any) -> Optional[int]:
    """Pull usage.total_tokens from an SDK response, tolerating object or dict shapes."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if total is None and isinstance(usage, dict):
        total = usage.get("total_tokens")
    if total is None:
        return None
    try:
        total_int = int(total)
    except (TypeError, ValueError):
        return None
    return total_int if total_int >= 0 else None


def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dictionaries without mutating inputs."""
    merged: Dict[str, Any] = copy.deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)

    return merged


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce loose boolean-like values with a safe default."""
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled"}:
            return False

    return bool(default)


def _normalize_openai_model_name(model_name: Any, default: str = "gpt-5.4") -> str:
    """Rewrite legacy OpenAI placeholder model names to the canonical default."""
    normalized = str(model_name or "").strip()
    if not normalized:
        return default
    return _LEGACY_OPENAI_MODEL_NAMES.get(normalized, normalized)


def _chat_supports_reasoning_effort(provider_name: Any, model_name: Any) -> bool:
    """Return True when the resolved chat provider/model should receive reasoning hints."""
    provider = str(provider_name or "").strip().lower()
    model = str(model_name or "").strip().lower()
    if provider in _CHAT_PROVIDER_BASE_URLS:
        return False
    if model.startswith("grok"):
        return False
    return True


def _coerce_int(
    value: Any,
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Coerce integer values with optional clamping."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)

    if minimum is not None and number < minimum:
        number = minimum

    if maximum is not None and number > maximum:
        number = maximum

    return number


def _coerce_float(
    value: Any,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Coerce float values with optional clamping."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)

    if minimum is not None and number < minimum:
        number = minimum

    if maximum is not None and number > maximum:
        number = maximum

    return number


def resolve_ai_config_path(config_path: Optional[Path] = None) -> Path:
    """Resolve ai_config.json path, defaulting to parse/config/ai_config.json."""
    if config_path is not None:
        return Path(config_path).expanduser().resolve()

    return Path(__file__).resolve().parents[2] / "config" / "ai_config.json"


def load_ai_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load AI config with schema defaults applied."""
    resolved_path = resolve_ai_config_path(config_path)
    defaults = copy.deepcopy(_DEFAULT_AI_CONFIG)

    if not resolved_path.exists():
        print(
            "[WARN] AI config not found at {0}; using defaults".format(resolved_path),
            file=sys.stderr,
        )
        return defaults

    try:
        raw_data = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            "[WARN] Failed to read AI config {0}: {1}; using defaults".format(
                resolved_path, exc
            ),
            file=sys.stderr,
        )
        return defaults

    if not isinstance(raw_data, dict):
        print(
            "[WARN] Invalid AI config root (expected object); using defaults",
            file=sys.stderr,
        )
        return defaults

    return _deep_merge_dicts(defaults, raw_data)


def _build_chat_config(merged_config: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve chat config from merged defaults/user config.

    Chat is OpenAI-compatible (OpenAI or xAI). ``read_only`` is honored from
    config (env ``PARSE_CHAT_READ_ONLY`` also overrides it at orchestrator
    construction). Attachments remain unsupported.
    """
    llm_config = merged_config.get("llm", {})
    if not isinstance(llm_config, dict):
        llm_config = {}

    chat_config = merged_config.get("chat", {})
    if not isinstance(chat_config, dict):
        chat_config = {}

    defaults = {
        "enabled": True,
        "read_only": False,
        "attachments_supported": False,
        "provider": "openai",
        "model": str(chat_config.get("model") or llm_config.get("model") or "gpt-5.4").strip() or "gpt-5.4",
        "api_key_env": str(chat_config.get("api_key_env") or llm_config.get("api_key_env") or "OPENAI_API_KEY").strip()
        or "OPENAI_API_KEY",
        "reasoning_effort": str(chat_config.get("reasoning_effort") or "high").strip() or "high",
        "temperature": chat_config.get("temperature", 0.1),
        "max_tool_rounds": chat_config.get("max_tool_rounds", 4),
        "max_history_messages": chat_config.get("max_history_messages", 24),
        "max_output_tokens": chat_config.get("max_output_tokens", 1400),
        "max_tool_result_chars": chat_config.get("max_tool_result_chars", 24000),
        "max_user_message_chars": chat_config.get("max_user_message_chars", 8000),
        "max_session_messages": chat_config.get("max_session_messages", 200),
    }

    resolved = _deep_merge_dicts(defaults, chat_config)

    stored_provider = ""
    try:
        from .openai_auth import get_api_key as _get_direct_key, get_api_key_provider as _get_provider

        if (_get_direct_key() or "").strip():
            stored_provider = str(_get_provider() or "").strip().lower()
    except Exception:
        stored_provider = ""

    provider_name = str(resolved.get("provider") or "openai").strip().lower()
    if stored_provider in _CHAT_SUPPORTED_PROVIDERS:
        provider_name = stored_provider
    if provider_name not in _CHAT_SUPPORTED_PROVIDERS:
        print(
            "[WARN] chat.provider={0!r} is unsupported; forcing 'openai'".format(provider_name),
            file=sys.stderr,
        )
        provider_name = "openai"
    resolved["provider"] = provider_name

    model_name = _normalize_openai_model_name(resolved.get("model"), default="")
    if provider_name in _CHAT_PROVIDER_BASE_URLS and model_name in _CHAT_OPENAI_ONLY_MODELS:
        model_name = _CHAT_PROVIDER_DEFAULT_MODELS[provider_name]
    resolved["model"] = model_name or _CHAT_PROVIDER_DEFAULT_MODELS.get(provider_name, "gpt-5.4")

    api_key_env = str(resolved.get("api_key_env") or "").strip()
    if provider_name in _CHAT_PROVIDER_BASE_URLS and (not api_key_env or api_key_env == "OPENAI_API_KEY"):
        api_key_env = "XAI_API_KEY"
    resolved["api_key_env"] = api_key_env or "OPENAI_API_KEY"

    base_url = str(resolved.get("base_url") or "").strip()
    if not base_url and provider_name in _CHAT_PROVIDER_BASE_URLS:
        base_url = _CHAT_PROVIDER_BASE_URLS[provider_name]
    resolved["base_url"] = base_url

    reasoning_effort = str(resolved.get("reasoning_effort") or "").strip().lower()
    if _chat_supports_reasoning_effort(provider_name, resolved.get("model")):
        if reasoning_effort not in {"minimal", "low", "medium", "high"}:
            reasoning_effort = "high"
    else:
        reasoning_effort = ""
    resolved["reasoning_effort"] = reasoning_effort

    resolved["enabled"] = _coerce_bool(resolved.get("enabled"), True)
    resolved["temperature"] = _coerce_float(resolved.get("temperature"), 0.1, minimum=0.0, maximum=2.0)
    resolved["max_tool_rounds"] = _coerce_int(resolved.get("max_tool_rounds"), 4, minimum=1, maximum=8)
    resolved["max_history_messages"] = _coerce_int(resolved.get("max_history_messages"), 24, minimum=1, maximum=64)
    resolved["max_output_tokens"] = _coerce_int(resolved.get("max_output_tokens"), 1400, minimum=128, maximum=8192)
    resolved["max_tool_result_chars"] = _coerce_int(
        resolved.get("max_tool_result_chars"),
        24000,
        minimum=2000,
        maximum=200000,
    )
    resolved["max_user_message_chars"] = _coerce_int(
        resolved.get("max_user_message_chars"),
        8000,
        minimum=500,
        maximum=50000,
    )
    resolved["max_session_messages"] = _coerce_int(
        resolved.get("max_session_messages"),
        200,
        minimum=10,
        maximum=1000,
    )

    resolved["read_only"] = _coerce_bool(resolved.get("read_only"), False)

    attachments_supported = _coerce_bool(resolved.get("attachments_supported"), False)
    if attachments_supported:
        print(
            "[WARN] chat.attachments_supported=true is unsupported in MVP; forcing false",
            file=sys.stderr,
        )
    resolved["attachments_supported"] = False

    return resolved


def get_chat_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return resolved chat config with OpenAI-only constraints applied."""
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    return _build_chat_config(merged)


class OpenAIChatRuntime:
    """Thin OpenAI chat runtime wrapper with tool-call support and reasoning fallback."""

    # Provider-specific base URLs for the OpenAI-compatible API
    _PROVIDER_BASE_URLS: Dict[str, str] = dict(_CHAT_PROVIDER_BASE_URLS)

    # Default models per provider (used when config still has a placeholder/OpenAI model)
    _PROVIDER_DEFAULT_MODELS: Dict[str, str] = dict(_CHAT_PROVIDER_DEFAULT_MODELS)

    # Model names that are clearly OpenAI-only and should be swapped for xAI
    _OPENAI_ONLY_MODELS = set(_CHAT_OPENAI_ONLY_MODELS)

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.config_path = resolve_ai_config_path(config_path)
        file_config = load_ai_config(self.config_path)
        merged_config = _deep_merge_dicts(file_config, config or {})

        self.chat_config = _build_chat_config(merged_config)
        self.model = str(self.chat_config.get("model") or "gpt-5.4").strip() or "gpt-5.4"
        self.api_key_env = str(self.chat_config.get("api_key_env") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY"
        self.reasoning_effort = str(self.chat_config.get("reasoning_effort") or "").strip().lower()

        try:
            self.temperature = float(self.chat_config.get("temperature", 0.1))
        except (TypeError, ValueError):
            self.temperature = 0.1

        try:
            self.max_output_tokens = int(self.chat_config.get("max_output_tokens", 1400) or 1400)
        except (TypeError, ValueError):
            self.max_output_tokens = 1400

        self.base_url = str(self.chat_config.get("base_url") or "").strip()
        self._client: Optional[Any] = None

    def _load_client(self) -> Any:
        if self._client is not None:
            return self._client

        from .openai_auth import (
            get_access_token as _get_access_token,
            get_api_key as _get_direct_key,
            get_api_key_provider as _get_provider,
        )

        _direct_key = (_get_direct_key() or "").strip()
        _provider = _get_provider().strip().lower() if _direct_key else ""

        api_key = _direct_key
        if not api_key:
            api_key = os.environ.get(self.api_key_env, "").strip()

        if not api_key:
            try:
                oauth_token = str(_get_access_token() or "").strip()
            except Exception:
                oauth_token = ""
            if oauth_token:
                api_key = oauth_token
                _provider = _provider or "openai"

        if not api_key:
            label, env_hint = self._credential_labels(_provider)
            raise RuntimeError(
                "{0} credentials are missing. Set {1} env var or sign in via the PARSE UI".format(
                    label, env_hint,
                )
            )

        if _provider in self._PROVIDER_DEFAULT_MODELS and self.model in self._OPENAI_ONLY_MODELS:
            self.model = self._PROVIDER_DEFAULT_MODELS[_provider]

        _base_url = (
            self.base_url
            or self.chat_config.get("base_url")
            or self._PROVIDER_BASE_URLS.get(_provider)
            or ""
        )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai dependency missing — run: pip install openai") from exc

        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if _base_url:
            client_kwargs["base_url"] = _base_url

        self._client = OpenAI(**client_kwargs)
        return self._client

    @classmethod
    def _credential_labels(cls, provider: str) -> tuple:
        """Return (display_label, env_var_hint) for a provider."""
        if provider in cls._PROVIDER_BASE_URLS:
            return ("xAI", "XAI_API_KEY")
        return ("OpenAI", "OPENAI_API_KEY")

    def _call_with_token_fallback(self, client: Any, payload: Dict[str, Any]) -> Tuple[Any, str]:
        """Call chat.completions.create while handling token-parameter differences."""
        candidate = copy.deepcopy(payload)
        try:
            response = client.chat.completions.create(**candidate)
            token_key = "max_completion_tokens" if "max_completion_tokens" in candidate else "none"
            return response, token_key
        except TypeError:
            if "max_completion_tokens" in candidate:
                max_tokens = candidate.pop("max_completion_tokens")
                candidate["max_tokens"] = max_tokens
                response = client.chat.completions.create(**candidate)
                return response, "max_tokens"
            raise

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        max_output_tokens: Optional[int] = None,
    ) -> Tuple[Any, Dict[str, Any]]:
        """Run a chat completion with optional tools.

        Tries to pass reasoning hints when supported by SDK/model. Falls back cleanly
        if the active client or model signature does not accept those fields.
        """
        client = self._load_client()

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }

        max_tokens = max_output_tokens if max_output_tokens is not None else self.max_output_tokens
        if isinstance(max_tokens, int) and max_tokens > 0:
            payload["max_completion_tokens"] = int(max_tokens)

        if tools is not None:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        reasoning_attempts: List[Tuple[str, Dict[str, Any]]] = []
        if self.reasoning_effort:
            reasoning_attempts.append(
                (
                    "reasoning",
                    {
                        "reasoning": {
                            "effort": self.reasoning_effort,
                        }
                    },
                )
            )
            reasoning_attempts.append(
                (
                    "reasoning_effort",
                    {
                        "reasoning_effort": self.reasoning_effort,
                    },
                )
            )

        reasoning_attempts.append(("none", {}))

        errors: List[str] = []
        for label, reasoning_payload in reasoning_attempts:
            candidate = copy.deepcopy(payload)
            candidate.update(reasoning_payload)

            try:
                response, token_key = self._call_with_token_fallback(client, candidate)
                return (
                    response,
                    {
                        "model": self.model,
                        "reasoningConfigured": self.reasoning_effort,
                        "reasoningAttempt": label,
                        "reasoningApplied": label != "none",
                        "tokenParameter": token_key,
                        "totalTokens": _extract_total_tokens(response),
                    },
                )
            except TypeError as exc:
                errors.append("{0}: {1}".format(label, exc))
                continue

        fallback_payload = {
            "model": self.model,
            "messages": messages,
        }
        if tools is not None:
            fallback_payload["tools"] = tools
            if tool_choice:
                fallback_payload["tool_choice"] = tool_choice

        response = client.chat.completions.create(**fallback_payload)
        return (
            response,
            {
                "model": self.model,
                "reasoningConfigured": self.reasoning_effort,
                "reasoningAttempt": "fallback_without_reasoning",
                "reasoningApplied": False,
                "warnings": errors,
                "tokenParameter": "none",
                "totalTokens": _extract_total_tokens(response),
            },
        )


def _coerce_confidence(value: float) -> float:
    """Clamp confidence score to [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _confidence_from_logprob(avg_logprob: Any) -> float:
    """Convert avg_logprob to a bounded confidence score."""
    if avg_logprob is None:
        return 0.0

    try:
        numeric = float(avg_logprob)
    except (TypeError, ValueError):
        return 0.0

    if numeric <= 0.0:
        return _coerce_confidence(math.exp(numeric))

    return _coerce_confidence(numeric)


def _strip_ipa_wrappers(text: str) -> str:
    """Remove common IPA wrappers (/.../, [...], leading labels)."""
    value = str(text).strip()
    value = re.sub(r"^\s*ipa\s*:\s*", "", value, flags=re.IGNORECASE)

    if value.startswith("/") and value.endswith("/") and len(value) > 1:
        value = value[1:-1].strip()
    if value.startswith("[") and value.endswith("]") and len(value) > 1:
        value = value[1:-1].strip()

    return value


def _dict_or_attr(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from dict-like or object-like values."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


# Cache so repeated _load_whisper_model calls don't re-walk the filesystem.
_CUDA_DLL_DIRS_REGISTERED: Optional[bool] = None
_CUDA_RUNTIME_FAILURE_MARKERS = (
    "cublas",
    "cudnn",
    "cuda",
    "is not found or cannot be loaded",
    "could not load library",
    "no cuda-capable device",
    "no cuda gpus are available",
    "cuda driver version is insufficient",
    "cublasstatus",
)


def _looks_like_cuda_runtime_failure(message: str) -> bool:
    """Heuristic — the GPU init failed because of a missing/broken CUDA runtime."""
    text = (message or "").lower()
    return any(marker in text for marker in _CUDA_RUNTIME_FAILURE_MARKERS)


def _stt_force_cpu_env() -> bool:
    """Respect PARSE_STT_FORCE_CPU as an emergency escape hatch."""
    value = os.environ.get("PARSE_STT_FORCE_CPU", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _register_cuda_dll_directories() -> None:
    """Register cuBLAS / cuDNN DLL directories on Windows.

    Since Python 3.8 the loader no longer searches ``PATH`` for dependent
    DLLs, so a Windows install with cuBLAS reachable via PATH still produces
    ``Library cublas64_12.dll is not found or cannot be loaded`` when
    CTranslate2 tries to ``LoadLibraryEx``. We add every plausible directory
    via ``os.add_dll_directory`` so the import succeeds.

    Safe no-op on non-Windows platforms.
    """
    global _CUDA_DLL_DIRS_REGISTERED
    if _CUDA_DLL_DIRS_REGISTERED is not None:
        return
    _CUDA_DLL_DIRS_REGISTERED = False

    if os.name != "nt":
        return

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return

    candidates: List[Path] = []

    # 1. NVIDIA pip wheels (nvidia-cublas-cu12, nvidia-cudnn-cu12) install
    #    DLLs under <site-packages>/nvidia/<lib>/bin. Walk every nvidia
    #    subpackage that has a `bin` dir.
    try:
        import nvidia  # type: ignore[import-not-found]

        nvidia_root = Path(nvidia.__file__).resolve().parent
        for entry in nvidia_root.iterdir():
            bin_dir = entry / "bin"
            if bin_dir.is_dir():
                candidates.append(bin_dir)
    except Exception:
        pass

    # 2. Explicit env vars that ship with CUDA Toolkit installs.
    for env_key in ("CUDA_PATH", "CUDA_HOME", "CUDNN_PATH"):
        value = os.environ.get(env_key)
        if not value:
            continue
        candidates.append(Path(value) / "bin")
        candidates.append(Path(value))

    # 3. Anything the user explicitly added.
    extra = os.environ.get("PARSE_CUDA_DLL_DIRS", "")
    for chunk in extra.split(os.pathsep):
        chunk = chunk.strip()
        if chunk:
            candidates.append(Path(chunk))

    seen: set = set()
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
        except (OSError, FileNotFoundError):
            # Directory exists but cannot be registered (e.g. permissions).
            # Skip silently — the WhisperModel try/except below will surface
            # any remaining DLL load failures with full context.
            pass


_ARABIC_DIACRITICS = {
    "\u064b",  # tanwin fatha
    "\u064c",  # tanwin damma
    "\u064d",  # tanwin kasra
    "\u064e",  # fatha
    "\u064f",  # damma
    "\u0650",  # kasra
    "\u0651",  # shadda
    "\u0652",  # sukun
    "\u0670",  # superscript alef
    "\u0653",  # maddah
    "\u0654",  # hamza above
    "\u0655",  # hamza below
}

_SOUTHERN_KURDISH_CHAR_MAP: Dict[str, str] = {
    "ا": "a",
    "أ": "a",
    "إ": "a",
    "آ": "a",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "dʒ",
    "چ": "tʃ",
    "ح": "h",
    "خ": "x",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ڕ": "r",
    "ز": "z",
    "ژ": "ʒ",
    "س": "s",
    "ش": "ʃ",
    "ع": "ʕ",
    "غ": "ɣ",
    "ف": "f",
    "ڤ": "v",
    "ق": "q",
    "ک": "k",
    "ك": "k",
    "گ": "g",
    "ل": "l",
    "ڵ": "ɫ",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ھ": "h",
    "ة": "e",
    "ە": "e",
    "ێ": "e",
    "ۆ": "o",
    "ئ": "ʔ",
    "ء": "ʔ",
}

_SOUTHERN_KURDISH_DIGRAPHS = {
    "وو": "u",
}


def _is_probably_arabic_script(text: str) -> bool:
    """Return True if text appears to use Arabic-script code points."""
    for char in text:
        code = ord(char)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            return True
    return False


def southern_kurdish_arabic_to_ipa(text: str) -> str:
    """Best-effort Arabic-script Southern Kurdish -> IPA fallback.

    This is intentionally lightweight and dependency-free, used when local IPA
    backends are unavailable. It is not a full phonological model.
    """
    normalized = str(text)
    normalized = normalized.replace("\u200c", "")
    normalized = normalized.replace("\u200d", "")

    for source, target in _SOUTHERN_KURDISH_DIGRAPHS.items():
        normalized = normalized.replace(source, target)

    output: List[str] = []
    for index, char in enumerate(normalized):
        if char in _ARABIC_DIACRITICS:
            continue

        if char in {"\n", "\r", "\t"}:
            output.append(" ")
            continue

        if char.isspace():
            output.append(" ")
            continue

        if char in {"ی", "ي", "ى"}:
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("j" if prev_is_space else "i")
            continue

        if char == "و":
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("w" if prev_is_space else "u")
            continue

        mapped = _SOUTHERN_KURDISH_CHAR_MAP.get(char)
        if mapped is not None:
            output.append(mapped)
            continue

        if char.isascii() and (char.isalnum() or char in "-_'"):
            output.append(char.lower())
            continue

    ipa = "".join(output)
    ipa = re.sub(r"\s+", " ", ipa).strip()
    return ipa


def _epitran_code_for_language(language: Optional[str]) -> Optional[str]:
    """Resolve best-effort Epitran code from a language code."""
    if not language:
        return "kur-Arab"

    normalized = str(language).strip().lower()
    if not normalized:
        return "kur-Arab"

    mapping = {
        "sdh": "kur-Arab",
        "ckb": "kur-Arab",
        "ku": "kur-Arab",
        "kur": "kur-Arab",
        "sd": "snd-Arab",
        "fa": "fas-Arab",
        "fas": "fas-Arab",
        "ar": "ara-Arab",
        "ara": "ara-Arab",
    }

    if normalized in mapping:
        return mapping[normalized]

    if "-" in normalized:
        return normalized

    return None


def _audio_duration_seconds(audio_path: Path) -> float:
    """Read audio duration using soundfile."""
    try:
        import soundfile as sf
    except ImportError:
        return 0.0

    try:
        info = sf.info(str(audio_path))
    except Exception:
        return 0.0

    duration = float(getattr(info, "duration", 0.0) or 0.0)
    if duration < 0.0:
        return 0.0
    return duration


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
    ) -> List[Segment]:
        """Transcribe an audio file into timestamped segments."""
        raise NotImplementedError

    @abc.abstractmethod
    def to_ipa(self, text: str, language: str) -> str:
        """Convert orthographic text to IPA."""
        raise NotImplementedError


class LocalWhisperProvider(AIProvider):
    """Local provider backed by faster-whisper.

    Used by both STT (``config_section="stt"``) and ORTHO
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
        self.language = str(language or section_config.get("language", "")).strip() or None
        self.device = str(device or section_config.get("device", "cpu")).strip() or "cpu"
        self.compute_type = (
            str(compute_type or section_config.get("compute_type", "int8")).strip() or "int8"
        )

        try:
            self.beam_size = max(1, int(stt_config.get("beam_size", 5) or 5))
        except (TypeError, ValueError):
            self.beam_size = 5
        task_raw = str(stt_config.get("task", "transcribe") or "transcribe").strip().lower()
        self.task = task_raw if task_raw in {"transcribe", "translate"} else "transcribe"
        self.vad_filter = bool(stt_config.get("vad_filter", True))
        vad_params_raw = stt_config.get("vad_parameters")
        # Only forward a dict when the user has set explicit parameters;
        # an empty {} falls through to faster-whisper's Silero defaults.
        self.vad_parameters: Optional[Dict[str, Any]] = (
            dict(vad_params_raw) if isinstance(vad_params_raw, dict) and vad_params_raw else None
        )

        if _stt_force_cpu_env() and self.device.lower().startswith("cuda"):
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
        self._epitran_instances: Dict[str, Any] = {}

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

        _register_cuda_dll_directories()

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
            cuda_failure = wants_gpu and _looks_like_cuda_runtime_failure(message)
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
    ) -> List[Segment]:
        """Run full-file STT with faster-whisper."""
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(path))

        model = self._load_whisper_model()
        # Auto-detect when the user hasn't forced a language (empty/None).
        # faster-whisper treats language=None as auto-detect; language=""
        # would error.
        selected_language = (language or self.language) or None

        def _run_transcription(m: Any) -> List[Segment]:
            segs_out: List[Segment] = []
            transcribe_kwargs: Dict[str, Any] = {
                "language": selected_language,
                "beam_size": self.beam_size,
                "task": self.task,
                "vad_filter": self.vad_filter,
            }
            if self.vad_filter and self.vad_parameters is not None:
                transcribe_kwargs["vad_parameters"] = self.vad_parameters
            segs_iter, info = m.transcribe(str(path), **transcribe_kwargs)
            total_duration = float(getattr(info, "duration", 0.0) or 0.0)
            for segment in segs_iter:
                start = float(_dict_or_attr(segment, "start", 0.0) or 0.0)
                end = float(_dict_or_attr(segment, "end", start) or start)
                text = str(_dict_or_attr(segment, "text", "") or "").strip()
                avg_logprob = _dict_or_attr(segment, "avg_logprob", None)
                segs_out.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                        "confidence": _confidence_from_logprob(avg_logprob),
                    }
                )
                if progress_callback is not None and total_duration > 0.0:
                    progress = _coerce_confidence(end / total_duration) * 100.0
                    progress_callback(progress, len(segs_out))
            return segs_out

        try:
            segments_out = _run_transcription(model)
        except Exception as exc:
            on_cuda = (
                self._effective_device is not None
                and self._effective_device.lower().startswith("cuda")
            )
            cuda_failure = on_cuda or _looks_like_cuda_runtime_failure(str(exc))
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

    def _epitran_transliterate(self, text: str, language: Optional[str]) -> Optional[str]:
        """Try transliteration with Epitran; return None when unavailable."""
        code = _epitran_code_for_language(language)
        if not code:
            return None

        try:
            import epitran
        except ImportError:
            return None

        instance = self._epitran_instances.get(code)
        if instance is None:
            try:
                instance = epitran.Epitran(code)
            except Exception as exc:
                print(
                    "[WARN] Could not initialize Epitran with code '{0}': {1}".format(
                        code, exc
                    ),
                    file=sys.stderr,
                )
                return None
            self._epitran_instances[code] = instance

        try:
            transliterated = str(instance.transliterate(text)).strip()
        except Exception as exc:
            print(
                "[WARN] Epitran transliteration failed: {0}".format(exc),
                file=sys.stderr,
            )
            return None

        if not transliterated:
            return None

        return transliterated

    def to_ipa(self, text: str, language: str) -> str:
        """Convert orthography to IPA using local tooling with Kurdish fallback."""
        value = str(text or "").strip()
        if not value:
            return ""

        transliterated = self._epitran_transliterate(value, language)
        if transliterated:
            return _strip_ipa_wrappers(transliterated)

        if _is_probably_arabic_script(value):
            return southern_kurdish_arabic_to_ipa(value)

        return value


class OpenAIProvider(AIProvider):
    """OpenAI-backed provider for STT and IPA conversion."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        stt_config = self.config.get("stt", {})
        llm_config = self.config.get("llm", {})

        self.stt_model = str(stt_config.get("model", "whisper-1")).strip() or "whisper-1"
        self.language = str(stt_config.get("language", "")).strip() or None
        self.llm_model = _normalize_openai_model_name(llm_config.get("model"), default="gpt-5.4")
        self.api_key_env = (
            str(llm_config.get("api_key_env", "OPENAI_API_KEY")).strip()
            or "OPENAI_API_KEY"
        )

        self._client: Optional[Any] = None

    def _load_client(self) -> Any:
        """Lazy-load OpenAI client."""
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                "OpenAI API key environment variable is missing: {0}".format(
                    self.api_key_env
                )
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            print(
                "[ERROR] openai package is not installed.",
                file=sys.stderr,
            )
            raise RuntimeError("openai dependency missing") from exc

        self._client = OpenAI(api_key=api_key)
        return self._client

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Transcribe audio with OpenAI STT endpoint."""
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(path))

        client = self._load_client()
        selected_language = language or self.language

        request_kwargs: Dict[str, Any] = {
            "model": self.stt_model,
            "file": None,
            "response_format": "verbose_json",
        }
        if selected_language:
            request_kwargs["language"] = selected_language

        segments_out: List[Segment] = []

        with path.open("rb") as audio_handle:
            request_kwargs["file"] = audio_handle
            try:
                request_kwargs["timestamp_granularities"] = ["segment"]
                response = client.audio.transcriptions.create(**request_kwargs)
            except TypeError:
                request_kwargs.pop("timestamp_granularities", None)
                response = client.audio.transcriptions.create(**request_kwargs)

        raw_segments = _dict_or_attr(response, "segments", None)
        if raw_segments:
            for index, segment in enumerate(raw_segments, start=1):
                start = float(_dict_or_attr(segment, "start", 0.0) or 0.0)
                end = float(_dict_or_attr(segment, "end", start) or start)
                text = str(_dict_or_attr(segment, "text", "") or "").strip()

                avg_logprob = _dict_or_attr(segment, "avg_logprob", None)
                confidence = _confidence_from_logprob(avg_logprob)
                if confidence == 0.0:
                    confidence = _coerce_confidence(
                        float(_dict_or_attr(segment, "confidence", 0.0) or 0.0)
                    )

                segments_out.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                        "confidence": confidence,
                    }
                )

                if progress_callback is not None:
                    progress_callback(100.0, index)
        else:
            text = str(_dict_or_attr(response, "text", "") or "").strip()
            duration = _audio_duration_seconds(path)
            segments_out.append(
                {
                    "start": 0.0,
                    "end": duration,
                    "text": text,
                    "confidence": 0.0,
                }
            )
            if progress_callback is not None:
                progress_callback(100.0, 1)

        return segments_out

    def to_ipa(self, text: str, language: str) -> str:
        """Convert text to IPA using an OpenAI chat model."""
        value = str(text or "").strip()
        if not value:
            return ""

        client = self._load_client()
        prompt = (
            "Convert the following text to IPA. "
            "Return only IPA characters with no explanation.\n"
            "Language code: {0}\n"
            "Text: {1}"
        ).format(language, value)

        response = client.chat.completions.create(
            model=self.llm_model,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a linguistics transcription assistant. "
                        "Output IPA only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        if not response.choices:
            raise RuntimeError("OpenAI returned no choices for IPA conversion")

        message = response.choices[0].message
        content = str(getattr(message, "content", "") or "").strip()
        if not content:
            return value

        return _strip_ipa_wrappers(content)


class XAIProvider(OpenAIProvider):
    """xAI (Grok) provider. Uses OpenAI-compatible API at api.x.ai."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        stt_config = self.config.get("stt", {})
        llm_config = self.config.get("llm", {})

        self.base_url = "https://api.x.ai/v1"

        configured_api_key_env = str(llm_config.get("api_key_env", "")).strip()
        if not configured_api_key_env or configured_api_key_env == "OPENAI_API_KEY":
            configured_api_key_env = "XAI_API_KEY"
        self.api_key_env = configured_api_key_env

        configured_llm_model = str(llm_config.get("model", "")).strip()
        if not configured_llm_model or configured_llm_model in {"gpt54", "gpt-4o", "gpt-5.4"}:
            configured_llm_model = "grok-4.20-0309-reasoning"
        self.llm_model = configured_llm_model

        self.stt_model = (
            str(stt_config.get("model", "whisper-large-v3")).strip()
            or "whisper-large-v3"
        )

        self._stt_fallback = LocalWhisperProvider(
            config=self.config,
            config_path=self.config_path,
        )

    def _load_client(self) -> Any:
        """Lazy-load xAI client via OpenAI-compatible SDK."""
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                "xAI API key environment variable is missing: {0}".format(
                    self.api_key_env
                )
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            print(
                "[ERROR] openai package is not installed.",
                file=sys.stderr,
            )
            raise RuntimeError("openai dependency missing") from exc

        self._client = OpenAI(api_key=api_key, base_url=self.base_url)
        return self._client

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Use local faster-whisper fallback for STT."""
        return self._stt_fallback.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=progress_callback,
        )


class OllamaProvider(AIProvider):
    """Ollama-backed local LLM provider."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        llm_config = self.config.get("llm", {})
        self.model = str(llm_config.get("model", "llama3.1")).strip() or "llama3.1"
        self.host = str(os.environ.get("OLLAMA_HOST", "http://localhost:11434")).strip()
        self.host = self.host.rstrip("/")

        self._stt_fallback = LocalWhisperProvider(
            config=self.config,
            config_path=self.config_path,
        )

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Use local faster-whisper fallback for STT."""
        return self._stt_fallback.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=progress_callback,
        )

    def _generate(self, prompt: str) -> str:
        """Call Ollama /api/generate."""
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            "{0}/api/generate".format(self.host),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError("Failed to contact Ollama at {0}: {1}".format(self.host, exc))

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Invalid JSON response from Ollama: {0}".format(exc))

        return str(body.get("response", "") or "").strip()

    def to_ipa(self, text: str, language: str) -> str:
        """Convert text to IPA using an Ollama LLM prompt."""
        value = str(text or "").strip()
        if not value:
            return ""

        prompt = (
            "Convert this text to IPA and output only IPA symbols. "
            "Language code: {0}. Text: {1}"
        ).format(language, value)
        response = self._generate(prompt)

        if not response:
            return value

        return _strip_ipa_wrappers(response)


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
    """Resolve provider name from config sections using priority order.

    When `override_config` is provided, its section providers are checked first.
    An explicit empty provider in an override section suppresses that section from
    fallback resolution in the merged config.
    """
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


def get_stt_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for STT providers resolved from `stt.provider`."""
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(merged, ["stt"], override_config=override)
    return _build_provider(provider_name, merged)


def get_ortho_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for the orthographic transcription provider (razhan/whisper-base-sdh).

    ORTHO is always a faster-whisper model configured in the `ortho` block,
    distinct from whatever general-purpose model STT uses. This goes straight
    to ``LocalWhisperProvider`` with ``config_section="ortho"`` so
    model_path / device / language come from the ortho block rather than stt.
    """
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    return LocalWhisperProvider(config=merged, config_section="ortho")


def get_ipa_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for IPA providers resolved from `ipa.provider` fallback chain."""
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(
        merged,
        ["ipa", "llm", "stt"],
        override_config=override,
    )
    return _build_provider(provider_name, merged)


def get_llm_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for LLM providers resolved from `llm.provider` fallback chain."""
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(
        merged,
        ["llm", "stt"],
        override_config=override,
    )
    return _build_provider(provider_name, merged)


def get_provider(config: Dict[str, Any]) -> AIProvider:
    """Factory for AI providers.

    Deprecated: use `get_stt_provider`, `get_ipa_provider`, or
    `get_llm_provider` for feature-specific provider resolution.

    By default this resolves against STT provider configuration.
    Pass an explicit top-level `provider` key in `config` to override.
    """
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)

    provider_name = str(override.get("provider", "")).strip().lower()
    if not provider_name:
        provider_name = _resolve_provider_name(merged, ["stt"])

    return _build_provider(provider_name, merged)


__all__ = [
    "Segment",
    "AIProvider",
    "LocalWhisperProvider",
    "OpenAIProvider",
    "XAIProvider",
    "OllamaProvider",
    "OpenAIChatRuntime",
    "get_stt_provider",
    "get_ortho_provider",
    "get_ipa_provider",
    "get_llm_provider",
    "get_chat_config",
    "get_provider",
    "load_ai_config",
    "resolve_ai_config_path",
    "southern_kurdish_arabic_to_ipa",
]
