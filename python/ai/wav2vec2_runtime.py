"""Shared wav2vec2 runtime option resolution for PARSE IPA/forced-align callsites."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .provider import load_ai_config


@dataclass(frozen=True)
class Wav2Vec2RuntimeOptions:
    """Resolved wav2vec2 options passed to ``Aligner.load``.

    This mirrors ``server._get_ipa_aligner``: ``force_cpu`` wins by setting
    device to ``"cpu"``; otherwise the configured ``device`` is forwarded (or
    ``None`` for forced_align auto-resolution), and WSL CUDA remains opt-in via
    ``allow_wsl_cuda is True``.
    """

    device: Optional[str]
    allow_wsl_cuda: bool


def resolve_wav2vec2_runtime_options(
    config_loader: Callable[[], Mapping[str, Any]] = load_ai_config,
) -> Wav2Vec2RuntimeOptions:
    """Resolve workspace-aware wav2vec2 device options safely.

    Config read failures degrade to the pre-existing conservative behavior:
    no explicit device and WSL CUDA disabled.
    """

    try:
        config = config_loader()
        wav2vec2 = config.get("wav2vec2", {}) if isinstance(config, Mapping) else {}
        if not isinstance(wav2vec2, Mapping):
            wav2vec2 = {}
        if wav2vec2.get("force_cpu"):
            device: Optional[str] = "cpu"
        else:
            raw_device = wav2vec2.get("device")
            device = str(raw_device).strip() if raw_device is not None and str(raw_device).strip() else None
        allow_wsl_cuda = wav2vec2.get("allow_wsl_cuda") is True
        return Wav2Vec2RuntimeOptions(device=device, allow_wsl_cuda=allow_wsl_cuda)
    except Exception:
        return Wav2Vec2RuntimeOptions(device=None, allow_wsl_cuda=False)
