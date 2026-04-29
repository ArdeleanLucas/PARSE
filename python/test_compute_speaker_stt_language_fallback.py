"""Regression tests for STT language fallback from annotation metadata."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


def _seed_annotation(
    tmp_path: pathlib.Path,
    *,
    speaker: str = "Fail01",
    language_code: str | None = "ku",
    source_audio: str = "raw/Fail01.wav",
) -> pathlib.Path:
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
    return audio_path


def _install_stt_capture(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    captured: dict[str, object] = {}

    def _fake_run_stt_job(job_id, speaker, source_wav, language):
        captured.update(
            {"job_id": job_id, "speaker": speaker, "source_wav": source_wav, "language": language}
        )
        return {"speaker": speaker, "sourceWav": source_wav, "language": language, "segments": []}

    monkeypatch.setattr(server, "_run_stt_job", _fake_run_stt_job)
    return captured


def test_stt_uses_annotation_language_when_payload_omits_language(tmp_path, monkeypatch):
    captured = _install_stt_capture(tmp_path, monkeypatch)
    _seed_annotation(tmp_path, language_code="ku")

    server._compute_speaker_stt("job-stt", {"speaker": "Fail01"})

    assert captured["language"] == "ku"


def test_stt_payload_language_wins_over_annotation_metadata(tmp_path, monkeypatch):
    captured = _install_stt_capture(tmp_path, monkeypatch)
    _seed_annotation(tmp_path, language_code="ku")

    server._compute_speaker_stt("job-stt", {"speaker": "Fail01", "language": "sd"})

    assert captured["language"] == "sd"


def test_stt_warns_and_uses_auto_detect_when_no_language_source(tmp_path, monkeypatch, capsys):
    captured = _install_stt_capture(tmp_path, monkeypatch)
    _seed_annotation(tmp_path, language_code=None)

    server._compute_speaker_stt("job-stt", {"speaker": "Fail01"})

    assert captured["language"] is None
    assert "metadata.language_code" in capsys.readouterr().err
