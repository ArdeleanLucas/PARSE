"""Tests for ``app.services.audio_paths.pipeline_audio_path_for_speaker``.

Covers the fallback chain that mirrors Lane A's HTTP route — the chat
tool layer (PR #328) regressed because it hardcoded ``working.wav``;
this helper is the shared resolver both callers now use.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

import pytest

from app.services.audio_paths import pipeline_audio_path_for_speaker


def _writable_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFFWAVEfake")
    return path


def test_returns_normalized_working_when_present(tmp_path: Path) -> None:
    speaker = "Saha01"
    raw = _writable_wav(tmp_path / "audio" / "raw" / "Saha01.wav")
    normalized = _writable_wav(tmp_path / "audio" / "working" / speaker / "Saha01.wav")

    def reader(_spk: str) -> Mapping[str, Any]:
        return {"source_audio": "audio/raw/Saha01.wav"}

    resolved = pipeline_audio_path_for_speaker(
        speaker,
        tmp_path,
        read_annotation_record=reader,
    )
    assert resolved == normalized
    assert resolved != raw


def test_falls_back_to_source_when_normalized_absent(tmp_path: Path) -> None:
    speaker = "Saha01"
    raw = _writable_wav(tmp_path / "audio" / "raw" / "Saha01.wav")
    # No normalized working copy on disk.

    def reader(_spk: str) -> Mapping[str, Any]:
        return {"source_audio": "audio/raw/Saha01.wav"}

    resolved = pipeline_audio_path_for_speaker(
        speaker,
        tmp_path,
        read_annotation_record=reader,
    )
    assert resolved == raw


def test_raises_when_neither_normalized_nor_source_exists(tmp_path: Path) -> None:
    speaker = "Saha01"

    def reader(_spk: str) -> Mapping[str, Any]:
        return {"source_audio": "audio/raw/Saha01.wav"}

    with pytest.raises(FileNotFoundError):
        pipeline_audio_path_for_speaker(
            speaker,
            tmp_path,
            read_annotation_record=reader,
        )


def test_raises_runtime_when_annotation_missing(tmp_path: Path) -> None:
    def reader(_spk: str) -> Optional[Mapping[str, Any]]:
        return None

    with pytest.raises(RuntimeError, match="No annotation found"):
        pipeline_audio_path_for_speaker(
            "Saha01",
            tmp_path,
            read_annotation_record=reader,
        )


def test_raises_runtime_when_source_audio_missing_from_record(tmp_path: Path) -> None:
    def reader(_spk: str) -> Mapping[str, Any]:
        return {"speaker": "Saha01"}

    with pytest.raises(RuntimeError, match="No source_audio on annotation"):
        pipeline_audio_path_for_speaker(
            "Saha01",
            tmp_path,
            read_annotation_record=reader,
        )


def test_consults_primary_source_wav_lookup_when_record_has_no_source(tmp_path: Path) -> None:
    speaker = "Saha01"
    raw = _writable_wav(tmp_path / "audio" / "raw" / "Saha01.wav")

    def reader(_spk: str) -> Mapping[str, Any]:
        return {}  # exists, but empty

    def primary(spk: str) -> str:
        assert spk == speaker
        return "audio/raw/Saha01.wav"

    resolved = pipeline_audio_path_for_speaker(
        speaker,
        tmp_path,
        read_annotation_record=reader,
        primary_source_wav_for_speaker=primary,
    )
    assert resolved == raw


def test_record_source_audio_takes_precedence_over_primary_lookup(tmp_path: Path) -> None:
    speaker = "Saha01"
    record_raw = _writable_wav(tmp_path / "audio" / "raw" / "Record.wav")
    _writable_wav(tmp_path / "audio" / "raw" / "Index.wav")

    def reader(_spk: str) -> Mapping[str, Any]:
        return {"source_audio": "audio/raw/Record.wav"}

    def primary(_spk: str) -> str:
        return "audio/raw/Index.wav"

    resolved = pipeline_audio_path_for_speaker(
        speaker,
        tmp_path,
        read_annotation_record=reader,
        primary_source_wav_for_speaker=primary,
    )
    assert resolved == record_raw


def test_path_traversal_escape_raises(tmp_path: Path) -> None:
    def reader(_spk: str) -> Mapping[str, Any]:
        return {"source_audio": "../escape.wav"}

    with pytest.raises(ValueError, match="escapes project root"):
        pipeline_audio_path_for_speaker(
            "Saha01",
            tmp_path,
            read_annotation_record=reader,
        )


def test_source_wav_alias_is_honored(tmp_path: Path) -> None:
    speaker = "Saha01"
    raw = _writable_wav(tmp_path / "audio" / "raw" / "Saha01.wav")

    def reader(_spk: str) -> Mapping[str, Any]:
        # Legacy field name still recognized by the HTTP route.
        return {"source_wav": "audio/raw/Saha01.wav"}

    resolved = pipeline_audio_path_for_speaker(
        speaker,
        tmp_path,
        read_annotation_record=reader,
    )
    assert resolved == raw
