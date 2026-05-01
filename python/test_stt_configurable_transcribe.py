"""Tests for LocalWhisperProvider's configurable transcribe() path.

Ensures:
  - empty ``stt.language`` maps to ``language=None`` (auto-detect), not "".
  - ``stt.vad_filter`` / ``stt.vad_parameters`` / ``stt.task`` / ``stt.beam_size``
    flow through to ``WhisperModel.transcribe()``.
  - Omitting ``stt.vad_parameters`` (or passing {}) does NOT send
    ``vad_parameters`` to faster-whisper (so its Silero defaults apply).

Context: default was ``language="sd"`` (Sindhi) + hard-coded
``vad_filter=True`` with no way to tune. Probing real Southern Kurdish
audio showed "sd" forces whisper to hallucinate garbage; auto-detect
lands on "fa" and produces coherent text. This test guards the new
config surface so we don't regress back to the hard-coded behavior.
"""
from __future__ import annotations

import pathlib
import sys
import types
from typing import Any, Dict, List, Tuple

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import provider as provider_module
from ai.provider import LocalWhisperProvider


class _StubSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = -0.3


class _StubInfo:
    def __init__(self, duration: float = 10.0) -> None:
        self.duration = duration


class _StubWhisperModel:
    """Records every transcribe() call so tests can assert on kwargs."""

    last_call: Dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def transcribe(self, audio: str, **kwargs: Any) -> Tuple[List[_StubSegment], _StubInfo]:
        type(self).last_call = {"audio": audio, **kwargs}
        return iter([_StubSegment(0.0, 1.0, "ok")]), _StubInfo()


def _make_provider(tmp_path: pathlib.Path, stt_config: Dict[str, Any],
                   monkeypatch: Any) -> LocalWhisperProvider:
    """Instantiate LocalWhisperProvider with the given stt config,
    bypassing real WhisperModel loading."""
    _StubWhisperModel.last_call = {}
    # Stub the WhisperModel import inside _load_whisper_model.
    monkeypatch.setattr(
        provider_module, "_register_cuda_dll_directories", lambda: None, raising=False
    )

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=_StubWhisperModel),
    )

    provider = LocalWhisperProvider(
        config={"stt": stt_config},
        config_path=tmp_path / "ai_config.json",
    )
    return provider


def _make_audio(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "clip.wav"
    p.write_bytes(b"RIFF    WAVEfmt ")  # faux header; provider only stats existence
    return p


def _make_ortho_provider(
    tmp_path: pathlib.Path,
    ortho_config: Dict[str, Any],
    monkeypatch: Any,
) -> LocalWhisperProvider:
    _StubWhisperModel.last_call = {}
    monkeypatch.setattr(
        provider_module, "_register_cuda_dll_directories", lambda: None, raising=False
    )
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=_StubWhisperModel),
    )

    ortho_model_dir = tmp_path / "razhan-ct2"
    ortho_model_dir.mkdir(exist_ok=True)
    config = {
        "language": "sd",
        "model_path": str(ortho_model_dir),
        **ortho_config,
    }
    return LocalWhisperProvider(
        config={"ortho": config},
        config_path=tmp_path / "ai_config.json",
        config_section="ortho",
    )


def test_empty_language_becomes_none_for_auto_detect(tmp_path, monkeypatch):
    """language="" in config must translate to language=None when calling
    faster-whisper, otherwise the decoder would error. This is the
    regression guard for the old default of "sd" (Sindhi) producing
    garbage on Kurdish audio — auto-detect is now the default."""
    provider = _make_provider(tmp_path, {"language": ""}, monkeypatch)
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["language"] is None


def test_explicit_language_is_passed_through(tmp_path, monkeypatch):
    """When the user explicitly sets a language code (in config or per-call),
    we forward it to whisper unchanged."""
    provider = _make_provider(tmp_path, {"language": "fa"}, monkeypatch)
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["language"] == "fa"

    # Per-call override wins over config.
    provider.transcribe(_make_audio(tmp_path), language="ar")
    assert _StubWhisperModel.last_call["language"] == "ar"


def test_vad_parameters_forwarded_when_populated(tmp_path, monkeypatch):
    """Non-empty vad_parameters dict reaches faster-whisper verbatim."""
    stt = {
        "language": "fa",
        "vad_filter": True,
        "vad_parameters": {
            "min_silence_duration_ms": 500,
            "threshold": 0.35,
        },
    }
    provider = _make_provider(tmp_path, stt, monkeypatch)
    provider.transcribe(_make_audio(tmp_path))
    call = _StubWhisperModel.last_call
    assert call["vad_filter"] is True
    assert call["vad_parameters"] == {
        "min_silence_duration_ms": 500,
        "threshold": 0.35,
    }


def test_empty_vad_parameters_omitted_so_silero_defaults_apply(tmp_path, monkeypatch):
    """The config's default is `vad_parameters: {}` meaning "use faster-
    whisper's built-in Silero defaults". We verify that an empty dict is
    NOT forwarded — otherwise it would override Silero with a broken
    empty config."""
    provider = _make_provider(tmp_path, {"vad_filter": True, "vad_parameters": {}}, monkeypatch)
    provider.transcribe(_make_audio(tmp_path))
    call = _StubWhisperModel.last_call
    assert call["vad_filter"] is True
    assert "vad_parameters" not in call, call


