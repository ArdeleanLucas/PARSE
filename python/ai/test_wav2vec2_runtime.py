from __future__ import annotations

from ai.wav2vec2_runtime import resolve_wav2vec2_runtime_options


def test_resolve_wav2vec2_runtime_options_plumbs_device_and_allow_wsl_cuda() -> None:
    options = resolve_wav2vec2_runtime_options(
        lambda: {"wav2vec2": {"device": "cuda", "allow_wsl_cuda": True}}
    )

    assert options.device == "cuda"
    assert options.allow_wsl_cuda is True


def test_resolve_wav2vec2_runtime_options_force_cpu_wins_over_device() -> None:
    options = resolve_wav2vec2_runtime_options(
        lambda: {"wav2vec2": {"device": "cuda", "force_cpu": True, "allow_wsl_cuda": True}}
    )

    assert options.device == "cpu"
    assert options.allow_wsl_cuda is True


def test_resolve_wav2vec2_runtime_options_degrades_safe_on_config_failure() -> None:
    def broken_config():
        raise RuntimeError("bad config")

    options = resolve_wav2vec2_runtime_options(broken_config)

    assert options.device is None
    assert options.allow_wsl_cuda is True
