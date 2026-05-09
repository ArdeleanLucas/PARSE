from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from server_routes.lexeme_rerun import _run_ipa_interval, _run_ortho_interval


def _options(device: str | None, allow_wsl_cuda: bool):
    return type("Options", (), {"device": device, "allow_wsl_cuda": allow_wsl_cuda})()


def test_run_ortho_interval_calls_renamed_helper(monkeypatch) -> None:
    import ai.stt_pipeline as stt_pipeline

    with pytest.raises(ImportError):
        from ai.stt_pipeline import run_stt_on_interval  # noqa: F401

    calls: list[dict[str, Any]] = []

    def fake_run_ortho_on_interval(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "ریشەم"

    monkeypatch.setattr(stt_pipeline, "run_ortho_on_interval", fake_run_ortho_on_interval)
    monkeypatch.setattr("server_routes.lexeme_rerun.resolve_wav2vec2_runtime_options", lambda: _options("cuda", True))

    result = _run_ortho_interval(audio_path=Path("/tmp/x.wav"), start=1.0, end=2.0, language="sdh")

    assert result == "ریشەم"
    assert len(calls) == 1
    assert calls[0]["audio_path"] == Path("/tmp/x.wav")
    assert calls[0]["start"] == 1.0
    assert calls[0]["end"] == 2.0
    assert calls[0]["language"] == "sdh"
    assert "config_path" in calls[0]
    assert calls[0]["device"] == "cuda"
    assert calls[0]["allow_wsl_cuda"] is True


def test_run_ipa_interval_calls_transcribe_intervals_with_single_interval(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_transcribe_intervals(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [{"start": 1.0, "end": 2.0, "ipa": " ʃ "}]

    monkeypatch.setattr("ai.ipa_transcribe.transcribe_intervals", fake_transcribe_intervals)
    monkeypatch.setattr("server_routes.lexeme_rerun.resolve_wav2vec2_runtime_options", lambda: _options("cuda", True))

    result = _run_ipa_interval(audio_path=Path("/tmp/x.wav"), start=1.0, end=2.0, language="sdh")

    assert result == "ʃ"
    assert calls == [
        {
            "audio_path": Path("/tmp/x.wav"),
            "intervals": [{"start": 1.0, "end": 2.0}],
            "device": "cuda",
            "allow_wsl_cuda": True,
        }
    ]
    assert "language" not in calls[0]


def test_run_ipa_interval_force_cpu_overrides_config_device(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_transcribe_intervals(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [{"start": 1.0, "end": 2.0, "ipa": "ʃ"}]

    monkeypatch.setattr("ai.ipa_transcribe.transcribe_intervals", fake_transcribe_intervals)
    monkeypatch.setattr("server_routes.lexeme_rerun.resolve_wav2vec2_runtime_options", lambda: _options("cpu", True))

    assert _run_ipa_interval(audio_path=Path("/tmp/x.wav"), start=1.0, end=2.0) == "ʃ"
    assert calls[0]["device"] == "cpu"
    assert calls[0]["allow_wsl_cuda"] is True


def test_run_ipa_interval_falls_back_when_config_load_fails(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_transcribe_intervals(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [{"start": 1.0, "end": 2.0, "ipa": "ʃ"}]

    monkeypatch.setattr("ai.ipa_transcribe.transcribe_intervals", fake_transcribe_intervals)

    def broken_options() -> Any:
        raise RuntimeError("bad config")

    monkeypatch.setattr("server_routes.lexeme_rerun.resolve_wav2vec2_runtime_options", broken_options)

    assert _run_ipa_interval(audio_path=Path("/tmp/x.wav"), start=1.0, end=2.0) == "ʃ"
    assert calls[0]["device"] is None
    assert calls[0]["allow_wsl_cuda"] is False
