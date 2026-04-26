from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools.offset_apply_tools import tool_apply_timestamp_offset


def _write_annotation(project_root: pathlib.Path, speaker: str = "Test01") -> pathlib.Path:
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
                            {"start": 10.0, "end": 10.5, "text": "STONE", "manuallyAdjusted": True},
                            {"start": 20.0, "end": 20.5, "text": "WATER"},
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_tool_apply_timestamp_offset_runs_direct_bundle_handler(tmp_path) -> None:
    path = _write_annotation(tmp_path, "Test01")
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_apply_timestamp_offset(
        tools,
        {"speaker": "Test01", "offsetSec": 5.0, "dryRun": False},
    )

    assert payload["speaker"] == "Test01"
    assert payload["shiftedIntervals"] == 1
    persisted = json.loads(path.read_text(encoding="utf-8"))
    by_text = {iv["text"]: iv for iv in persisted["tiers"]["concept"]["intervals"]}
    assert by_text["STONE"]["start"] == 10.0
    assert by_text["WATER"]["start"] == 25.0


def test_tool_apply_timestamp_offset_supports_dry_run_directly(tmp_path) -> None:
    _write_annotation(tmp_path, "Test01")
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_apply_timestamp_offset(
        tools,
        {"speaker": "Test01", "offsetSec": 5.0, "dryRun": True},
    )

    assert payload["dryRun"] is True
    assert payload["wouldShiftIntervals"] == 1
    assert payload["preview"][0]["to"] == [25.0, 25.5]
