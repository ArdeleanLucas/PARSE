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


class WordSpan(TypedDict, total=False):
    """Per-word timing from faster-whisper word_timestamps=True.

    Optional enrichment attached to Segment.words in Tier 1 of the acoustic
    alignment pipeline. Consumers that predate Tier 1 simply ignore it.
    """

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
    """Segment enriched with per-word spans (Tier 1 acoustic alignment).

    Structural subtype of Segment — legacy consumers ignore the extra key.
    """

    words: List[WordSpan]


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
    # Tier 3 acoustic alignment: wav2vec2 is the ONLY IPA engine. Text-based
    # paths (Epitran, LLM prompts, Arabic-to-IPA rules) have been removed.
    # The ``engine`` key is informational — the code path is hard-wired to
    # facebook/wav2vec2-xlsr-53-espeak-cv-ft via ai.forced_align.Aligner.
    "ipa": {
        "engine": "wav2vec2",
        "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
    },
    "ortho": {
        "provider": "faster-whisper",
        "model_path": "razhan/whisper-base-sdh",
        "language": "sd",
        "device": "cuda",
        "compute_type": "float16",
        # ORTH: VAD on with TUNED Silero parameters that don't
        # collapse coverage. Flipped from ``vad_filter=False`` on
        # 2026-04-23 after Fail02 regressed from 131 full-coverage
        # intervals to 38 intervals truncating at 06:31 with classic
        # whisper repetition-loop hallucination ("ئە ئە ئە ئە ئە ...").
        # Root cause was faster-whisper's ``condition_on_previous_text``
        # default carrying a poisoned segment forward into every
        # subsequent segment; tuned VAD gating silence gaps prevents
        # the decoder from entering that state in the first place.
        # Untuned Silero is too conservative for fieldwork recordings,
        # hence the explicit params below. See provider __init__ for
        # the full back-story.
        "vad_filter": True,
        "vad_parameters": {
            # Require 500 ms of silence before gating (leaves
            # inter-word pauses to Whisper). Stock Silero uses
            # 2000 ms which misses short Kurdish utterance gaps.
            "min_silence_duration_ms": 500,
            # 0.35 voice-probability threshold (stock 0.5). Catches
            # quieter elicitation speech that the default misses.
            "threshold": 0.35,
        },
        # Keep one bad segment from poisoning the entire downstream
        # decode — this is THE fix for the repetition cascade.
        "condition_on_previous_text": False,
        # Stricter than Whisper's 2.4 default so the decoder falls
        # back to higher temperature (or drops the segment) earlier
        # when it detects repetition.
        "compression_ratio_threshold": 1.8,
        # Optional decoder priming string for elicited word-list recordings.
        # Empty = not passed to faster-whisper.
        "initial_prompt": "",
        # When True the ORTH compute runner will also do a short-clip
        # Whisper pass per concept after Tier-2 forced alignment. Off by
        # default — opt in per speaker via the compute payload or per
        # machine via ai_config.json.
        "refine_lexemes": False,
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
    """Resolve ai_config.json path.

    Search order (first match wins):
      1. ``config_path`` arg, if provided.
      2. ``PARSE_AI_CONFIG`` env var (escape hatch for operators).
      3. ``<cwd>/config/ai_config.json`` — matches server.py's ``_config_path()``
         which reads from cwd. The server runs with cwd set to the
         project workspace (e.g. ``/home/lucas/parse-workspace``), so
         this is where the user's real config lives.
      4. ``<repo>/config/ai_config.json`` — the historical location,
         relative to this module's path. Kept as a fallback for
         scripts/tests that import ``load_ai_config`` without a
         meaningful cwd.

    Returns the *first existing* path, else the repo path (so the
    "missing" WARN in ``load_ai_config`` surfaces a coherent message).

    Fixes a silent bug where the server reported
    ``stt.model_path: C:\\...razhan-whisper-ct2`` via ``/api/config``
    (which reads from cwd) while ``get_stt_provider()`` fell back to
    defaults — because this function was only checking the repo path,
    which is empty on a fresh deploy. ORTH in particular needs razhan
    configured; defaults hand it the HF repo id which faster-whisper
    can't load, and every ORTH run silently errored.
    """
    if config_path is not None:
        return Path(config_path).expanduser().resolve()

    env_override = os.environ.get("PARSE_AI_CONFIG", "").strip()
    if env_override:
        return Path(env_override).expanduser().resolve()

    cwd_candidate = Path.cwd() / "config" / "ai_config.json"
    if cwd_candidate.exists():
        return cwd_candidate.resolve()

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


def _dict_or_attr(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from dict-like or object-like values."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _extract_word_spans(segment: Any) -> List[WordSpan]:
    """Pull per-word spans from a faster-whisper Segment when available.

    Returns an empty list for providers/modes that don't produce word-level
    timestamps so SegmentWithWords.words can be omitted cleanly.
    """
    raw_words = _dict_or_attr(segment, "words", None)
    if not raw_words:
        return []
    out: List[WordSpan] = []
    for w in raw_words:
        text = str(_dict_or_attr(w, "word", "") or "").strip()
        if not text:
            continue
        try:
            start = float(_dict_or_attr(w, "start", 0.0) or 0.0)
            end = float(_dict_or_attr(w, "end", start) or start)
        except (TypeError, ValueError):
            continue
        prob_raw = _dict_or_attr(w, "probability", None)
        entry: WordSpan = {"word": text, "start": start, "end": end}
        if prob_raw is not None:
            try:
                entry["prob"] = _coerce_confidence(float(prob_raw))
            except (TypeError, ValueError):
                pass
        out.append(entry)
    return out


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


_HF_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


def _looks_like_hf_repo_id(value: str) -> bool:
    """Distinguish a HuggingFace repo id (``org/name``) from a filesystem path.

    HF ids are two simple segments with a forward slash. Local paths can
    contain forward slashes too (POSIX absolute paths, WSL paths with
    forward slashes) so we check for disqualifying markers first:
    drive letters, leading slashes, backslashes, or more than one slash.
    """
    text = str(value or "").strip()
    if not text:
        return False
    if "\\" in text:
        return False
    if text.startswith(("/", ".")) or (len(text) >= 2 and text[1] == ":"):
        return False
    return bool(_HF_REPO_ID_RE.match(text))


def _collect_nvidia_wheel_bin_dirs() -> List[Path]:
    """Return ``<site-packages>/nvidia/<subpkg>/bin`` dirs for every
    installed NVIDIA wheel (cublas, cudnn, cuda-runtime, …).

    ``nvidia`` is a PEP-420 *namespace* package — there is no
    ``nvidia/__init__.py``, so ``nvidia.__file__`` is ``None``. We
    must iterate ``nvidia.__path__`` (a list of directories that
    contribute to the namespace) to find the subpackage roots.

    A prior revision used ``Path(nvidia.__file__).resolve().parent``
    which raises ``TypeError`` when ``__file__`` is ``None``. The
    enclosing ``except Exception: pass`` swallowed it, so no DLL
    directories ever got registered — faster-whisper silently fell
    back to CPU at the first cuBLAS call. This helper is the fix;
    the bottom of ``test_ortho_provider_fallback.py`` locks the
    behaviour in.
    """
    results: List[Path] = []
    try:
        import nvidia  # type: ignore[import-not-found]
    except ImportError:
        return results

    # __path__ can be a list of str OR a _NamespacePath — iterate uniformly.
    roots: List[str] = []
    try:
        roots = list(nvidia.__path__)  # type: ignore[attr-defined]
    except TypeError:
        return results

    for root_str in roots:
        try:
            nvidia_root = Path(root_str)
        except Exception:
            continue
        if not nvidia_root.is_dir():
            continue
        for entry in nvidia_root.iterdir():
            bin_dir = entry / "bin"
            if bin_dir.is_dir():
                results.append(bin_dir)
    return results


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

    # 1. NVIDIA pip wheels (nvidia-cublas-cu12, nvidia-cudnn-cu12,
    #    nvidia-cuda-runtime-cu12, …). Extracted into a helper so it
    #    can be unit-tested without the surrounding Windows-only gate.
    candidates.extend(_collect_nvidia_wheel_bin_dirs())

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
            # Directory exists but cannot be registered (e.g. permissions).
            # Skip silently — the WhisperModel try/except below will surface
            # any remaining DLL load failures with full context.
            pass

    # One-shot diagnostic on stderr so silent registration failures
    # (e.g. the nvidia.__file__=None namespace-package bug that caused
    # production CPU fallbacks for months) are immediately visible.
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
            "[WARN] No CUDA DLL directories could be registered. If you expect "
            "GPU inference, install the NVIDIA runtime wheels: "
            "`pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12`.",
            file=sys.stderr,
        )


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

class LocalWhisperProvider(AIProvider):
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

        # If an ORTH provider has no explicit model_path, fall back to
        # stt.model_path — users who configured razhan (or any local CT2)
        # for STT almost always want the same model for ORTH, and
        # HuggingFace-repo-id defaults like "razhan/whisper-base-sdh" don't
        # resolve to faster-whisper's CT2 format so they fail at load time.
        # Explicit empty/HF-id → stt.model_path (when non-empty).
        if self.config_section == "ortho":
            if not self.model_path or _looks_like_hf_repo_id(self.model_path):
                stt_fallback = str(
                    self.config.get("stt", {}).get("model_path", "") or ""
                ).strip()
                if stt_fallback:
                    if self.model_path:
                        print(
                            "[INFO] ortho.model_path '{0}' looks like a HuggingFace "
                            "repo id; faster-whisper needs CT2. Falling back to "
                            "stt.model_path '{1}'.".format(self.model_path, stt_fallback),
                            file=sys.stderr,
                        )
                    self.model_path = stt_fallback
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
        self.refine_lexemes: bool = _coerce_bool(
            section_config.get("refine_lexemes", False), default=False
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
                start = float(_dict_or_attr(segment, "start", 0.0) or 0.0)
                end = float(_dict_or_attr(segment, "end", start) or start)
                text = str(_dict_or_attr(segment, "text", "") or "").strip()
                avg_logprob = _dict_or_attr(segment, "avg_logprob", None)
                words_out = _extract_word_spans(segment)
                seg_dict: SegmentWithWords = {
                    "start": start,
                    "end": end,
                    "text": text,
                    "confidence": _confidence_from_logprob(avg_logprob),
                }
                if words_out:
                    seg_dict["words"] = words_out
                segs_out.append(seg_dict)
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

    def transcribe_clip(
        self,
        audio_array: Any,
        *,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Tuple[str, float]:
        """Transcribe a preloaded mono-16kHz numpy array and return ``(text, confidence)``.

        Unlike :meth:`transcribe` this takes an in-memory audio array (not a
        file path) and returns a flat ``(text, confidence)`` tuple rather
        than a list of segments. ``confidence`` is derived from the best
        segment ``avg_logprob`` the same way :meth:`transcribe` does; the
        returned text is the concatenation of all segments (usually 1 for
        short clips). Empty input yields ``("", 0.0)``.

        Used by the ORTH compute runner's short-clip fallback — the caller
        has already sliced a ±0.8s window around a concept anchor and loaded
        the audio once via ``ai.forced_align._load_audio_mono_16k``.
        """
        if audio_array is None:
            return ("", 0.0)

        model = self._load_whisper_model()
        selected_language = (language or self.language) or None
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
            text = str(_dict_or_attr(seg, "text", "") or "").strip()
            if text:
                parts.append(text)
                conf = _confidence_from_logprob(_dict_or_attr(seg, "avg_logprob", None))
                if conf and conf > best_conf:
                    best_conf = conf
        return (" ".join(parts).strip(), float(best_conf))


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


# Persistent-worker preload cache. Set by ``preload_stt_provider`` /
# ``preload_ortho_provider`` (called once at worker startup) so the
# factory getters below skip the model build when no custom config is
# requested. Non-worker callers never touch these globals — the cache
# stays None and the factories behave as before.
_PRELOADED_STT_PROVIDER: Optional[AIProvider] = None
_PRELOADED_ORTHO_PROVIDER: Optional[AIProvider] = None


def preload_stt_provider(config: Optional[Dict[str, Any]] = None) -> Optional[AIProvider]:
    """Build the STT provider, warm its Whisper model, and cache it.

    Returns the cached instance, or ``None`` if anything fails (missing
    model, CUDA runtime error, etc.). Worker startup calls this; a
    failure is non-fatal — the factory still works on-demand.
    """
    global _PRELOADED_STT_PROVIDER
    try:
        provider = _build_stt_provider(config)
        if isinstance(provider, LocalWhisperProvider):
            provider.warm_up()
        _PRELOADED_STT_PROVIDER = provider
        return provider
    except Exception as exc:
        print(
            "[provider] STT preload failed: {0}".format(exc),
            file=sys.stderr,
            flush=True,
        )
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
        print(
            "[provider] ORTH preload failed: {0}".format(exc),
            file=sys.stderr,
            flush=True,
        )
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
    """Factory for STT providers resolved from `stt.provider`.

    Returns the preloaded singleton when available and the caller did
    not pass a custom ``config`` override. Custom configs always get a
    fresh build so tests and ad-hoc callers see the correct provider.
    """
    if _PRELOADED_STT_PROVIDER is not None and config is None:
        return _PRELOADED_STT_PROVIDER
    return _build_stt_provider(config)


def get_ortho_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for the orthographic transcription provider (razhan/whisper-base-sdh).

    ORTH is always a faster-whisper model configured in the `ortho` block,
    distinct from whatever general-purpose model STT uses. This goes straight
    to ``LocalWhisperProvider`` with ``config_section="ortho"`` so
    model_path / device / language come from the ortho block rather than stt.

    Returns the preloaded singleton when available and no custom
    ``config`` was passed (see ``preload_ortho_provider``).
    """
    if _PRELOADED_ORTHO_PROVIDER is not None and config is None:
        return _PRELOADED_ORTHO_PROVIDER
    return _build_ortho_provider(config)


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

    Deprecated: use `get_stt_provider` or `get_llm_provider` for
    feature-specific provider resolution. IPA is generated acoustically
    via ai.forced_align.Aligner and has no provider factory any more.

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
    "get_llm_provider",
    "get_chat_config",
    "get_provider",
    "load_ai_config",
    "resolve_ai_config_path",
]
