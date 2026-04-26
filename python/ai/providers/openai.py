from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import ai.provider as provider_module

class OpenAIChatRuntime:
    """Thin OpenAI chat runtime wrapper with tool-call support and reasoning fallback."""

    # Provider-specific base URLs for the OpenAI-compatible API
    _PROVIDER_BASE_URLS: Dict[str, str] = dict(provider_module._CHAT_PROVIDER_BASE_URLS)

    # Default models per provider (used when config still has a placeholder/OpenAI model)
    _PROVIDER_DEFAULT_MODELS: Dict[str, str] = dict(provider_module._CHAT_PROVIDER_DEFAULT_MODELS)

    # Model names that are clearly OpenAI-only and should be swapped for xAI
    _OPENAI_ONLY_MODELS = set(provider_module._CHAT_OPENAI_ONLY_MODELS)

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.config_path = provider_module.resolve_ai_config_path(config_path)
        file_config = provider_module.load_ai_config(self.config_path)
        merged_config = provider_module._deep_merge_dicts(file_config, config or {})

        self.chat_config = provider_module._build_chat_config(merged_config)
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

        from ..openai_auth import (
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
                        "totalTokens": provider_module._extract_total_tokens(response),
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
                "totalTokens": provider_module._extract_total_tokens(response),
            },
        )

class OpenAIProvider(provider_module.AIProvider):
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
        self.llm_model = provider_module._normalize_openai_model_name(llm_config.get("model"), default="gpt-5.4")
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
        segment_callback: Optional[Callable[[Segment], None]] = None,
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

        raw_segments = provider_module._dict_or_attr(response, "segments", None)
        if raw_segments:
            for index, segment in enumerate(raw_segments, start=1):
                start = float(provider_module._dict_or_attr(segment, "start", 0.0) or 0.0)
                end = float(provider_module._dict_or_attr(segment, "end", start) or start)
                text = str(provider_module._dict_or_attr(segment, "text", "") or "").strip()

                avg_logprob = provider_module._dict_or_attr(segment, "avg_logprob", None)
                confidence = provider_module._confidence_from_logprob(avg_logprob)
                if confidence == 0.0:
                    confidence = provider_module._coerce_confidence(
                        float(provider_module._dict_or_attr(segment, "confidence", 0.0) or 0.0)
                    )

                segments_out.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                        "confidence": confidence,
                    }
                )
                if segment_callback is not None:
                    segment_callback(copy.deepcopy(segments_out[-1]))

                if progress_callback is not None:
                    progress_callback(100.0, index)
        else:
            text = str(provider_module._dict_or_attr(response, "text", "") or "").strip()
            duration = provider_module._audio_duration_seconds(path)
            segments_out.append(
                {
                    "start": 0.0,
                    "end": duration,
                    "text": text,
                    "confidence": 0.0,
                }
            )
            if segment_callback is not None:
                segment_callback(copy.deepcopy(segments_out[-1]))
            if progress_callback is not None:
                progress_callback(100.0, 1)

        return segments_out

__all__ = ["OpenAIChatRuntime", "OpenAIProvider"]
