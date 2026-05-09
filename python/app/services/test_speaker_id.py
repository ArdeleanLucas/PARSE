"""Tests for ``app.services.speaker_id.normalize_speaker_id``.

Pin error messages so the HTTP route and the chat-tool wrapper, which
both delegate here, can rely on stable wording.
"""
from __future__ import annotations

import pytest

from app.services.speaker_id import normalize_speaker_id


def test_strips_whitespace_and_returns_value() -> None:
    assert normalize_speaker_id("  Saha01  ") == "Saha01"


def test_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="speaker is required"):
        normalize_speaker_id("")
    with pytest.raises(ValueError, match="speaker is required"):
        normalize_speaker_id("   ")
    with pytest.raises(ValueError, match="speaker is required"):
        normalize_speaker_id(None)


def test_rejects_dot_dotdot() -> None:
    with pytest.raises(ValueError, match="Invalid speaker id"):
        normalize_speaker_id(".")
    with pytest.raises(ValueError, match="Invalid speaker id"):
        normalize_speaker_id("..")


def test_rejects_null_byte() -> None:
    with pytest.raises(ValueError, match="speaker contains an invalid null byte"):
        normalize_speaker_id("Saha\x0001")


def test_rejects_path_separators() -> None:
    with pytest.raises(ValueError, match="speaker must not contain path separators"):
        normalize_speaker_id("Saha/01")
    with pytest.raises(ValueError, match="speaker must not contain path separators"):
        normalize_speaker_id("Saha\\01")


def test_rejects_too_long() -> None:
    long = "A" * 201
    with pytest.raises(ValueError, match="speaker is too long"):
        normalize_speaker_id(long)


def test_accepts_201_chars_only_after_strip() -> None:
    # 200 chars is valid, 201 raises.
    assert normalize_speaker_id("A" * 200) == "A" * 200


def test_coerces_non_string_via_str() -> None:
    assert normalize_speaker_id(12345) == "12345"
