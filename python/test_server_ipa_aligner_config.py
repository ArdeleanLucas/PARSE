from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest

import server
from ai import forced_align, provider


class _FakeAligner:
    device = "cuda"
    vocab = {"a": 1}


@pytest.fixture(autouse=True)
def _reset_ipa_aligner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_IPA_ALIGNER", None)
    monkeypatch.setattr(server, "_compute_checkpoint", lambda *args, **kwargs: None)
    monkeypatch.setattr(forced_align, "_is_wsl", lambda: False)


def test_get_ipa_aligner_reads_wav2vec2_config_from_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        provider,
        "load_ai_config",
        lambda: {"wav2vec2": {"device": "cuda", "allow_wsl_cuda": True}},
    )

    def fake_load(*, device=None, allow_wsl_cuda: bool = False):
        calls.append({"device": device, "allow_wsl_cuda": allow_wsl_cuda})
        return _FakeAligner()

    monkeypatch.setattr(forced_align.Aligner, "load", staticmethod(fake_load))

    assert server._get_ipa_aligner() is not None

    assert calls == [{"device": "cuda", "allow_wsl_cuda": True}]


def test_get_ipa_aligner_falls_back_when_ai_config_load_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fail_load_ai_config():
        raise RuntimeError("config unavailable")

    monkeypatch.setattr(provider, "load_ai_config", fail_load_ai_config)

    def fake_load(*, device=None, allow_wsl_cuda: bool = False):
        calls.append({"device": device, "allow_wsl_cuda": allow_wsl_cuda})
        return _FakeAligner()

    monkeypatch.setattr(forced_align.Aligner, "load", staticmethod(fake_load))

    assert server._get_ipa_aligner() is not None

    assert calls == [{"device": None, "allow_wsl_cuda": False}]


def test_get_ipa_aligner_force_cpu_overrides_configured_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        provider,
        "load_ai_config",
        lambda: {"wav2vec2": {"device": "cuda", "force_cpu": True, "allow_wsl_cuda": True}},
    )

    def fake_load(*, device=None, allow_wsl_cuda: bool = False):
        calls.append({"device": device, "allow_wsl_cuda": allow_wsl_cuda})
        return _FakeAligner()

    monkeypatch.setattr(forced_align.Aligner, "load", staticmethod(fake_load))

    assert server._get_ipa_aligner() is not None

    assert calls == [{"device": "cpu", "allow_wsl_cuda": True}]
