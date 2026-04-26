from __future__ import annotations

import json
import pathlib
import sys
from types import MethodType
from typing import Any, Dict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools.pipeline_orchestration_tools import (
    tool_pipeline_run,
    tool_pipeline_state_batch,
)


def _seed_annotation(tmp_path: pathlib.Path, speaker: str) -> None:
    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir(exist_ok=True)
    (ann_dir / f"{speaker}.parse.json").write_text(
        json.dumps({"version": 1, "speaker": speaker, "tiers": {}}),
        encoding="utf-8",
    )


def _fake_state(speaker: str) -> Dict[str, Any]:
    return {
        "speaker": speaker,
        "duration_sec": 300.0,
        "normalize": {"done": True, "can_run": True, "reason": None, "path": "x.wav"},
        "stt": {"done": True, "can_run": True, "reason": None, "segments": 82, "full_coverage": True, "coverage_fraction": 0.99},
        "ortho": {"done": False, "can_run": True, "reason": None, "intervals": 0, "full_coverage": False, "coverage_fraction": 0.0},
        "ipa": {"done": False, "can_run": False, "reason": "No ortho intervals yet — run ORTH first", "intervals": 0, "full_coverage": False, "coverage_fraction": 0.0},
    }


def test_tool_pipeline_state_batch_reads_speakers_without_wrapper_bounce(tmp_path) -> None:
    _seed_annotation(tmp_path, "Fail01")
    _seed_annotation(tmp_path, "Fail02")

    tools = ParseChatTools(project_root=tmp_path, pipeline_state=_fake_state)

    def _unexpected_wrapper(self, args):
        raise AssertionError("pipeline bundle should call project_read_tools directly")

    tools._tool_speakers_list = MethodType(_unexpected_wrapper, tools)

    payload = tool_pipeline_state_batch(tools, {})

    assert payload["count"] == 2
    assert [row["speaker"] for row in payload["rows"]] == ["Fail01", "Fail02"]
    assert payload["blockedSpeakers"] == 2


def test_tool_pipeline_run_deduplicates_steps_directly(tmp_path) -> None:
    captured: Dict[str, Any] = {}

    def _start_compute(compute_type: str, payload: Dict[str, Any]) -> str:
        captured["type"] = compute_type
        captured["payload"] = payload
        return "job-pipeline-direct"

    tools = ParseChatTools(project_root=tmp_path, start_compute_job=_start_compute)

    payload = tool_pipeline_run(
        tools,
        {"speaker": "Fail02", "steps": ["ortho", "ortho", "ipa"], "language": "sd"},
    )

    assert payload["jobId"] == "job-pipeline-direct"
    assert payload["steps"] == ["ortho", "ipa"]
    assert captured == {
        "type": "full_pipeline",
        "payload": {
            "speaker": "Fail02",
            "steps": ["ortho", "ipa"],
            "overwrites": {},
            "language": "sd",
        },
    }
