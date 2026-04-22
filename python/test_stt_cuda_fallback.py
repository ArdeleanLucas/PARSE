"""Tests for cuBLAS / cuDNN runtime fallback in LocalWhisperProvider.

Covers the ``Library cublas64_12.dll is not found or cannot be loaded``
class of errors: when the requested CUDA backend can't initialise we want
STT to silently retry on CPU rather than block the entire pipeline. This
mirrors the user requirement: "when wav files are located within parse
workspace, it should be possible to trigger STT, IPA transcriptions, and
all tools".
"""
from __future__ import annotations

import pathlib
import sys
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import provider as provider_module
from ai.provider import (
    LocalWhisperProvider,
    _looks_like_cuda_runtime_failure,
    _register_cuda_dll_directories,
)


CUBLAS_ERROR = (
    "Library cublas64_12.dll is not found or cannot be loaded"
)


class _FakeWhisperModel:
    """Stand-in for faster_whisper.WhisperModel that mimics the GPU/CPU split.

    First ``raise_until`` constructions raise the configured CUDA error;
    after that, instances record the device/compute_type they were built
    with so the test can assert the fallback used "cpu" / "int8".
    """

    raise_until: int = 0
    instances: List["_FakeWhisperModel"] = []

    def __init__(self, model_source: str, device: str, compute_type: str) -> None:
        if _FakeWhisperModel.raise_until > 0:
            _FakeWhisperModel.raise_until -= 1
            raise RuntimeError(CUBLAS_ERROR)
        self.model_source = model_source
        self.device = device
        self.compute_type = compute_type
        _FakeWhisperModel.instances.append(self)


def _install_fake_whisper(monkeypatch, *, raise_until: int) -> None:
    _FakeWhisperModel.raise_until = raise_until
    _FakeWhisperModel.instances = []

    class _FakeFasterWhisperModule:
        WhisperModel = _FakeWhisperModel

    monkeypatch.setitem(sys.modules, "faster_whisper", _FakeFasterWhisperModule)


def test_looks_like_cuda_runtime_failure_matches_cublas_dll_error() -> None:
    assert _looks_like_cuda_runtime_failure(CUBLAS_ERROR)
    assert _looks_like_cuda_runtime_failure("CUDA driver version is insufficient")
    assert _looks_like_cuda_runtime_failure("Could not load library libcudnn.so.8")
    assert not _looks_like_cuda_runtime_failure("model.bin: file not found")
    assert not _looks_like_cuda_runtime_failure("")


def test_register_cuda_dll_directories_is_idempotent_and_safe_off_windows() -> None:
    # Reset the cache so the first call actually runs.
    provider_module._CUDA_DLL_DIRS_REGISTERED = None  # type: ignore[attr-defined]
    _register_cuda_dll_directories()
    first = provider_module._CUDA_DLL_DIRS_REGISTERED  # type: ignore[attr-defined]
    # Second invocation should be a no-op (cache flag retained).
    _register_cuda_dll_directories()
    assert provider_module._CUDA_DLL_DIRS_REGISTERED is first


def test_cuda_runtime_failure_falls_back_to_cpu(monkeypatch) -> None:
    _install_fake_whisper(monkeypatch, raise_until=1)

    provider_module._CUDA_DLL_DIRS_REGISTERED = True  # type: ignore[attr-defined]

    provider = LocalWhisperProvider(
        config={
            "stt": {
                "model_path": "tiny",
                "device": "cuda",
                "compute_type": "float16",
            }
        }
    )
    model = provider._load_whisper_model()

    assert isinstance(model, _FakeWhisperModel)
    assert model.device == "cpu"
    assert model.compute_type == "int8"
    # Provider records the realised runtime separately from the requested
    # device so other consumers that read self.device still see the user's
    # intent. Status payloads / loaders should prefer _effective_device.
    assert provider._effective_device == "cpu"
    assert provider._effective_compute_type == "int8"


def test_non_cuda_failure_is_re_raised_without_cpu_fallback(monkeypatch) -> None:
    class _FailingFasterWhisperModule:
        @staticmethod
        def WhisperModel(model_source, device, compute_type):  # noqa: N802
            raise RuntimeError("model.bin: file not found")

    monkeypatch.setitem(sys.modules, "faster_whisper", _FailingFasterWhisperModule)
    provider_module._CUDA_DLL_DIRS_REGISTERED = True  # type: ignore[attr-defined]

    provider = LocalWhisperProvider(
        config={
            "stt": {
                "model_path": "tiny",
                "device": "cuda",
                "compute_type": "float16",
            }
        }
    )

    try:
        provider._load_whisper_model()
    except RuntimeError as exc:
        assert "file not found" in str(exc)
    else:
        raise AssertionError("expected non-CUDA failure to propagate")


def test_cpu_device_failure_does_not_attempt_cpu_fallback(monkeypatch) -> None:
    """If the user explicitly asked for CPU and it failed, we shouldn't
    silently swallow that into a second CPU attempt."""
    _install_fake_whisper(monkeypatch, raise_until=1)
    provider_module._CUDA_DLL_DIRS_REGISTERED = True  # type: ignore[attr-defined]

    provider = LocalWhisperProvider(
        config={"stt": {"model_path": "tiny", "device": "cpu", "compute_type": "int8"}}
    )

    try:
        provider._load_whisper_model()
    except RuntimeError as exc:
        assert CUBLAS_ERROR in str(exc) or "cublas" in str(exc).lower()
    else:
        raise AssertionError("expected CPU init failure to propagate")