def test_vad_disabled_does_not_forward_parameters(tmp_path, monkeypatch):
    """If vad_filter=False, vad_parameters is meaningless — we should not
    pass it even when the user configured values."""
    stt = {
        "vad_filter": False,
        "vad_parameters": {"threshold": 0.35},
    }
    provider = _make_provider(tmp_path, stt, monkeypatch)
    provider.transcribe(_make_audio(tmp_path))
    call = _StubWhisperModel.last_call
    assert call["vad_filter"] is False
    assert "vad_parameters" not in call, call


def test_task_and_beam_size_forwarded(tmp_path, monkeypatch):
    provider = _make_provider(
        tmp_path,
        {"task": "translate", "beam_size": 3},
        monkeypatch,
    )
    provider.transcribe(_make_audio(tmp_path))
    call = _StubWhisperModel.last_call
    assert call["task"] == "translate"
    assert call["beam_size"] == 3


def test_invalid_task_falls_back_to_transcribe(tmp_path, monkeypatch):
    provider = _make_provider(
        tmp_path, {"task": "garbage-value"}, monkeypatch
    )
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["task"] == "transcribe"


def test_invalid_beam_size_falls_back_to_five(tmp_path, monkeypatch):
    provider = _make_provider(
        tmp_path, {"beam_size": "not-a-number"}, monkeypatch
    )
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["beam_size"] == 5


# ---------------------------------------------------------------------------
# ORTH repetition-cascade guard (2026-04-23)
# ---------------------------------------------------------------------------


def test_stt_defaults_condition_on_previous_text_true(tmp_path, monkeypatch):
    """STT preserves Whisper's default — cross-segment conditioning ON."""
    provider = _make_provider(tmp_path, {}, monkeypatch)
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["condition_on_previous_text"] is True


def test_stt_defaults_compression_ratio_threshold_24(tmp_path, monkeypatch):
    """STT uses Whisper's default 2.4 compression-ratio threshold."""
    provider = _make_provider(tmp_path, {}, monkeypatch)
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["compression_ratio_threshold"] == 2.4


def test_condition_on_previous_text_override(tmp_path, monkeypatch):
    """User can set condition_on_previous_text=False on STT too."""
    provider = _make_provider(
        tmp_path, {"condition_on_previous_text": False}, monkeypatch
    )
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["condition_on_previous_text"] is False


def test_compression_ratio_threshold_override(tmp_path, monkeypatch):
    provider = _make_provider(
        tmp_path, {"compression_ratio_threshold": 1.5}, monkeypatch
    )
    provider.transcribe(_make_audio(tmp_path))
    assert _StubWhisperModel.last_call["compression_ratio_threshold"] == 1.5


def test_compression_ratio_threshold_null_disables_it(tmp_path, monkeypatch):
    """Passing None in config removes the kwarg entirely — Whisper then
    falls back to its library default and never rejects on this metric."""
    provider = _make_provider(
        tmp_path, {"compression_ratio_threshold": None}, monkeypatch
    )
    provider.transcribe(_make_audio(tmp_path))
    assert "compression_ratio_threshold" not in _StubWhisperModel.last_call


def test_legacy_ortho_faster_whisper_rejects_hf_default_model_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        provider_module, "_register_cuda_dll_directories", lambda: None, raising=False
    )

    with pytest.raises(ValueError, match=r"looks like a HuggingFace repo id"):
        LocalWhisperProvider(
            config={"ortho": {"language": "sd"}},
            config_path=tmp_path / "ai_config.json",
            config_section="ortho",
        )


def test_ortho_section_defaults_cascade_guard(tmp_path, monkeypatch):
    """ORTH's defaults stop the repetition cascade that truncated Fail02
    at 06:31 on 2026-04-23:
      - condition_on_previous_text=False (critical — the cascade fix)
      - vad_filter=True with tuned Silero params (gate silence)
      - compression_ratio_threshold=1.8 (reject repetition earlier)
    """
    ortho_provider = _make_ortho_provider(tmp_path, {}, monkeypatch)
    ortho_provider.transcribe(_make_audio(tmp_path))
    call = _StubWhisperModel.last_call
    assert call["condition_on_previous_text"] is False
    assert call["vad_filter"] is True
    assert call["vad_parameters"] == {
        "min_silence_duration_ms": 500,
        "threshold": 0.35,
    }
    assert call["compression_ratio_threshold"] == 1.8


def test_ortho_explicit_override_beats_defaults(tmp_path, monkeypatch):
    """Config override wins over the ORTH-specific defaults — so a user
    who intentionally wants the old permissive behaviour can restore it."""
    ortho_provider = _make_ortho_provider(
        tmp_path,
        {
            "vad_filter": False,
            "condition_on_previous_text": True,
            "compression_ratio_threshold": 2.4,
        },
        monkeypatch,
    )
    ortho_provider.transcribe(_make_audio(tmp_path))
    call = _StubWhisperModel.last_call
    assert call["vad_filter"] is False
    assert call["condition_on_previous_text"] is True
    assert call["compression_ratio_threshold"] == 2.4
