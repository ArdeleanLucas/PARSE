"""Tests for the ortho→stt model_path fallback in LocalWhisperProvider.

Context: ``_DEFAULT_AI_CONFIG["ortho"]["model_path"]`` ships as
``razhan/whisper-base-sdh`` — a HuggingFace repo id. faster-whisper
cannot load HF Transformers checkpoints (it wants CTranslate2 format),
so passing the HF id straight through crashes with ``Unable to open
file 'model.bin'``. Meanwhile users who've already set up razhan for
STT have a local CT2 path in ``stt.model_path``. The fallback: when
``ortho.model_path`` is empty or looks like a HF repo id, reuse
``stt.model_path``.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.provider import LocalWhisperProvider, _looks_like_hf_repo_id


def test_hf_repo_id_classifier():
    """The helper that distinguishes HF repo ids from local paths."""
    assert _looks_like_hf_repo_id("razhan/whisper-base-sdh") is True
    assert _looks_like_hf_repo_id("openai/whisper-base") is True

    # Local paths — must NOT be treated as HF ids.
    assert _looks_like_hf_repo_id("C:/local/ortho-ct2") is False
    assert _looks_like_hf_repo_id("C:\\local\\ortho-ct2") is False
    assert _looks_like_hf_repo_id("/home/user/model") is False
    assert _looks_like_hf_repo_id("./model") is False
    assert _looks_like_hf_repo_id("..\\sibling") is False

    # Invalid / empty.
    assert _looks_like_hf_repo_id("") is False
    assert _looks_like_hf_repo_id("basename") is False
    assert _looks_like_hf_repo_id("org//empty") is False
    assert _looks_like_hf_repo_id("org/with/extra") is False


def test_ortho_with_empty_model_path_falls_back_to_stt(tmp_path):
    """Empty ortho.model_path + non-empty stt.model_path → ortho uses stt's."""
    provider = LocalWhisperProvider(
        config={
            "stt": {"model_path": "C:/local/razhan-ct2"},
            "ortho": {"model_path": ""},
        },
        config_section="ortho",
        config_path=tmp_path / "ai_config.json",
    )
    assert provider.model_path == "C:/local/razhan-ct2"


def test_ortho_with_hf_repo_id_falls_back_to_stt(tmp_path):
    """HuggingFace repo id in ortho.model_path → fall back to stt.model_path
    (the stock default ``razhan/whisper-base-sdh`` would otherwise crash
    at faster-whisper load time)."""
    provider = LocalWhisperProvider(
        config={
            "stt": {"model_path": "C:/local/razhan-ct2"},
            "ortho": {"model_path": "razhan/whisper-base-sdh"},
        },
        config_section="ortho",
        config_path=tmp_path / "ai_config.json",
    )
    assert provider.model_path == "C:/local/razhan-ct2"


def test_ortho_with_local_path_keeps_its_own(tmp_path):
    """Explicit local ortho.model_path must NOT be silently overridden —
    power users who've set up a different model for ortho deserve to
    have their choice respected."""
    provider = LocalWhisperProvider(
        config={
            "stt": {"model_path": "C:/local/stt-ct2"},
            "ortho": {"model_path": "C:/local/ortho-ct2"},
        },
        config_section="ortho",
        config_path=tmp_path / "ai_config.json",
    )
    assert provider.model_path == "C:/local/ortho-ct2"


def test_stt_section_is_never_touched_by_fallback(tmp_path):
    """The fallback logic is scoped to ortho. STT is unaffected even if
    its path is blank — the provider's own empty-path → 'base' fallback
    inside _load_whisper_model handles that downstream."""
    provider = LocalWhisperProvider(
        config={
            "stt": {"model_path": ""},
            "ortho": {"model_path": "C:/local/ortho-ct2"},
        },
        config_section="stt",
        config_path=tmp_path / "ai_config.json",
    )
    assert provider.model_path == ""
