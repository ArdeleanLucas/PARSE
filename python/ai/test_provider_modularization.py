from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import ai.provider as provider_module
from ai.providers.local_whisper import LocalWhisperProvider
from ai.providers.ollama import OllamaProvider
from ai.providers.openai import OpenAIChatRuntime, OpenAIProvider
from ai.providers.xai import XAIProvider


def test_provider_module_reexports_split_provider_classes() -> None:
    assert provider_module.LocalWhisperProvider is LocalWhisperProvider
    assert provider_module.OpenAIProvider is OpenAIProvider
    assert provider_module.XAIProvider is XAIProvider
    assert provider_module.OllamaProvider is OllamaProvider
    assert provider_module.OpenAIChatRuntime is OpenAIChatRuntime
