from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .local_whisper import LocalWhisperProvider
from .openai import OpenAIProvider

if TYPE_CHECKING:
    from ai.provider import Segment

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
        segment_callback: Optional[Callable[[Segment], None]] = None,
    ) -> List[Segment]:
        """Use local faster-whisper fallback for STT."""
        return self._stt_fallback.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=progress_callback,
            segment_callback=segment_callback,
        )

__all__ = ["XAIProvider"]
