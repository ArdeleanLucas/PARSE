"""Regression tests for tag-filter rerun interval wrapper contracts."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, get_type_hints

import pytest

# Prime chat_tools before importing tag_filter_tools; this mirrors the existing
# tag-filter tests and avoids the known partial-import cycle during collection.
import ai.chat_tools  # noqa: F401
from ai.provider import ConfidenceScore
from ai.tools import tag_filter_tools


def test_tag_filter_tools_run_ortho_interval_wrapper_returns_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {"text": "یەک", "confidence": ConfidenceScore(value=0.5, source="avg_logprob", n_tokens=4)}

    def fake_impl(*, audio_path: Path, start: float, end: float, language: str | None = None) -> dict[str, Any]:
        _ = (audio_path, start, end, language)
        return expected

    from server_routes import lexeme_rerun

    monkeypatch.setattr(lexeme_rerun, "_run_ortho_interval", fake_impl)

    result = tag_filter_tools._run_ortho_interval(tmp_path / "audio.wav", 1.0, 1.2, "sdh")

    assert get_type_hints(tag_filter_tools._run_ortho_interval)["return"] == dict[str, Any]
    assert isinstance(result, Mapping)
    assert result["text"] == "یەک"
    assert isinstance(result.get("confidence"), ConfidenceScore)


def test_tag_filter_tools_run_ipa_interval_wrapper_still_returns_str(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server_routes import lexeme_rerun

    monkeypatch.setattr(
        lexeme_rerun,
        "_run_ipa_interval",
        lambda *, audio_path, start, end, language=None: "ʃ",
    )

    result = tag_filter_tools._run_ipa_interval(tmp_path / "audio.wav", 1.0, 1.2)

    assert get_type_hints(tag_filter_tools._run_ipa_interval)["return"] is str
    assert isinstance(result, str)
    assert result == "ʃ"
