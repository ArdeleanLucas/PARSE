"""Device-aware compute_type coercion (Gate B3).

faster-whisper / ctranslate2 do not support compute_type "float16" on CPU
(it silently coerces to float32). When the resolved device is CPU, PARSE
coerces float16 → int8 (supported, low-memory) before model load. Any other
explicit CPU compute_type is a deliberate choice and is left untouched. GPU
(cuda) keeps float16.

The provider is constructed WITHOUT loading a model (no faster_whisper /
torch import at construction time), and ``resolve_compute_device`` is
monkeypatched in the local_whisper namespace so the resolved device is
deterministic without needing real torch / CUDA.
"""

from __future__ import annotations

from typing import Any, Dict

from ai.providers import local_whisper
from ai.providers.local_whisper import LocalWhisperProvider


def _config(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "provider": "faster-whisper",
        "model_path": "/tmp/razhan-sdh-ct2",
        "language": "sd",
        "compute_type": "float16",
    }
    base.update(overrides)
    return base


def _provider(
    monkeypatch: Any,
    *,
    resolved_device: str,
    config_section: str = "ortho",
    **config_overrides: Any,
) -> LocalWhisperProvider:
    # Force the resolved device deterministically; this is what
    # resolve_compute_device would return for the given machine/config.
    monkeypatch.setattr(
        local_whisper,
        "resolve_compute_device",
        lambda *args, **kwargs: resolved_device,
        raising=True,
    )
    return LocalWhisperProvider(
        config={config_section: _config(**config_overrides)},
        config_section=config_section,
    )


def test_cpu_resolved_float16_coerced_to_int8_ortho(monkeypatch: Any) -> None:
    provider = _provider(monkeypatch, resolved_device="cpu", config_section="ortho")

    assert provider.device == "cpu"
    assert provider.compute_type == "int8"


def test_cpu_resolved_float16_coerced_to_int8_stt(monkeypatch: Any) -> None:
    provider = _provider(
        monkeypatch,
        resolved_device="cpu",
        config_section="stt",
        model_path="",
        language="fa",
    )

    assert provider.device == "cpu"
    assert provider.compute_type == "int8"


def test_cpu_resolved_float16_emits_device_warning(
    monkeypatch: Any, capsys: Any
) -> None:
    _provider(monkeypatch, resolved_device="cpu")

    err = capsys.readouterr().err
    assert "[device]" in err
    assert "float16" in err
    assert "int8" in err


def test_cuda_resolved_float16_unchanged(monkeypatch: Any) -> None:
    provider = _provider(monkeypatch, resolved_device="cuda")

    assert provider.device == "cuda"
    assert provider.compute_type == "float16"


def test_cpu_resolved_explicit_float32_not_coerced(monkeypatch: Any) -> None:
    provider = _provider(
        monkeypatch, resolved_device="cpu", compute_type="float32"
    )

    assert provider.device == "cpu"
    assert provider.compute_type == "float32"


def test_cpu_resolved_explicit_int8_stays_int8(monkeypatch: Any) -> None:
    provider = _provider(monkeypatch, resolved_device="cpu", compute_type="int8")

    assert provider.device == "cpu"
    assert provider.compute_type == "int8"


def test_cpu_resolved_int8_float32_not_coerced(monkeypatch: Any) -> None:
    provider = _provider(
        monkeypatch, resolved_device="cpu", compute_type="int8_float32"
    )

    assert provider.device == "cpu"
    assert provider.compute_type == "int8_float32"
