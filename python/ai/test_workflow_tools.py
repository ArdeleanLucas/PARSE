"""Tests for PARSE MCP composite workflow tools.

These tests cover the Task 3 macro surface implemented in
`python/ai/workflow_tools.py`. The macros should remain thin orchestration
layers over the existing low-level tool handlers, while exposing their own
ChatToolSpec metadata for MCP discovery.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, List, Tuple

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.workflow_tools import WorkflowTools


def _write_concepts_csv(tmp_path: pathlib.Path) -> None:
    (tmp_path / "concepts.csv").write_text(
        "id,concept_en\n1,water\n2,fire\n3,sun\n",
        encoding="utf-8",
    )


def _seed_annotation(
    tmp_path: pathlib.Path,
    speaker: str,
    *,
    source_audio: str | None = None,
    concepts: List[str] | None = None,
) -> None:
    concepts = concepts or ["1", "2"]
    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir(exist_ok=True)

    if source_audio is None:
        source_audio = f"audio/original/{speaker}.wav"
    audio_path = tmp_path / source_audio
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFFWAVE")

    concept_intervals = []
    ortho_intervals = []
    ipa_intervals = []
    speaker_intervals = []
    for index, concept_id in enumerate(concepts):
        start = float(index)
        end = float(index + 1)
        concept_intervals.append({"start": start, "end": end, "text": concept_id})
        ortho_intervals.append({"start": start, "end": end, "text": f"{speaker}-orth-{concept_id}"})
        ipa_intervals.append({"start": start, "end": end, "text": f"{speaker}-ipa-{concept_id}"})
        speaker_intervals.append({"start": start, "end": end, "text": speaker})

    payload = {
        "version": 1,
        "speaker": speaker,
        "source_audio": source_audio,
        "tiers": {
            "concept": {"type": "interval", "intervals": concept_intervals},
            "ortho": {"type": "interval", "intervals": ortho_intervals},
            "ipa": {"type": "interval", "intervals": ipa_intervals},
            "speaker": {"type": "interval", "intervals": speaker_intervals},
        },
    }
    (ann_dir / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")


def test_run_full_annotation_pipeline_orchestrates_low_level_jobs(tmp_path: pathlib.Path) -> None:
    _seed_annotation(tmp_path, "Fail02")

    start_calls: List[Tuple[str, Dict[str, Any]]] = []
    stt_calls: List[Tuple[str, str, str | None]] = []

    def fake_start_stt(speaker: str, source_wav: str, language: str | None) -> str:
        stt_calls.append((speaker, source_wav, language))
        return "job-stt"

    def fake_start_compute(compute_type: str, payload: Dict[str, Any]) -> str:
        start_calls.append((compute_type, dict(payload)))
        if compute_type == "forced_align":
            return "job-align"
        if compute_type == "ipa_only":
            return "job-ipa"
        raise AssertionError(f"Unexpected compute type: {compute_type}")

    snapshots = {
        "job-stt": {
            "type": "stt",
            "status": "complete",
            "progress": 100.0,
            "result": {
                "speaker": "Fail02",
                "sourceWav": "audio/original/Fail02.wav",
                "segments": [{"start": 0.0, "end": 1.0, "text": "alpha"}],
            },
        },
        "job-align": {
            "type": "compute:forced_align",
            "status": "complete",
            "progress": 100.0,
            "result": {"aligned": 2},
        },
        "job-ipa": {
            "type": "compute:ipa_only",
            "status": "complete",
            "progress": 100.0,
            "result": {"filled": 2},
        },
    }

    workflow = WorkflowTools(
        project_root=tmp_path,
        start_stt_job=fake_start_stt,
        start_compute_job=fake_start_compute,
        get_job_snapshot=lambda job_id: snapshots.get(job_id),
    )

    result = workflow.execute(
        "run_full_annotation_pipeline",
        {"speaker_id": "Fail02", "concept_list": ["1", "2"]},
    )
    payload = result["result"]

    assert payload["speaker_id"] == "Fail02"
    assert payload["concept_list"] == ["1", "2"]
    assert payload["final_status"] == "complete"
    assert [stage["stage"] for stage in payload["stages"]] == ["stt", "forced_align", "ipa"]
    assert payload["job_ids"] == {
        "stt": "job-stt",
        "forced_align": "job-align",
        "ipa": "job-ipa",
    }
    assert payload["progress"]["completedStages"] == 3
    assert payload["progress"]["totalStages"] == 3
    assert payload["progress"]["percent"] == 100.0
    assert payload["progress"]["done"] is True
    assert [event["event"] for event in payload["events"]] == [
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
    ]
    assert stt_calls == [("Fail02", "audio/original/Fail02.wav", None)]
    assert start_calls == [
        ("forced_align", {"speaker": "Fail02", "overwrite": False, "language": "ku", "padMs": 100, "emitPhonemes": True}),
        ("ipa_only", {"speaker": "Fail02", "overwrite": False}),
    ]


def test_run_full_annotation_pipeline_returns_structured_failure_payload(tmp_path: pathlib.Path) -> None:
    _seed_annotation(tmp_path, "Fail02")

    workflow = WorkflowTools(
        project_root=tmp_path,
        start_stt_job=lambda *_args: "job-stt",
        start_compute_job=lambda *_args, **_kwargs: "unused",
        get_job_snapshot=lambda job_id: {
            "type": "stt",
            "status": "error",
            "progress": 42.0,
            "error": "decoder crash",
            "result": {"speaker": "Fail02", "sourceWav": "audio/original/Fail02.wav"},
        } if job_id == "job-stt" else None,
    )

    payload = workflow.execute(
        "run_full_annotation_pipeline",
        {"speaker_id": "Fail02", "concept_list": ["1"]},
    )["result"]

    assert payload["final_status"] == "error"
    assert payload["failedStep"] == "stt"
    assert payload["failedTool"] == "stt_status"
    assert payload["error"]["message"] == "decoder crash"
    assert payload["progress"]["completedStages"] == 0
    assert payload["progress"]["currentStage"] == "stt"
    assert payload["progress"]["done"] is False
    assert payload["events"][-1]["event"] == "stage_failed"


def test_prepare_compare_mode_builds_compare_bundle_from_selected_range(tmp_path: pathlib.Path) -> None:
    _write_concepts_csv(tmp_path)
    _seed_annotation(tmp_path, "Fail01", concepts=["1", "2", "3"])
    _seed_annotation(tmp_path, "Fail02", concepts=["1", "2", "3"])
    (tmp_path / "parse-enrichments.json").write_text("{}", encoding="utf-8")

    workflow = WorkflowTools(project_root=tmp_path)

    workflow._parse_tools._tool_cognate_compute_preview = lambda args: {
        "readOnly": True,
        "previewOnly": True,
        "summary": {"conceptCount": len(args["conceptIds"]), "speakerCount": len(args["speakers"]), "hasSimilarity": True},
        "enrichmentsPreview": {"config": {"concepts_included": list(args["conceptIds"])}},
    }
    workflow._parse_tools._tool_cross_speaker_match_preview = lambda args: {
        "readOnly": True,
        "previewOnly": True,
        "speaker": args["speaker"],
        "matches": [{"conceptId": "1", "score": 0.9}],
    }

    result = workflow.execute(
        "prepare_compare_mode",
        {"concept_range": "1-2", "speakers": ["Fail01", "Fail02"]},
    )
    payload = result["result"]

    assert payload["concept_ids"] == ["1", "2"]
    assert payload["speaker_count"] == 2
    assert set(payload["speaker_annotations"].keys()) == {"Fail01", "Fail02"}
    assert payload["compare_preview"]["summary"]["conceptCount"] == 2
    assert set(payload["cross_speaker_matches"].keys()) == {"Fail01", "Fail02"}


def test_export_complete_lingpy_dataset_chains_contact_lookup_and_exports(tmp_path: pathlib.Path) -> None:
    workflow = WorkflowTools(project_root=tmp_path)
    calls: List[Tuple[str, Dict[str, Any]]] = []

    workflow._parse_tools._tool_contact_lexeme_lookup = lambda args: calls.append(("contact_lexeme_lookup", dict(args))) or {
        "ok": True,
        "dryRun": args.get("dryRun", False),
        "configPath": str(tmp_path / "config" / "sil_contact_languages.json"),
    }
    workflow._parse_tools._tool_export_lingpy_tsv = lambda args: calls.append(("export_lingpy_tsv", dict(args))) or {
        "success": True,
        "outputPath": args["outputPath"],
        "rowCount": 12,
    }
    workflow._parse_tools._tool_export_nexus = lambda args: calls.append(("export_nexus", dict(args))) or {
        "success": True,
        "outputPath": args["outputPath"],
        "totalChars": 321,
    }

    result = workflow.execute(
        "export_complete_lingpy_dataset",
        {"with_contact_lexemes": True, "dryRun": False},
    )
    payload = result["result"]

    assert [name for name, _args in calls] == [
        "contact_lexeme_lookup",
        "export_lingpy_tsv",
        "export_nexus",
    ]
    assert calls[0][1]["dryRun"] is False
    assert calls[1][1]["outputPath"] == "exports/lingpy/wordlist.tsv"
    assert calls[2][1]["outputPath"] == "exports/lingpy/dataset.nex"
    assert payload["final_status"] == "complete"
    assert payload["artifacts"]["lingpy_tsv"] == "exports/lingpy/wordlist.tsv"
    assert payload["artifacts"]["nexus"] == "exports/lingpy/dataset.nex"


def test_workflow_tools_publish_metadata_for_macro_specs(tmp_path: pathlib.Path) -> None:
    workflow = WorkflowTools(project_root=tmp_path)

    annotation_spec = workflow.tool_spec("run_full_annotation_pipeline")
    assert annotation_spec.supports_dry_run is True
    assert annotation_spec.dry_run_parameter == "dryRun"
    assert any(cond.id == "project_loaded" for cond in annotation_spec.preconditions)

    compare_spec = workflow.tool_spec("prepare_compare_mode")
    assert compare_spec.mutability == "read_only"
    assert any(cond.id == "compare_inputs_available" for cond in compare_spec.postconditions)

    export_spec = workflow.tool_spec("export_complete_lingpy_dataset")
    assert export_spec.mutability == "mutating"
    assert any(cond.id == "export_bundle_written" for cond in export_spec.postconditions)

    assert workflow.tool_names() == [
        "export_complete_lingpy_dataset",
        "prepare_compare_mode",
        "run_full_annotation_pipeline",
    ]
