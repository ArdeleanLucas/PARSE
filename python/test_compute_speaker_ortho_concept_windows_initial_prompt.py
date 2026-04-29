"""Prompt-safety regression tests for ORTH concept-window transcription."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

pytest.importorskip("numpy")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _PromptRecordingProvider:
    def __init__(self) -> None:
        self.clip_calls: list[dict[str, object]] = []

    def transcribe(self, *args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("concept-window ORTH must not call full-file transcribe")

    def transcribe_clip(self, audio_array, *, initial_prompt=None, language=None):
        call_index = len(self.clip_calls) + 1
        self.clip_calls.append({"initial_prompt": initial_prompt, "language": language})
        return (f"window-{call_index}", 0.8)


def _seed_annotation(tmp_path: pathlib.Path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    payload = {
        "version": 1,
        "project_id": "t",
        "speaker": "Fail01",
        "source_audio": "raw/Fail01.wav",
        "source_audio_duration_sec": 5.0,
        "tiers": {
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 1.0, "end": 1.3, "text": "head"},
                    {"start": 2.0, "end": 2.4, "text": "arm"},
                ],
            },
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "ku"},
    }
    (annotations_dir / "Fail01.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    audio_path = tmp_path / "raw" / "Fail01.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")


def _patch_audio_loader(monkeypatch, duration_sec: float = 5.0) -> None:
    import numpy as np
    import ai.forced_align as forced_align

    fake_audio = np.zeros(int(duration_sec * 16000), dtype=np.float32)
    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: fake_audio)


def test_ortho_concept_windows_drops_english_gloss_initial_prompt(tmp_path, monkeypatch):
    provider = _PromptRecordingProvider()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: provider)
    _patch_audio_loader(monkeypatch)
    _seed_annotation(tmp_path)

    result = server._compute_speaker_ortho(
        "job-ortho",
        {"speaker": "Fail01", "run_mode": "concept-windows", "overwrite": True},
    )

    assert result["filled"] == 2
    assert len(provider.clip_calls) == 2
    assert all(call["language"] == "ku" for call in provider.clip_calls)
    assert all(call["initial_prompt"] is None for call in provider.clip_calls)
