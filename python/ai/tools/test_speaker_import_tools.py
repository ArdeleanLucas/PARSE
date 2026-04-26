from __future__ import annotations

import json
import pathlib
import sys
import wave
from types import MethodType

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools.speaker_import_tools import (
    tool_import_processed_speaker,
    tool_onboard_speaker_import,
)


def _write_test_wav(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 8000)


def _write_processed_fixture(root: pathlib.Path, speaker: str = "Fail02") -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    wav_path = root / "Audio_Working" / speaker / "speaker.wav"
    _write_test_wav(wav_path)

    annotation_path = root / "annotations" / f"{speaker}.json"
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "southern-kurdish-dialect-comparison",
                "speaker": speaker,
                "source_audio": f"audio/working/{speaker}/speaker.wav",
                "source_audio_duration_sec": 2.0,
                "metadata": {"language_code": "sdh", "timestamps_source": "processed"},
                "tiers": {
                    "concept": {"display_order": 3, "intervals": [{"start": 0.0, "end": 1.0, "text": "1: ash"}, {"start": 1.0, "end": 2.0, "text": "2: bark"}]},
                    "speaker": {"display_order": 4, "intervals": [{"start": 0.0, "end": 1.0, "text": speaker}, {"start": 1.0, "end": 2.0, "text": speaker}]},
                },
            }
        ),
        encoding="utf-8",
    )

    peaks_path = root / "peaks" / f"{speaker}.json"
    peaks_path.parent.mkdir(parents=True, exist_ok=True)
    peaks_path.write_text(json.dumps({"duration": 2.0, "peaks": [0, 1, 0, -1]}), encoding="utf-8")
    return wav_path, annotation_path, peaks_path


def test_tool_onboard_speaker_import_reports_dry_run_plan_directly(tmp_path) -> None:
    external_root = tmp_path / "external"
    external_root.mkdir()
    wav_path = external_root / "spk1.wav"
    _write_test_wav(wav_path)

    project_root = tmp_path / "proj"
    project_root.mkdir()
    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])

    def _display_override(self, path: pathlib.Path) -> str:
        return f"display::{path.name}"

    tools._display_readable_path = MethodType(_display_override, tools)

    payload = tool_onboard_speaker_import(
        tools,
        {"speaker": "Speaker01", "sourceWav": str(wav_path), "dryRun": True},
    )

    assert payload["ok"] is True
    assert payload["dryRun"] is True
    assert payload["plan"]["speaker"] == "Speaker01"
    assert payload["plan"]["wavDest"] == "display::spk1.wav"


def test_tool_import_processed_speaker_reports_dry_run_plan_directly(tmp_path) -> None:
    external_root = tmp_path / "Thesis"
    wav_path, annotation_path, peaks_path = _write_processed_fixture(external_root)
    project_root = tmp_path / "proj"
    project_root.mkdir()
    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])

    payload = tool_import_processed_speaker(
        tools,
        {
            "speaker": "Fail02",
            "workingWav": str(wav_path),
            "annotationJson": str(annotation_path),
            "peaksJson": str(peaks_path),
            "dryRun": True,
        },
    )

    assert payload["ok"] is True
    assert payload["dryRun"] is True
    assert payload["plan"]["speaker"] == "Fail02"
    assert payload["plan"]["conceptCount"] == 2
    assert payload["plan"]["audioDest"].endswith("audio/working/Fail02/speaker.wav")
