"""Tests for read_audio_info chat tool and read_csv_preview path sandboxing."""

import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools, ChatToolValidationError


def _build_project(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "ai_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "annotations").mkdir(parents=True, exist_ok=True)
    (tmp_path / "audio").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_wav(path: Path, *, frame_rate: int = 16000, channels: int = 1,
               sample_width: int = 2, duration_sec: float = 0.5) -> None:
    n_frames = int(frame_rate * duration_sec)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(frame_rate)
        w.writeframes(b"\x00" * n_frames * sample_width * channels)


def test_read_audio_info_returns_metadata(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    wav_path = project / "audio" / "clip.wav"
    _write_wav(wav_path, frame_rate=22050, channels=2, duration_sec=1.25)

    tools = ParseChatTools(project_root=project)
    result = tools.execute("read_audio_info", {"sourceWav": "audio/clip.wav"})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert inner["channels"] == 2
    assert inner["sampleRateHz"] == 22050
    assert inner["durationSec"] == 1.25
    assert inner["numFrames"] == int(22050 * 1.25)
    assert inner["path"] == "audio/clip.wav"


def test_read_audio_info_rejects_path_outside_audio_dir(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    stray = project / "stray.wav"
    _write_wav(stray)

    tools = ParseChatTools(project_root=project)
    with pytest.raises(ChatToolValidationError):
        tools.execute("read_audio_info", {"sourceWav": "stray.wav"})


def test_read_audio_info_rejects_traversal(tmp_path: Path) -> None:
    project = _build_project(tmp_path / "proj")
    outside = tmp_path / "outside.wav"
    _write_wav(outside)

    tools = ParseChatTools(project_root=project)
    with pytest.raises(ChatToolValidationError):
        tools.execute("read_audio_info", {"sourceWav": "../outside.wav"})


def test_read_audio_info_rejects_non_wav(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    fake = project / "audio" / "clip.mp3"
    fake.write_bytes(b"ID3\x00\x00\x00\x00")

    tools = ParseChatTools(project_root=project)
    result = tools.execute("read_audio_info", {"sourceWav": "audio/clip.mp3"})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is False
    assert ".wav" in inner["error"]


def test_read_audio_info_rejects_corrupt_wav(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    bad = project / "audio" / "bad.wav"
    bad.write_bytes(b"not a real wav header")

    tools = ParseChatTools(project_root=project)
    result = tools.execute("read_audio_info", {"sourceWav": "audio/bad.wav"})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is False
    assert "Invalid WAV" in inner["error"] or "Failed to read" in inner["error"]


def test_read_csv_preview_rejects_traversal(tmp_path: Path) -> None:
    project = _build_project(tmp_path / "proj")
    outside = tmp_path / "secret.csv"
    outside.write_text("a,b\n1,2\n", encoding="utf-8")

    tools = ParseChatTools(project_root=project)
    with pytest.raises(ChatToolValidationError):
        tools.execute("read_csv_preview", {"csvPath": "../secret.csv"})


def test_read_csv_preview_still_works_for_valid_path(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    csv_path = project / "data.csv"
    csv_path.write_text("id,label\n1,one\n2,two\n", encoding="utf-8")

    tools = ParseChatTools(project_root=project)
    result = tools.execute("read_csv_preview", {"csvPath": "data.csv"})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert inner["totalRows"] == 2
    assert inner["columns"] == ["id", "label"]
