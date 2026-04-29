"""Regression tests for ORTH language fallback from annotation metadata."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _RecordingOrthoProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def transcribe(self, audio_path, language=None, progress_callback=None):
        self.calls.append({"audio_path": str(audio_path), "language": language})
        if progress_callback is not None:
            progress_callback(25.0, 1)
        return [{"start": 0.0, "end": 0.4, "text": "سەر"}]


def _seed_annotation(
    tmp_path: pathlib.Path,
    *,
    speaker: str = "Fail01",
    language_code: str | None = "ku",
    source_audio: str = "raw/Fail01.wav",
) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    metadata: dict[str, object] = {}
    if language_code is not None:
        metadata["language_code"] = language_code
    payload = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 1.0,
        "tiers": {
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "concept": {"type": "interval", "display_order": 3, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": metadata,
    }
    (annotations_dir / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    audio_path = tmp_path / source_audio
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")


def _install_provider(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    provider = _RecordingOrthoProvider()
    monkeypatch.setattr(server, "get_ortho_provider", lambda: provider)
    return provider


def test_ortho_uses_annotation_language_when_payload_omits_language(tmp_path, monkeypatch):
    provider = _install_provider(tmp_path, monkeypatch)
    _seed_annotation(tmp_path, language_code="ku")

    server._compute_speaker_ortho("job-ortho", {"speaker": "Fail01"})

    assert provider.calls[0]["language"] == "ku"


def test_ortho_payload_language_wins_over_annotation_metadata(tmp_path, monkeypatch):
    provider = _install_provider(tmp_path, monkeypatch)
    _seed_annotation(tmp_path, language_code="ku")

    server._compute_speaker_ortho("job-ortho", {"speaker": "Fail01", "language": "sd"})

    assert provider.calls[0]["language"] == "sd"


def test_ortho_warns_and_uses_auto_detect_when_no_language_source(tmp_path, monkeypatch, capsys):
    provider = _install_provider(tmp_path, monkeypatch)
    _seed_annotation(tmp_path, language_code=None)

    server._compute_speaker_ortho("job-ortho", {"speaker": "Fail01"})

    assert provider.calls[0]["language"] is None
    assert "metadata.language_code" in capsys.readouterr().err
