from __future__ import annotations

import json
from pathlib import Path

from parity.harness.runner import (
    DiffEntry,
    ScenarioCapture,
    compare_capture_sections,
    normalize_for_diff,
    prepare_fixture_bundle,
    render_markdown_report,
)


def test_normalize_for_diff_scrubs_job_ids_and_timestamps() -> None:
    payload = {
        "jobId": "job-123",
        "job_id": "job-123",
        "startedAt": "2026-04-26T22:15:00Z",
        "modified": "2026-04-26T22:15:01Z",
        "nested": [{"completed_at": "2026-04-26T22:15:02Z", "speaker": "Imp01"}],
    }

    assert normalize_for_diff(payload) == {
        "jobId": "<job-id>",
        "job_id": "<job-id>",
        "startedAt": "<timestamp>",
        "modified": "<timestamp>",
        "nested": [{"completed_at": "<timestamp>", "speaker": "Imp01"}],
    }


def test_prepare_fixture_bundle_seeds_workspace_and_inputs(tmp_path: Path) -> None:
    fixture = prepare_fixture_bundle(tmp_path)

    project = json.loads((fixture.workspace_root / "project.json").read_text(encoding="utf-8"))
    assert project["project_id"] == "parse-parity-fixture"

    source_index = json.loads((fixture.workspace_root / "source_index.json").read_text(encoding="utf-8"))
    assert source_index["speakers"]["Base01"]["source_wavs"][0]["filename"] == "audio/original/Base01/source.wav"

    assert fixture.seed_speaker_id == "Base01"
    assert (fixture.workspace_root / "annotations" / "Base01.parse.json").exists()
    assert (fixture.workspace_root / "audio" / "original" / "Base01" / "source.wav").exists()
    assert (fixture.input_root / "onboard" / "Parity01.wav").exists()
    assert (fixture.input_root / "concepts-import.csv").read_text(encoding="utf-8").startswith("id,concept_en")
    assert (fixture.input_root / "tags-import.csv").read_text(encoding="utf-8").startswith("concept_en")


def test_compare_capture_sections_reports_api_export_and_persisted_diffs() -> None:
    oracle = ScenarioCapture(
        label="oracle",
        api={"config": {"status": 200, "body": {"jobId": "job-1", "status": "done"}}},
        job_lifecycles={"onboard": {"states": ["running", "done"]}},
        exports={"lingpy": "A\n", "nexus": "#NEXUS\nA\n"},
        persisted_json={"source_index.json": {"speakers": {"Imp01": {"path": "audio\\orig.wav"}}}},
    )
    rebuild = ScenarioCapture(
        label="rebuild",
        api={"config": {"status": 200, "body": {"jobId": "job-9", "status": "done"}}},
        job_lifecycles={"onboard": {"states": ["running", "done"]}},
        exports={"lingpy": "B\n", "nexus": "#NEXUS\nA\n"},
        persisted_json={"source_index.json": {"speakers": {"Imp01": {"path": "audio/orig.wav"}}}},
    )

    diffs = compare_capture_sections(oracle, rebuild)

    assert [entry.section for entry in diffs] == ["exports", "persisted_json"]
    assert diffs[0].key == "lingpy"
    assert diffs[1].key == "source_index.json"


def test_render_markdown_report_summarizes_diff_entries() -> None:
    oracle = ScenarioCapture(label="oracle", api={}, job_lifecycles={}, exports={}, persisted_json={})
    rebuild = ScenarioCapture(label="rebuild", api={}, job_lifecycles={}, exports={}, persisted_json={})
    diffs = [
        DiffEntry(
            section="persisted_json",
            key="source_index.json",
            oracle_value={"path": "audio\\orig.wav"},
            rebuild_value={"path": "audio/orig.wav"},
        )
    ]

    markdown = render_markdown_report(oracle, rebuild, diffs)

    assert "# PARSE parity diff harness report" in markdown
    assert "Current diff count: **1**" in markdown
    assert "source_index.json" in markdown
    assert "audio\\\\orig.wav" in markdown
    assert "audio/orig.wav" in markdown
