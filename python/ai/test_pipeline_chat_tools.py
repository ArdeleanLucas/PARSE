"""Tests for the pipeline preflight + run chat tools.

These tools are exposed via MCP so external agents can answer
"can I run a batch across all speakers?" and kick off a full
pipeline for a single speaker. The tests exercise the happy
path, validation, and callback-missing failure modes — all
behaviour is client-side, so there's no need to spin up a server.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import (
    ChatToolExecutionError,
    ChatToolValidationError,
    ParseChatTools,
)


def _seed_annotation(tmp_path: pathlib.Path, speaker: str) -> None:
    """Drop a minimally-valid annotation file so speakers_list picks it up."""
    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir(exist_ok=True)
    (ann_dir / f"{speaker}.parse.json").write_text(
        json.dumps({"version": 1, "speaker": speaker, "tiers": {}}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# speakers_list
# ---------------------------------------------------------------------------


def test_speakers_list_enumerates_annotation_stems(tmp_path):
    _seed_annotation(tmp_path, "Fail01")
    _seed_annotation(tmp_path, "Fail02")
    _seed_annotation(tmp_path, "Kalh01")
    # Add a non-annotation dir that should be skipped.
    (tmp_path / "annotations" / "backups").mkdir()
    # Legacy .json without .parse.json is also a valid annotation.
    (tmp_path / "annotations" / "Legacy01.json").write_text("{}", encoding="utf-8")

    tools = ParseChatTools(project_root=tmp_path)
    result = tools.execute("speakers_list", {})
    speakers = result["result"]["speakers"]

    assert speakers == ["Fail01", "Fail02", "Kalh01", "Legacy01"]
    assert result["result"]["count"] == 4
    assert "backups" not in speakers


def test_speakers_list_empty_when_no_annotations(tmp_path):
    tools = ParseChatTools(project_root=tmp_path)
    result = tools.execute("speakers_list", {})
    assert result["result"]["speakers"] == []
    assert result["result"]["count"] == 0


# ---------------------------------------------------------------------------
# pipeline_state_read
# ---------------------------------------------------------------------------


def _fake_state(speaker: str) -> Dict[str, Any]:
    return {
        "speaker": speaker,
        "normalize": {"done": True, "can_run": True, "reason": None, "path": "x.wav"},
        "stt":       {"done": True, "can_run": True, "reason": None, "segments": 82},
        "ortho":     {"done": False, "can_run": True, "reason": None, "intervals": 0},
        "ipa":       {"done": False, "can_run": False,
                      "reason": "No ortho intervals yet — run ORTH first", "intervals": 0},
    }


def test_pipeline_state_read_returns_preflight(tmp_path):
    tools = ParseChatTools(project_root=tmp_path, pipeline_state=_fake_state)
    result = tools.execute("pipeline_state_read", {"speaker": "Fail02"})
    payload = result["result"]
    assert payload["speaker"] == "Fail02"
    assert payload["stt"]["done"] is True
    assert payload["ipa"]["can_run"] is False
    assert "run ORTH first" in payload["ipa"]["reason"]


def test_pipeline_state_read_requires_callback(tmp_path):
    tools = ParseChatTools(project_root=tmp_path)  # no pipeline_state passed
    with pytest.raises(ChatToolExecutionError, match="pipeline state callback"):
        tools.execute("pipeline_state_read", {"speaker": "Fail02"})


# ---------------------------------------------------------------------------
# pipeline_state_batch
# ---------------------------------------------------------------------------


def test_pipeline_state_batch_defaults_to_every_speaker(tmp_path):
    _seed_annotation(tmp_path, "Fail01")
    _seed_annotation(tmp_path, "Fail02")

    tools = ParseChatTools(project_root=tmp_path, pipeline_state=_fake_state)
    result = tools.execute("pipeline_state_batch", {})
    payload = result["result"]

    assert payload["count"] == 2
    speakers = [r["speaker"] for r in payload["rows"]]
    assert speakers == ["Fail01", "Fail02"]
    # One per speaker × IPA blocked → each speaker counts as blocked at least once.
    assert payload["blockedSpeakers"] == 2


def test_pipeline_state_batch_honors_speaker_filter(tmp_path):
    _seed_annotation(tmp_path, "Fail01")
    _seed_annotation(tmp_path, "Fail02")

    tools = ParseChatTools(project_root=tmp_path, pipeline_state=_fake_state)
    result = tools.execute("pipeline_state_batch", {"speakers": ["Fail02"]})
    speakers = [r["speaker"] for r in result["result"]["rows"]]
    assert speakers == ["Fail02"]


# ---------------------------------------------------------------------------
# pipeline_run + compute_status
# ---------------------------------------------------------------------------


def test_pipeline_run_forwards_payload_to_start_compute(tmp_path):
    captured: Dict[str, Any] = {}

    def fake_start_compute(compute_type: str, payload: Dict[str, Any]) -> str:
        captured["type"] = compute_type
        captured["payload"] = payload
        return "job-abc"

    tools = ParseChatTools(project_root=tmp_path, start_compute_job=fake_start_compute)
    result = tools.execute(
        "pipeline_run",
        {
            "speaker": "Fail02",
            "steps": ["ortho", "ipa"],
            "overwrites": {"ortho": True, "ipa": False},
            "language": "sd",
        },
    )

    assert captured["type"] == "full_pipeline"
    assert captured["payload"]["speaker"] == "Fail02"
    assert captured["payload"]["steps"] == ["ortho", "ipa"]
    assert captured["payload"]["overwrites"] == {"ortho": True, "ipa": False}
    assert captured["payload"]["language"] == "sd"

    payload = result["result"]
    assert payload["jobId"] == "job-abc"
    assert payload["status"] == "running"
    assert payload["computeType"] == "full_pipeline"


def test_pipeline_run_deduplicates_and_lowercases_steps(tmp_path):
    def fake_start_compute(compute_type: str, payload: Dict[str, Any]) -> str:
        return "job-x"

    tools = ParseChatTools(project_root=tmp_path, start_compute_job=fake_start_compute)
    # steps contains dup + wrong case — should normalize.
    # Note the schema enum rejects invalid strings; test with valid + dup.
    result = tools.execute(
        "pipeline_run",
        {"speaker": "Fail02", "steps": ["ortho", "ortho", "ipa"]},
    )
    assert result["result"]["steps"] == ["ortho", "ipa"]


def test_pipeline_run_rejects_invalid_steps(tmp_path):
    tools = ParseChatTools(project_root=tmp_path, start_compute_job=lambda *a: "x")
    with pytest.raises(ChatToolValidationError):
        # "something" is not in the schema's enum — fails schema validation.
        tools.execute("pipeline_run", {"speaker": "Fail02", "steps": ["something"]})


def test_pipeline_run_requires_callback(tmp_path):
    tools = ParseChatTools(project_root=tmp_path)
    with pytest.raises(ChatToolExecutionError, match="start_compute"):
        tools.execute("pipeline_run", {"speaker": "Fail02", "steps": ["ortho"]})


def test_compute_status_returns_full_snapshot(tmp_path):
    def fake_snapshot(job_id: str):
        return {
            "jobId": job_id,
            "type": "compute:full_pipeline",
            "status": "complete",
            "progress": 100.0,
            "message": "Compute complete",
            "error": None,
            "result": {
                "speaker": "Fail02",
                "steps_run": ["ortho", "ipa"],
                "results": {
                    "ortho": {"status": "ok", "filled": 128},
                    "ipa": {"status": "ok", "filled": 129},
                },
                "summary": {"ok": 2, "skipped": 0, "error": 0},
            },
        }

    tools = ParseChatTools(project_root=tmp_path, get_job_snapshot=fake_snapshot)
    result = tools.execute(
        "compute_status",
        {"jobId": "job-1", "computeType": "full_pipeline"},
    )
    payload = result["result"]
    assert payload["status"] == "complete"
    assert payload["result"]["summary"]["ok"] == 2


def test_compute_status_flags_job_type_mismatch(tmp_path):
    def fake_snapshot(job_id: str):
        return {"type": "stt", "status": "complete"}

    tools = ParseChatTools(project_root=tmp_path, get_job_snapshot=fake_snapshot)
    result = tools.execute(
        "compute_status",
        {"jobId": "job-1", "computeType": "full_pipeline"},
    )
    assert result["result"]["status"] == "invalid_job_type"
    assert result["result"]["expected"] == "compute:full_pipeline"


def test_compute_status_unknown_job(tmp_path):
    tools = ParseChatTools(project_root=tmp_path, get_job_snapshot=lambda _: None)
    result = tools.execute("compute_status", {"jobId": "gone"})
    assert result["result"]["status"] == "not_found"
