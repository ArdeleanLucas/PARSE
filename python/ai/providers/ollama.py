from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import ai.provider as provider_module

from .local_whisper import LocalWhisperProvider

class OllamaProvider(provider_module.AIProvider):
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
        segment_callback: Optional[Callable[[Segment], None]] = None,
    ) -> List[Segment]:
        """Use local faster-whisper fallback for STT."""
        return self._stt_fallback.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=progress_callback,
            segment_callback=segment_callback,
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

__all__ = ["OllamaProvider"]
