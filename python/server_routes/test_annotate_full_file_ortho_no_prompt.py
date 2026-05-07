from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import server


class _FullFilePromptRecordingProvider:
    refine_lexemes = False

    def __init__(self) -> None:
        self.transcribe_calls: list[dict[str, Any]] = []

    def transcribe(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.transcribe_calls.append(kwargs)
        return [{"start": 0.0, "end": 1.0, "text": "full-one", "confidence": 0.9}]

    def transcribe_clip(self, *args: Any, **kwargs: Any) -> tuple[str, float]:  # pragma: no cover - failure path
        raise AssertionError("full-file ORTH must not call transcribe_clip")


def _seed_annotation(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "project_id": "t",
        "speaker": "Fail01",
        "source_audio": "raw/Fail01.wav",
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "concept": {"type": "interval", "display_order": 3, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "ku"},
    }
    (annotations_dir / "Fail01.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    audio_path = tmp_path / "raw" / "Fail01.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")


def test_compute_speaker_ortho_full_file_passes_initial_prompt_none(tmp_path: Path, monkeypatch) -> None:
    provider = _FullFilePromptRecordingProvider()
    server._install_route_bindings()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_pipeline_audio_path_for_speaker", lambda speaker: tmp_path / "raw" / f"{speaker}.wav")
    monkeypatch.setattr(server, "_ortho_tier2_align_to_words", lambda audio_path, segments: [])
    _seed_annotation(tmp_path)

    result = server._compute_speaker_ortho("job-full", {"speaker": "Fail01", "run_mode": "full", "overwrite": True}, provider=provider)

    assert result["filled"] == 1
    assert provider.transcribe_calls[0]["initial_prompt"] is None
