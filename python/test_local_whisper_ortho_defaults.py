from __future__ import annotations

import sys
import types
from typing import Any, Dict, List

from ai import provider as provider_module
from ai.providers import local_whisper
from ai.providers.local_whisper import LocalWhisperProvider

_EXPECTED_ORTH_DEFAULT_INITIAL_PROMPT = getattr(
    local_whisper,
    "_ORTH_DEFAULT_INITIAL_PROMPT",
    "کوڕ و کچ. مال و باخ. ئاو و خاک. هاتن و چوون. ئەم زمانە کوردیە.",
)


class _RecordingWhisperModel:
    calls: List[Dict[str, Any]] = []

    def __init__(self, model_source: str, *, device: str, compute_type: str) -> None:
        type(self).calls.append(
            {
                "model_source": model_source,
                "device": device,
                "compute_type": compute_type,
            }
        )


class _CudaThenCpuWhisperModel:
    calls: List[Dict[str, Any]] = []

    def __init__(self, model_source: str, *, device: str, compute_type: str) -> None:
        type(self).calls.append(
            {
                "model_source": model_source,
                "device": device,
                "compute_type": compute_type,
            }
        )
        if device == "cuda":
            raise RuntimeError("CUDA driver version is insufficient for CUDA runtime")


def _ortho_config(**overrides: Any) -> Dict[str, Any]:
    return {
        "provider": "faster-whisper",
        "model_path": "/tmp/razhan-sdh-ct2",
        "language": "sd",
        "device": "cpu",
        "compute_type": "int8",
        **overrides,
    }


def _provider(config_section: str, section_config: Dict[str, Any]) -> LocalWhisperProvider:
    return LocalWhisperProvider(
        config={config_section: section_config},
        config_section=config_section,
    )


def _install_whisper_stub(monkeypatch: Any, stub: type) -> None:
    stub.calls = []
    monkeypatch.setattr(
        provider_module, "_register_cuda_dll_directories", lambda: None, raising=False
    )
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=stub),
    )


def test_ortho_default_initial_prompt_applies_when_key_absent() -> None:
    provider = _provider("ortho", _ortho_config())

    assert provider.initial_prompt == _EXPECTED_ORTH_DEFAULT_INITIAL_PROMPT


def test_ortho_explicit_empty_initial_prompt_overrides_default() -> None:
    provider = _provider("ortho", _ortho_config(initial_prompt=""))

    assert provider.initial_prompt == ""


def test_ortho_explicit_custom_initial_prompt_wins() -> None:
    provider = _provider("ortho", _ortho_config(initial_prompt="my custom prime"))

    assert provider.initial_prompt == "my custom prime"


def test_stt_section_does_not_get_ortho_default() -> None:
    provider = _provider(
        "stt",
        {
            "provider": "faster-whisper",
            "model_path": "",
            "language": "fa",
            "device": "cpu",
            "compute_type": "int8",
        },
    )

    assert provider.initial_prompt == ""


def test_stt_non_string_initial_prompt_still_resolves_empty() -> None:
    provider = _provider(
        "stt",
        {
            "provider": "faster-whisper",
            "model_path": "",
            "language": "fa",
            "device": "cpu",
            "compute_type": "int8",
            "initial_prompt": None,
        },
    )

    assert provider.initial_prompt == ""


def test_ortho_non_string_initial_prompt_falls_back_to_default() -> None:
    provider = _provider("ortho", _ortho_config(initial_prompt=None))

    assert provider.initial_prompt == _EXPECTED_ORTH_DEFAULT_INITIAL_PROMPT


def test_log_model_init_emits_section_tag_and_truncated_prompt(capsys: Any) -> None:
    long_prompt = "کوردی " * 30
    provider = _provider("ortho", _ortho_config(initial_prompt=long_prompt))
    provider._model_source = "/tmp/razhan-sdh-ct2"
    provider._effective_device = "cuda"
    provider._effective_compute_type = "float16"

    provider._log_model_init()

    err = capsys.readouterr().err
    assert "[ORTH] loaded model: /tmp/razhan-sdh-ct2" in err
    assert "device=cuda" in err
    assert "compute_type=float16" in err
    assert "language=fa" in err
    assert "initial_prompt=" in err
    assert "..." in err
    assert repr(long_prompt) not in err


def test_load_whisper_model_logs_once_when_model_is_initialized(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    _install_whisper_stub(monkeypatch, _RecordingWhisperModel)
    provider = _provider("ortho", _ortho_config())

    provider._load_whisper_model()
    provider._load_whisper_model()

    err = capsys.readouterr().err
    assert err.count("[ORTH] loaded model: /tmp/razhan-sdh-ct2") == 1
    assert "device=cpu" in err
    assert "compute_type=int8" in err
    assert "language=fa" in err
    assert _EXPECTED_ORTH_DEFAULT_INITIAL_PROMPT in err
    assert len(_RecordingWhisperModel.calls) == 1


def test_cpu_fallback_logs_effective_cpu_model_init(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    _install_whisper_stub(monkeypatch, _CudaThenCpuWhisperModel)
    provider = _provider("ortho", _ortho_config(device="cuda", compute_type="float16"))

    provider._load_whisper_model()

    err = capsys.readouterr().err
    assert "[WARN] CUDA backend unavailable for faster-whisper" in err
    assert "[ORTH] loaded model: /tmp/razhan-sdh-ct2" in err
    assert "device=cpu" in err
    assert "compute_type=int8" in err
    assert _CudaThenCpuWhisperModel.calls == [
        {
            "model_source": "/tmp/razhan-sdh-ct2",
            "device": "cuda",
            "compute_type": "float16",
        },
        {
            "model_source": "/tmp/razhan-sdh-ct2",
            "device": "cpu",
            "compute_type": "int8",
        },
    ]
