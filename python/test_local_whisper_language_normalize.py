from __future__ import annotations

from ai.providers.local_whisper import _normalize_whisper_language


def test_normalize_whisper_language_preserves_empty_values() -> None:
    assert _normalize_whisper_language(None) is None
    assert _normalize_whisper_language("") == ""


def test_normalize_whisper_language_maps_razhan_sdh_aliases_to_fa() -> None:
    assert _normalize_whisper_language("sdh") == "fa"
    assert _normalize_whisper_language("SDH") == "fa"
    assert _normalize_whisper_language(" sdh ") == "fa"
    assert _normalize_whisper_language("sd") == "fa"


def test_normalize_whisper_language_preserves_other_codes() -> None:
    assert _normalize_whisper_language("fa") == "fa"
    assert _normalize_whisper_language("en") == "en"
    assert _normalize_whisper_language("ku") == "ku"
