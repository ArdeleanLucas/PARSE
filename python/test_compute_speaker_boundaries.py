"""Unit tests for _compute_speaker_boundaries (the standalone BND job)."""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


def _seed_annotation(
    tmp_path: pathlib.Path,
    speaker: str,
    ortho_words: List[Dict[str, Any]] | None = None,
    source_audio: str = "raw/Fail02.wav",
) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    tiers = {
        "ipa": {"type": "interval", "display_order": 1, "intervals": []},
        "ortho": {"type": "interval", "display_order": 2, "intervals": []},
        "concept": {"type": "interval", "display_order": 3, "intervals": []},
        "speaker": {"type": "interval", "display_order": 4, "intervals": []},
    }
    if ortho_words is not None:
        tiers["ortho_words"] = {
            "type": "interval",
            "display_order": 5,
            "intervals": ortho_words,
        }
    annotation = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 10.0,
        "tiers": tiers,
        "metadata": {
            "language_code": "sdh",
            "created": "2026-01-01T00:00:00Z",
            "modified": "2026-01-01T00:00:00Z",
        },
    }
    (annotations_dir / f"{speaker}.parse.json").write_text(json.dumps(annotation), encoding="utf-8")


def _write_fake_source_wav(tmp_path: pathlib.Path, rel_path: str) -> None:
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")


def _write_stt_cache(tmp_path: pathlib.Path, speaker: str, segments: List[Dict[str, Any]]) -> None:
    cache_dir = tmp_path / "coarse_transcripts"
    cache_dir.mkdir(exist_ok=True)
    payload = {
        "speaker": speaker,
        "source_wav": f"raw/{speaker}.wav",
        "language": "ku",
        "segments": segments,
    }
    (cache_dir / f"{speaker}.json").write_text(json.dumps(payload), encoding="utf-8")


def _load_canonical(tmp_path: pathlib.Path, speaker: str) -> Dict[str, Any]:
    return json.loads((tmp_path / "annotations" / f"{speaker}.parse.json").read_text("utf-8"))


def _install_align_stub(monkeypatch, fake_aligned: List[Dict[str, Any]]) -> None:
    monkeypatch.setattr(server, "_ortho_tier2_align_to_words", lambda audio_path, segments: fake_aligned)


def test_writes_ortho_words_from_stt_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    _seed_annotation(tmp_path, "Fail02")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(
        tmp_path,
        "Fail02",
        [{"start": 1.0, "end": 1.5, "text": "one", "words": [{"word": "one", "start": 1.0, "end": 1.5, "prob": 0.9}]}],
    )
    _install_align_stub(
        monkeypatch,
        [
            {"start": 1.0, "end": 1.4, "text": "one"},
            {"start": 2.0, "end": 2.5, "text": "two"},
        ],
    )

    result = server._compute_speaker_boundaries("j1", {"speaker": "Fail02"})

    assert result == {"speaker": "Fail02", "generated": 2, "preserved_manual": 0, "total": 2}
    ann = _load_canonical(tmp_path, "Fail02")
    intervals = ann["tiers"]["ortho_words"]["intervals"]
    assert [round(interval["start"], 2) for interval in intervals] == [1.0, 2.0]
    assert all(interval.get("manuallyAdjusted") is False for interval in intervals)


@pytest.mark.parametrize("alias", ["boundaries", "bnd", "ortho_words", "ortho-words"])
def test_run_compute_job_dispatches_boundaries_aliases(tmp_path, monkeypatch, alias):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    speaker = f"Disp_{alias.replace('-', '_')}"
    _seed_annotation(tmp_path, speaker, source_audio=f"raw/{speaker}.wav")
    _write_fake_source_wav(tmp_path, f"raw/{speaker}.wav")
    _write_stt_cache(
        tmp_path,
        speaker,
        [{"start": 0.0, "end": 1.0, "text": "x", "words": [{"word": "x", "start": 0.0, "end": 1.0, "prob": 0.9}]}],
    )
    _install_align_stub(monkeypatch, [{"start": 0.0, "end": 0.8, "text": "x"}])

    captured: Dict[str, Any] = {}
    monkeypatch.setattr(server, "_set_job_complete", lambda job_id, result, **kwargs: captured.setdefault("result", result))
    monkeypatch.setattr(server, "_set_job_error", lambda job_id, err: captured.setdefault("error", err))

    server._run_compute_job(f"j-{alias}", alias, {"speaker": speaker})
    assert "error" not in captured, captured
    assert captured["result"]["generated"] == 1


def test_missing_stt_word_timestamps_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    _seed_annotation(tmp_path, "Fail02")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(tmp_path, "Fail02", [{"start": 1.0, "end": 1.5, "text": "one"}])
    _install_align_stub(monkeypatch, [])

    with pytest.raises(RuntimeError, match="Run STT first"):
        server._compute_speaker_boundaries("j1", {"speaker": "Fail02"})


def test_preserves_manual_intervals_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    _seed_annotation(
        tmp_path,
        "Fail02",
        ortho_words=[{"start": 2.0, "end": 2.5, "text": "manual", "manuallyAdjusted": True}],
    )
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(
        tmp_path,
        "Fail02",
        [{"start": 1.0, "end": 1.5, "text": "one", "words": [{"word": "one", "start": 1.0, "end": 1.5, "prob": 0.9}]}],
    )
    _install_align_stub(
        monkeypatch,
        [
            {"start": 1.0, "end": 1.4, "text": "one"},
            {"start": 2.1, "end": 2.4, "text": "overlap-drop"},
            {"start": 3.0, "end": 3.3, "text": "three"},
        ],
    )

    result = server._compute_speaker_boundaries("j1", {"speaker": "Fail02"})

    assert result == {"speaker": "Fail02", "generated": 2, "preserved_manual": 1, "total": 3}
    ann = _load_canonical(tmp_path, "Fail02")
    intervals = ann["tiers"]["ortho_words"]["intervals"]
    texts = [interval["text"] for interval in intervals]
    assert texts == ["one", "manual", "three"]
    assert intervals[1]["manuallyAdjusted"] is True


def test_overwrite_discards_manual_intervals(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    _seed_annotation(
        tmp_path,
        "Fail02",
        ortho_words=[{"start": 2.0, "end": 2.5, "text": "manual", "manuallyAdjusted": True}],
    )
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_stt_cache(
        tmp_path,
        "Fail02",
        [{"start": 1.0, "end": 1.5, "text": "one", "words": [{"word": "one", "start": 1.0, "end": 1.5, "prob": 0.9}]}],
    )
    _install_align_stub(monkeypatch, [{"start": 3.0, "end": 3.3, "text": "fresh"}])

    result = server._compute_speaker_boundaries("j1", {"speaker": "Fail02", "overwrite": True})

    assert result == {"speaker": "Fail02", "generated": 1, "preserved_manual": 0, "total": 1}
    ann = _load_canonical(tmp_path, "Fail02")
    intervals = ann["tiers"]["ortho_words"]["intervals"]
    assert len(intervals) == 1
    assert intervals[0]["text"] == "fresh"
    assert intervals[0]["manuallyAdjusted"] is False
