from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clear_device_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "PARSE_STT_DEVICE",
        "PARSE_ORTH_DEVICE",
        "PARSE_IPA_DEVICE",
        "PARSE_COMPUTE_DEVICE",
        "PARSE_STT_FORCE_CPU",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.long_audio
def test_wav2vec2_cuda_sanity() -> None:
    try:
        import torch  # type: ignore
    except ImportError:
        pytest.skip("torch not importable")
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    from ai.forced_align import Aligner, DEFAULT_SAMPLE_RATE

    aligner = Aligner.load(device="cuda")
    audio = torch.zeros(DEFAULT_SAMPLE_RATE, dtype=torch.float32)
    ipa_text = aligner.transcribe_window(audio)

    assert aligner.device.startswith("cuda")
    assert isinstance(ipa_text, str)


def test_resolve_compute_device_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai import device as device_module

    monkeypatch.setattr(device_module, "_torch_cuda_available", lambda: True)
    monkeypatch.setenv("PARSE_COMPUTE_DEVICE", "cpu")
    assert device_module.resolve_compute_device("orth", config_device="cuda", section_default="auto") == "cpu"

    monkeypatch.setenv("PARSE_ORTH_DEVICE", "cuda:0")
    assert device_module.resolve_compute_device("orth", config_device="cpu", section_default="cpu") == "cuda:0"

    monkeypatch.delenv("PARSE_ORTH_DEVICE")
    monkeypatch.delenv("PARSE_COMPUTE_DEVICE")
    assert device_module.resolve_compute_device("orth", config_device="cpu", section_default="cuda") == "cpu"

    assert device_module.resolve_compute_device("orth", config_device=None, section_default="auto") == "cuda"


def test_resolve_compute_device_auto_falls_back_to_cpu_without_cuda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai import device as device_module

    monkeypatch.setattr(device_module, "_torch_cuda_available", lambda: False)

    assert device_module.resolve_compute_device("ipa", section_default="auto") == "cpu"


def test_resolve_compute_device_cuda_request_with_no_cuda_warns_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai import device as device_module

    monkeypatch.setattr(device_module, "_torch_cuda_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger="parse.device"):
        resolved = device_module.resolve_compute_device("stt", config_device="cuda")

    assert resolved == "cpu"
    assert "requested device='cuda'" in caplog.text
    assert "falling back to cpu" in caplog.text


def test_resolve_compute_device_explicit_cuda_falls_back_to_cpu_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai import device as device_module

    monkeypatch.setattr(device_module, "_torch_cuda_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger="parse.device"):
        resolved = device_module.resolve_compute_device(
            "orth", config_device="cuda", section_default="auto"
        )

    assert resolved == "cpu"
    assert "falling back to cpu" in caplog.text


def test_resolve_compute_device_stt_force_cpu_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai import device as device_module

    monkeypatch.setattr(device_module, "_torch_cuda_available", lambda: True)
    monkeypatch.setenv("PARSE_STT_FORCE_CPU", "1")

    assert device_module.resolve_compute_device("stt", section_default="auto") == "cpu"


def test_ai_device_imports_without_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "ai.device"
    old_module = sys.modules.pop(module_name, None)
    real_import = __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "torch":
            raise ImportError("no torch in lightweight env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    try:
        import ai.device as reimported_device

        assert reimported_device.resolve_compute_device("ipa", section_default="auto") == "cpu"
    finally:
        sys.modules.pop(module_name, None)
        if old_module is not None:
            sys.modules[module_name] = old_module


def test_local_whisper_uses_resolver_for_stt_and_ortho(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai.provider import LocalWhisperProvider

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(  # type: ignore[attr-defined]
        is_available=lambda: True,
        device_count=lambda: 1,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    provider = LocalWhisperProvider(
        config={
            "stt": {"model_path": "base", "compute_type": "float16"},
            "ortho": {"model_path": "/tmp/ct2-model", "compute_type": "float16"},
        },
        config_section="stt",
    )
    assert provider.device == "cuda"

    monkeypatch.setenv("PARSE_STT_FORCE_CPU", "1")
    forced = LocalWhisperProvider(
        config={"stt": {"model_path": "base", "device": "cuda", "compute_type": "float16"}},
        config_section="stt",
    )
    assert forced.device == "cpu"
    assert forced.compute_type == "int8"


def test_hf_ortho_uses_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """HFWhisperProvider must route device selection through resolve_compute_device.

    This test is intentionally hermetic against upstream test pollution. MC-384-Y/Z
    exposed that resolver tests can pass in isolation while failing in the full
    sweep if earlier tests leak a torch-CUDA stub or replace ``sys.modules['ai.device']``.
    Three independent defenses keep this assertion about HF ORTH device routing
    stable regardless of collection order:

      1. ``sys.modules['torch']`` stub — forces lazy torch CUDA detection to a
         known-False result even if a prior test installed a CUDA-available stub.
      2. ``_torch_cuda_available`` monkeypatch — exercises the canonical resolver hook.
      3. ``_resolve_auto`` monkeypatch — protects against stale module-dict references
         if an earlier test reloaded/replaced ``ai.device``.
    """
    torch_stub = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: False,
            device_count=lambda: 0,
        )
    )
    monkeypatch.setitem(sys.modules, "torch", torch_stub)

    from ai import device as device_module
    from ai.providers.hf_whisper import HFWhisperProvider

    monkeypatch.setattr(device_module, "_torch_cuda_available", lambda: False)
    monkeypatch.setattr(device_module, "_resolve_auto", lambda: "cpu")
    provider = HFWhisperProvider(config={"ortho": {"model": {"repo_id": "razhan/whisper-base-sdh"}}})

    assert provider.device == "cpu"
    assert provider._effective_device == "cpu"


def test_forced_align_resolve_device_defaults_to_unified_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai import forced_align

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(  # type: ignore[attr-defined]
        is_available=lambda: True,
        device_count=lambda: 1,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert forced_align.resolve_device(None) == "cuda"
    assert forced_align.resolve_device("cuda", allow_wsl_cuda=False) == "cpu"


def test_wav2vec2_runtime_options_default_allow_wsl_cuda_true() -> None:
    from ai.wav2vec2_runtime import resolve_wav2vec2_runtime_options

    options = resolve_wav2vec2_runtime_options(lambda: {"wav2vec2": {}})

    assert options.device is None
    assert options.allow_wsl_cuda is True


def test_parse_run_documents_device_env_defaults() -> None:
    text = Path("scripts/parse-run.sh").read_text(encoding="utf-8")

    assert "PARSE_COMPUTE_DEVICE=auto" in text
    assert "PARSE_STT_DEVICE=auto" in text
    assert "PARSE_ORTH_DEVICE=auto" in text
    assert "PARSE_IPA_DEVICE=auto" in text
