"""Regression tests for concept-scoped STT compute modes."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

pytest.importorskip("numpy")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _StubSttProvider:
    def __init__(self) -> None:
        self.clip_calls: list[dict[str, object]] = []

    def transcribe_clip(self, audio_array, *, initial_prompt=None, language=None):
        call_index = len(self.clip_calls) + 1
        self.clip_calls.append(
            {
                "samples": int(getattr(audio_array, "shape", [0])[0] or 0),
                "initial_prompt": initial_prompt,
                "language": language,
            }
        )
        return (f"stt-window-{call_index}", 0.70 + call_index / 100.0)


def _seed_annotation(
    tmp_path: pathlib.Path,
    *,
    speaker: str = "Fail02",
    concept_intervals: list[dict[str, object]] | None = None,
    source_audio: str = "raw/Fail02.wav",
) -> None:
    (tmp_path / "annotations").mkdir(exist_ok=True)
    payload = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 8.0,
        "tiers": {
            "concept": {"type": "interval", "display_order": 3, "intervals": concept_intervals or []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "sdh"},
    }
    (tmp_path / "annotations" / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    audio_path = tmp_path / source_audio
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFFWAVEfake")


def _patch_audio_loader(monkeypatch, duration_sec: float = 8.0) -> None:
    import numpy as np
    import ai.forced_align as forced_align

    fake_audio = np.zeros(int(duration_sec * 16000), dtype=np.float32)
    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: fake_audio)


def _load_stt_cache(tmp_path: pathlib.Path, speaker: str = "Fail02") -> dict[str, object]:
    return json.loads((tmp_path / "coarse_transcripts" / f"{speaker}.json").read_text("utf-8"))


def test_compute_speaker_stt_concept_windows_transcribes_each_concept_window(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    stub = _StubSttProvider()
    monkeypatch.setattr(server, "get_stt_provider", lambda: stub)
    _patch_audio_loader(monkeypatch)

    _seed_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2"},
            {"start": 4.0, "end": 4.5, "text": "3"},
        ],
    )

    result = server._compute_speaker_stt(
        "job-stt",
        {"speaker": "Fail02", "run_mode": "concept-windows", "language": "ku"},
    )

    assert result["run_mode"] == "concept-windows"
    assert result["concept_windows"] == 3
    assert result["segments_written"] == 3
    assert len(stub.clip_calls) == 3
    assert all(call["language"] == "ku" for call in stub.clip_calls)
    assert "1" in str(stub.clip_calls[0]["initial_prompt"])

    cache = _load_stt_cache(tmp_path)
    assert cache["source"] == "concept-windows"
    assert [segment["conceptId"] for segment in cache["segments"]] == ["1", "2", "3"]
    assert [segment["text"] for segment in cache["segments"]] == [
        "stt-window-1",
        "stt-window-2",
        "stt-window-3",
    ]
    assert [(segment["start"], segment["end"]) for segment in cache["segments"]] == [
        (1.0, 1.2),
        (2.0, 2.4),
        (4.0, 4.5),
    ]


def test_compute_speaker_stt_concept_windows_respects_explicit_concept_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    stub = _StubSttProvider()
    monkeypatch.setattr(server, "get_stt_provider", lambda: stub)
    _patch_audio_loader(monkeypatch)

    _seed_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2"},
            {"start": 4.0, "end": 4.5, "text": "3"},
        ],
    )

    result = server._compute_speaker_stt(
        "job-stt",
        {"speaker": "Fail02", "run_mode": "concept-windows", "concept_ids": ["2"]},
    )

    assert result["concept_windows"] == 1
    assert result["affected_concepts"] == [{"concept_id": "2", "start": 2.0, "end": 2.4}]
    assert len(stub.clip_calls) == 1
    cache = _load_stt_cache(tmp_path)
    assert [(segment["conceptId"], segment["text"]) for segment in cache["segments"]] == [("2", "stt-window-1")]


def test_compute_speaker_stt_edited_only_filters_to_manually_adjusted_concepts(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    stub = _StubSttProvider()
    monkeypatch.setattr(server, "get_stt_provider", lambda: stub)
    _patch_audio_loader(monkeypatch)

    _seed_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2", "manuallyAdjusted": True},
            {"start": 4.0, "end": 4.5, "text": "3"},
        ],
    )

    result = server._compute_speaker_stt(
        "job-stt",
        {"speaker": "Fail02", "run_mode": "edited-only"},
    )

    assert result["run_mode"] == "edited-only"
    assert result["concept_windows"] == 1
    assert result["segments_written"] == 1
    assert len(stub.clip_calls) == 1
    cache = _load_stt_cache(tmp_path)
    assert [segment["conceptId"] for segment in cache["segments"]] == ["2"]
    assert cache["segments"][0]["text"] == "stt-window-1"


def test_compute_speaker_stt_edited_only_empty_is_structured_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        server,
        "get_stt_provider",
        lambda: (_ for _ in ()).throw(AssertionError("edited-only empty must not load STT provider")),
    )
    _patch_audio_loader(monkeypatch)

    _seed_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2"},
        ],
    )

    result = server._compute_speaker_stt(
        "job-stt",
        {"speaker": "Fail02", "run_mode": "edited-only"},
    )

    assert result["run_mode"] == "edited-only"
    assert result["skipped"] is True
    assert result["no_op"] is True
    assert result["concept_windows"] == 0
    assert "No edited concepts" in result["reason"]
    assert not (tmp_path / "coarse_transcripts" / "Fail02.json").exists()
