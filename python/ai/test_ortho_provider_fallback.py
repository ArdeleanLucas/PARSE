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


# --------------------------------------------------------------------------
# _collect_nvidia_wheel_bin_dirs — regression guard for the PEP-420
# namespace-package bug that silently disabled GPU inference in
# production (no DLL dirs registered → cublas fails mid-transcription
# → faster-whisper falls back to CPU). The helper is platform-agnostic
# so we can test it on every CI runner, not only Windows.
# --------------------------------------------------------------------------


def test_collect_nvidia_wheel_bin_dirs_iterates_namespace_path(tmp_path, monkeypatch):
    """The ``nvidia`` package installed by ``nvidia-cublas-cu12`` etc. is a
    PEP-420 namespace package — ``nvidia.__file__`` is ``None`` but
    ``nvidia.__path__`` enumerates its site-packages root(s). A previous
    revision used ``Path(nvidia.__file__).resolve().parent`` and silently
    failed (``TypeError``), meaning no DLL dirs got registered and
    faster-whisper fell back to CPU at the first cuBLAS call.
    """
    import types
    import sys as _sys
    from ai import provider as provider_module

    # Simulate how the nvidia-* wheels actually install: subpackage
    # directories under <site-packages>/nvidia/ each with a bin/ dir.
    fake_root = tmp_path / "site-packages" / "nvidia"
    (fake_root / "cublas" / "bin").mkdir(parents=True)
    (fake_root / "cudnn" / "bin").mkdir(parents=True)
    (fake_root / "cuda_runtime" / "bin").mkdir(parents=True)
    # Also drop a subpackage without a bin dir — must NOT be registered.
    (fake_root / "cusparse").mkdir()

    fake_nvidia = types.ModuleType("nvidia")
    fake_nvidia.__file__ = None  # the exact shape that used to crash
    fake_nvidia.__path__ = [str(fake_root)]
    monkeypatch.setitem(_sys.modules, "nvidia", fake_nvidia)

    dirs = provider_module._collect_nvidia_wheel_bin_dirs()

    names = {d.parent.name for d in dirs}
    assert names == {"cublas", "cudnn", "cuda_runtime"}, names


def test_ortho_section_defaults_vad_filter_off(tmp_path):
    """The ortho provider runs razhan full-file for full-waveform coverage.
    Silero VAD with stock defaults was dropping coverage to ~2 intervals
    on real recordings (vs 80+ from STT with tuned VAD params). Default
    must be **off** for ortho so razhan sees the entire audio."""
    provider = LocalWhisperProvider(
        config={"ortho": {"model_path": "C:/local/razhan-ct2"}},
        config_section="ortho",
        config_path=tmp_path / "ai_config.json",
    )
    assert provider.vad_filter is False


def test_stt_section_still_defaults_vad_filter_on(tmp_path):
    """STT's default is still VAD on (PR #135 rationale: avoids Whisper
    hallucinating through long silences). The ortho default change
    doesn't leak to other sections."""
    provider = LocalWhisperProvider(
        config={"stt": {"model_path": "C:/local/whisper-base"}},
        config_section="stt",
        config_path=tmp_path / "ai_config.json",
    )
    assert provider.vad_filter is True


def test_ortho_vad_filter_explicit_override_wins(tmp_path):
    """Users can still force VAD on for ortho via an explicit
    ``vad_filter: true`` in their config."""
    provider = LocalWhisperProvider(
        config={"ortho": {"model_path": "C:/local/razhan-ct2", "vad_filter": True}},
        config_section="ortho",
        config_path=tmp_path / "ai_config.json",
    )
    assert provider.vad_filter is True


def test_resolve_ai_config_explicit_arg_wins(tmp_path):
    from ai.provider import resolve_ai_config_path
    explicit = tmp_path / "my-config.json"
    explicit.write_text("{}")
    assert resolve_ai_config_path(explicit) == explicit.resolve()


def test_resolve_ai_config_env_var(tmp_path, monkeypatch):
    """``PARSE_AI_CONFIG`` env var is the operator escape hatch — takes
    precedence over every path-based lookup but the explicit arg."""
    from ai.provider import resolve_ai_config_path
    special = tmp_path / "special.json"
    special.write_text("{}")
    monkeypatch.setenv("PARSE_AI_CONFIG", str(special))
    assert resolve_ai_config_path() == special.resolve()


def test_resolve_ai_config_prefers_cwd_over_repo_path(tmp_path, monkeypatch):
    """The server runs with ``cwd = <project-workspace>`` — that's where
    the real ai_config.json lives. A prior revision only checked the
    repo path, which was empty on a fresh deploy, so providers silently
    fell back to defaults and every razhan/ortho run errored out with
    the HF-id model_path crash. Regression guard.
    """
    from ai.provider import resolve_ai_config_path
    monkeypatch.delenv("PARSE_AI_CONFIG", raising=False)
    cwd_cfg_dir = tmp_path / "config"
    cwd_cfg_dir.mkdir()
    cwd_cfg = cwd_cfg_dir / "ai_config.json"
    cwd_cfg.write_text("{}")
    monkeypatch.chdir(tmp_path)
    resolved = resolve_ai_config_path()
    assert resolved == cwd_cfg.resolve()


def test_resolve_ai_config_falls_back_to_repo_when_nothing_found(tmp_path, monkeypatch):
    from ai.provider import resolve_ai_config_path
    monkeypatch.delenv("PARSE_AI_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    resolved = resolve_ai_config_path()
    # Lands on repo-relative ai_config.json path (which may or may not
    # exist) — this lets the caller emit a clean "AI config not found"
    # warning with a stable path instead of a cwd-dependent one.
    assert resolved.name == "ai_config.json"
    assert resolved.parent.name == "config"


def test_collect_nvidia_wheel_bin_dirs_returns_empty_when_nvidia_absent(monkeypatch):
    """No nvidia wheels installed → empty list, no exception."""
    import sys as _sys
    from ai import provider as provider_module

    # Ensure ``import nvidia`` fails cleanly.
    monkeypatch.setitem(_sys.modules, "nvidia", None)

    assert provider_module._collect_nvidia_wheel_bin_dirs() == []

