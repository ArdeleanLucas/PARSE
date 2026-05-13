"""STT cache contract tests: cache persists flat segments, never chunks[]."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _bind_tmp_stt_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from server_routes import annotate

    monkeypatch.setattr(annotate._server, "_project_root", lambda: tmp_path, raising=False)
    monkeypatch.setattr(annotate._server, "_stt_cache_path", annotate._stt_cache_path, raising=False)
    return annotate


def test_write_stt_cache_emits_flat_segment_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    annotate = _bind_tmp_stt_cache(monkeypatch, tmp_path)
    segments = [
        {"start": 0.0, "end": 5.0, "text": "hello", "confidence": 0.9, "words": []},
        {"start": 5.0, "end": 10.0, "text": "world", "confidence": 0.8, "words": []},
    ]

    annotate._write_stt_cache("TestSpk", "/tmp/test.wav", "ku", segments)

    cache_file = tmp_path / "coarse_transcripts" / "TestSpk.json"
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"speaker", "source_wav", "language", "segments"}
    assert "chunks" not in payload
    assert "chunk_results" not in payload
    assert isinstance(payload["segments"], list)
    assert payload["segments"] == segments
    assert all(isinstance(segment, dict) and "start" in segment for segment in payload["segments"])


def test_write_stt_cache_segments_have_absolute_timestamps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    annotate = _bind_tmp_stt_cache(monkeypatch, tmp_path)
    segments = [
        {"start": float(idx * 240), "end": float(idx * 240 + 4), "text": f"segment {idx}", "words": []}
        for idx in range(6)
    ]

    annotate._write_stt_cache("Abs01", "/tmp/abs.wav", "ku", segments)

    payload = json.loads((tmp_path / "coarse_transcripts" / "Abs01.json").read_text(encoding="utf-8"))
    assert payload["segments"][0]["start"] == 0.0
    assert payload["segments"][5]["start"] == 1200.0
    assert payload["segments"][5]["end"] == 1204.0


def test_read_stt_cache_round_trip_drops_chunks_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    annotate = _bind_tmp_stt_cache(monkeypatch, tmp_path)
    result_envelope = {
        "chunks": [
            {"idx": 0, "span": {"idx": 0, "start": 0, "end": 600}, "status": "ok"},
            {"idx": 1, "span": {"idx": 1, "start": 600, "end": 1200}, "status": "ok"},
        ],
        "segments": [
            {"start": 0.0, "end": 2.5, "text": "flat one", "words": []},
            {"start": 602.0, "end": 605.0, "text": "flat two", "words": []},
        ],
    }

    annotate._write_stt_cache("Round01", "/tmp/round.wav", "ku", result_envelope["segments"])

    cache_file = tmp_path / "coarse_transcripts" / "Round01.json"
    raw_payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "chunks" not in raw_payload
    assert "chunk_results" not in raw_payload
    assert annotate._read_stt_cache("Round01") == result_envelope["segments"]


def test_cache_path_unchanged_pre_post_chunking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    annotate = _bind_tmp_stt_cache(monkeypatch, tmp_path)

    assert annotate._stt_cache_path("Fail01") == tmp_path / "coarse_transcripts" / "Fail01.json"
