"""Unified device resolution for PARSE compute stages.

Precedence (highest first):
  1. PARSE_{STAGE}_DEVICE env var
  2. PARSE_COMPUTE_DEVICE env var
  3. config_device argument (caller's section config["device"])
  4. section_default (typically "auto")

Accepted values at every level: "auto" | "cpu" | "cuda" | "cuda:N".
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger("parse.device")

_CUDA_DEVICE_RE = re.compile(r"^cuda(?::\d+)?$")
_TRUTHY = {"1", "true", "yes", "y", "on"}


def _torch_cuda_available() -> bool:
    """Return whether PyTorch currently reports at least one CUDA device.

    Torch is imported lazily so lightweight server/test environments can import
    this module without installing the GPU stack.
    """

    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available()) and int(torch.cuda.device_count()) > 0
    except Exception:
        return False


def _stt_force_cpu_env_set() -> bool:
    """Backwards compat: PARSE_STT_FORCE_CPU=1 forces STT to CPU."""

    raw = os.environ.get("PARSE_STT_FORCE_CPU", "").strip().lower()
    return raw in _TRUTHY


def _normalize_device_value(stage: str, raw: object) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if not value:
        return None
    if value in {"auto", "cpu"} or _CUDA_DEVICE_RE.match(value):
        return value
    logger.warning(
        "[device] %s invalid device=%r; falling back to auto",
        stage.upper() or "COMPUTE",
        value,
    )
    return "auto"


def _resolve_auto() -> str:
    return "cuda" if _torch_cuda_available() else "cpu"


def resolve_compute_device(
    stage: str,
    *,
    config_device: Optional[str] = None,
    section_default: str = "auto",
) -> str:
    """Resolve the compute device for a PARSE stage.

    ``stage`` is normally one of ``stt``, ``orth``, or ``ipa``. Unknown stage
    names still get the global/env/config/default precedence, but only the STT
    stage honors the legacy ``PARSE_STT_FORCE_CPU`` escape hatch.
    """

    stage_upper = str(stage or "").strip().upper()
    if stage_upper == "STT" and _stt_force_cpu_env_set():
        return "cpu"

    candidates = [
        os.environ.get(f"PARSE_{stage_upper}_DEVICE") if stage_upper else None,
        os.environ.get("PARSE_COMPUTE_DEVICE"),
        config_device,
        section_default,
    ]
    chosen = next(
        (
            normalized
            for raw in candidates
            for normalized in [_normalize_device_value(stage_upper, raw)]
            if normalized is not None
        ),
        "auto",
    )

    if chosen == "auto":
        resolved = _resolve_auto()
        logger.info("[device] %s resolved auto -> %s", stage_upper or "COMPUTE", resolved)
        return resolved
    if chosen == "cpu":
        return "cpu"
    if chosen.startswith("cuda"):
        if _torch_cuda_available():
            return chosen
        logger.warning(
            "[device] %s requested device=%r but torch.cuda unavailable; falling back to cpu",
            stage_upper or "COMPUTE",
            chosen,
        )
        return "cpu"
    # Defensive fallback for future edits that bypass _normalize_device_value.
    return _resolve_auto()
