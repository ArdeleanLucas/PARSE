from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools.offset_detection_tools import tool_detect_timestamp_offset, tool_detect_timestamp_offset_from_pair


def _write_annotation(project_root: pathlib.Path, speaker: str = "Fail01") -> pathlib.Path:
    annotations_dir = project_root / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    path = annotations_dir / f"{speaker}.parse.json"
    path.write_text(
        json.dumps(
            {
                "speaker": speaker,
                "tiers": {
                    "concept": {
                        "intervals": [
                            {"start": 1.0, "end": 1.4, "text": "alpha"},
                            {"start": 2.0, "end": 2.4, "text": "beta"},
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_tool_detect_timestamp_offset_from_pair_runs_direct_bundle_handler(tmp_path) -> None:
    _write_annotation(tmp_path, "Fail01")
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_detect_timestamp_offset_from_pair(
        tools,
        {"speaker": "Fail01", "audioTimeSec": 1.5, "csvTimeSec": 1.0},
    )

    assert payload["speaker"] == "Fail01"
    assert payload["offsetSec"] == 0.5
    assert payload["method"] == "manual_pair"
    assert payload["nAnchors"] == 1


def test_tool_detect_timestamp_offset_runs_direct_bundle_handler(tmp_path) -> None:
    _write_annotation(tmp_path, "Fail01")

    snapshot = {
        "type": "stt",
        "status": "complete",
        "result": {
            "segments": [
                {"start": 1.5, "end": 1.9, "text": "alpha"},
                {"start": 2.5, "end": 2.9, "text": "beta"},
            ]
        },
    }
    tools = ParseChatTools(project_root=tmp_path, get_job_snapshot=lambda job_id: snapshot)

    payload = tool_detect_timestamp_offset(
        tools,
        {"speaker": "Fail01", "sttJobId": "job-stt-1", "nAnchors": 2},
    )

    assert payload["speaker"] == "Fail01"
    assert payload["offsetSec"] == 0.5
    assert payload["method"] in {"monotonic_alignment", "bucket_vote"}
    assert payload["annotationPath"].endswith("Fail01.parse.json")
