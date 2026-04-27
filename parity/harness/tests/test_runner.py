from __future__ import annotations

import json
from pathlib import Path

import pytest

from parity.harness.runner import (
    CanonicalizationContext,
    BootSmokeResult,
    DiffEntry,
    DiffReport,
    ROUND2_CONTRACT_GROUP_COVERAGE,
    ROUND2_FAILURE_CASES,
    ROUND2_JOB_LIFECYCLE_KEYS,
    SUPPORTED_FIXTURE_NAMES,
    ScenarioCapture,
    _extract_active_job_summary,
    build_diff_report,
    build_server_boot_smoke_blockers,
    build_signoff_payload,
    compare_capture_sections,
    load_allowlist_rules,
    normalize_for_diff,
    prepare_fixture_bundle,
    render_markdown_report,
)


def _context() -> CanonicalizationContext:
    return CanonicalizationContext(
        repo_roots={
            "oracle": Path("/tmp/oracle-repo"),
            "rebuild": Path("/tmp/rebuild-repo"),
        },
        workspace_roots={
            "oracle": Path("/tmp/oracle-workspace"),
            "rebuild": Path("/tmp/rebuild-workspace"),
        },
    )


def test_normalize_for_diff_scrubs_job_ids_uuid_timestamps_paths_and_rounds_floats() -> None:
    payload = {
        "jobId": "job-123",
        "job_id": "job-123",
        "startedAt": "2026-04-26T22:15:00.123456+00:00",
        "modified": "2026-04-26T22:15:01Z",
        "uuid": "2b7d31f0-65ec-4b4f-a421-6c1d640c4ac3",
        "source_audio": "/tmp/oracle-workspace/audio/original/Base01/source.wav",
        "duration": 0.123456789,
        "nested": [
            {
                "completed_at": "2026-04-26T22:15:02Z",
                "path": "C:\\tmp\\oracle-workspace\\annotations\\Base01.parse.json",
            }
        ],
    }

    assert normalize_for_diff(payload, context=_context()) == {
        "duration": 0.123457,
        "jobId": "<job-id>",
        "job_id": "<job-id>",
        "modified": "<timestamp>",
        "nested": [
            {
                "completed_at": "<timestamp>",
                "path": "C:<workspace>/annotations/Base01.parse.json",
            }
        ],
        "source_audio": "<workspace>/audio/original/Base01/source.wav",
        "startedAt": "<timestamp>",
        "uuid": "<uuid>",
    }


def test_normalize_for_diff_sorts_only_order_insensitive_lists() -> None:
    payload = {
        "tags": [
            {"id": "tag-b", "label": "Beta", "concepts": ["3", "1"]},
            {"id": "tag-a", "label": "Alpha", "concepts": ["2", "1"]},
        ],
        "states": ["queued", "running", "error"],
        "source_wavs": [
            {"filename": "audio/original/B.wav", "is_primary": False},
            {"filename": "audio/original/A.wav", "is_primary": True},
        ],
        "intervals": [
            {"start": 0.2, "end": 0.4, "text": "later"},
            {"start": 0.0, "end": 0.1, "text": "earlier"},
        ],
    }

    normalized = normalize_for_diff(payload, context=_context())

    assert [tag["id"] for tag in normalized["tags"]] == ["tag-a", "tag-b"]
    assert normalized["tags"][0]["concepts"] == ["1", "2"]
    assert [wav["filename"] for wav in normalized["source_wavs"]] == [
        "audio/original/A.wav",
        "audio/original/B.wav",
    ]
    assert normalized["states"] == ["queued", "running", "error"]
    assert [interval["text"] for interval in normalized["intervals"]] == ["later", "earlier"]


def test_prepare_fixture_bundle_seeds_multispeaker_workspace_and_inputs(tmp_path: Path) -> None:
    fixture = prepare_fixture_bundle(tmp_path, fixture_name="saha-2speaker")

    assert "saha-2speaker" in SUPPORTED_FIXTURE_NAMES
    project = json.loads((fixture.workspace_root / "project.json").read_text(encoding="utf-8"))
    assert project["project_id"] == "parse-parity-fixture"
    assert sorted(project["speakers"].keys()) == ["Base01", "Base02"]
    assert project["concepts"]["source"] == "concepts.csv"

    concepts_csv = (fixture.workspace_root / "concepts.csv").read_text(encoding="utf-8")
    assert concepts_csv.startswith("id,concept_en")
    assert "1,ash" in concepts_csv

    source_index = json.loads((fixture.workspace_root / "source_index.json").read_text(encoding="utf-8"))
    assert sorted(source_index["speakers"].keys()) == ["Base01", "Base02"]

    assert fixture.seed_speaker_id == "Base01"
    assert fixture.compare_speaker_id == "Base02"
    assert (fixture.workspace_root / "annotations" / "Base01.parse.json").exists()
    assert (fixture.workspace_root / "annotations" / "Base02.parse.json").exists()
    assert (fixture.workspace_root / "audio" / "original" / "Base01" / "source.wav").exists()
    assert (fixture.workspace_root / "audio" / "original" / "Base02" / "source.wav").exists()
    assert (fixture.input_root / "onboard" / "Parity01.wav").exists()
    assert (fixture.input_root / "concepts-import.csv").read_text(encoding="utf-8").startswith("id,concept_en")
    assert (fixture.input_root / "tags-import.csv").read_text(encoding="utf-8").startswith("concept_en")

    with pytest.raises(ValueError, match="Unknown fixture"):
        prepare_fixture_bundle(tmp_path / "other", fixture_name="does-not-exist")


def test_load_allowlist_rules_rejects_todo_reasons(tmp_path: Path) -> None:
    allowlist_path = tmp_path / "allowlist.yaml"
    allowlist_path.write_text(
        """
version: 1
rules:
  - id: TODO-rule
    section: exports
    path: $.exports.nexus
    permanence: permanent
    classification: intentional
    reason: "TODO: fill this in"
    reason_ref: parity/deviations.md#todo
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="TODO"):
        load_allowlist_rules(allowlist_path)


def test_extract_active_job_summary_matches_target_job_and_strips_runtime_noise() -> None:
    summary = _extract_active_job_summary(
        {
            "status": 200,
            "body": {
                "jobs": [
                    {
                        "jobId": "job-123",
                        "type": "normalize",
                        "status": "running",
                        "speaker": "Base01",
                        "message": "Starting compute job",
                        "progress": 5.0,
                        "result": {"ignored": True},
                        "locks": {
                            "resources": [{"kind": "speaker", "id": "Base01"}],
                            "ttl_seconds": 600,
                        },
                    }
                ]
            },
        },
        "job-123",
    )

    assert summary == {
        "status": 200,
        "body": {
            "job": {
                "jobId": "job-123",
                "locks": {
                    "resources": [{"kind": "speaker", "id": "Base01"}],
                    "ttl_seconds": 600,
                },
                "speaker": "Base01",
                "status": "running",
                "type": "normalize",
            }
        },
    }
    assert _extract_active_job_summary({"status": 200, "body": {"jobs": []}}, "missing") is None


def test_round2_coverage_matrix_tracks_all_inventory_groups_and_required_failures() -> None:
    assert set(ROUND2_CONTRACT_GROUP_COVERAGE) == {
        "annotation_data",
        "project_config_and_pipeline_state",
        "enrichments_tags_notes_imports",
        "auth",
        "stt_normalize_onboard",
        "offset_tools",
        "suggestions_lexeme_search",
        "chat_and_generic_compute",
        "job_observability",
        "export_and_media",
        "clef_contact_lexeme",
    }
    assert set(ROUND2_FAILURE_CASES) >= {
        "annotation_save_invalid",
        "annotation_get_missing",
        "clef_config_invalid",
        "lingpy_empty_wordlist",
        "nexus_empty_wordlist",
    }
    assert set(ROUND2_JOB_LIFECYCLE_KEYS) >= {
        "stt",
        "normalize",
        "full_pipeline",
        "onboard",
        "offset_detect_from_pair",
    }
    assert set(ROUND2_CONTRACT_GROUP_COVERAGE["job_observability"]) >= {
        "jobs_list",
        "jobs_active",
    }


def test_server_boot_smoke_failures_are_reported_as_real_blockers() -> None:
    blockers = build_server_boot_smoke_blockers(
        {
            "oracle": BootSmokeResult(repo_label="oracle", success=True, port=8766, detail="booted", log_path=Path("/tmp/oracle.log")),
            "rebuild": BootSmokeResult(
                repo_label="rebuild",
                success=False,
                port=8766,
                detail="NameError: _api_get_annotation is not defined",
                log_path=Path("/tmp/rebuild.log"),
            ),
        }
    )

    assert len(blockers) == 1
    assert blockers[0].section == "server_boot_smoke"
    assert blockers[0].path == "$.server_boot_smoke.rebuild"
    assert blockers[0].oracle_value == {"expected": "boot success"}
    assert blockers[0].rebuild_value["success"] is False


def test_build_signoff_payload_captures_repo_shas_counts_and_boot_results() -> None:
    payload = build_signoff_payload(
        fixture_name="saha-2speaker",
        oracle_repo=Path("/repos/oracle"),
        rebuild_repo=Path("/repos/rebuild"),
        oracle_sha="abc123",
        rebuild_sha="def456",
        report=DiffReport(raw_diffs=[], allowlisted_diffs=[], unallowlisted_diffs=[], raw_diff_count=0, allowlisted_diff_count=0, unallowlisted_diff_count=0),
        server_boot_results={
            "oracle": BootSmokeResult(repo_label="oracle", success=True, port=8766, detail="booted", log_path=Path("/tmp/oracle.log")),
            "rebuild": BootSmokeResult(repo_label="rebuild", success=False, port=8766, detail="blocked", log_path=Path("/tmp/rebuild.log")),
        },
    )

    assert payload["fixture"] == "saha-2speaker"
    assert payload["repos"]["oracle"]["sha"] == "abc123"
    assert payload["repos"]["rebuild"]["sha"] == "def456"
    assert payload["diff_counts"] == {"raw": 0, "allowlisted": 0, "unallowlisted": 0}
    assert payload["server_boot_smoke"]["oracle"]["success"] is True
    assert payload["server_boot_smoke"]["rebuild"]["success"] is False


def test_compare_capture_sections_returns_path_level_diffs() -> None:
    oracle = ScenarioCapture(
        label="oracle",
        api={"config": {"status": 200, "body": {"jobId": "job-1", "status": "done"}}},
        job_lifecycles={"onboard": {"states": ["running", "done"]}},
        exports={"lingpy": "A\n", "nexus": "#NEXUS\nA\n"},
        persisted_json={"source_index.json": {"speakers": {"Imp01": {"path": "/tmp/oracle-workspace/audio/orig.wav"}}}},
    )
    rebuild = ScenarioCapture(
        label="rebuild",
        api={"config": {"status": 200, "body": {"jobId": "job-9", "status": "error"}}},
        job_lifecycles={"onboard": {"states": ["running", "done"]}},
        exports={"lingpy": "B\n", "nexus": "#NEXUS\nA\n"},
        persisted_json={"source_index.json": {"speakers": {"Imp01": {"path": "/tmp/rebuild-workspace/audio/orig.wav"}}}},
    )

    diffs = compare_capture_sections(oracle, rebuild, context=_context())

    assert {(entry.section, entry.path) for entry in diffs} == {
        ("api", "$.api.config.body.status"),
        ("exports", "$.exports.lingpy"),
    }


def test_build_diff_report_separates_allowlisted_and_unallowlisted_diffs(tmp_path: Path) -> None:
    allowlist_path = tmp_path / "allowlist.yaml"
    allowlist_path.write_text(
        """
version: 1
rules:
  - id: perm-lingpy-fixture
    section: exports
    path: $.exports.lingpy
    permanence: permanent
    classification: intentional
    reason: Fixture TSV newline variance is intentionally ignored.
    reason_ref: parity/deviations.md#perm-lingpy-fixture
""".strip()
        + "\n",
        encoding="utf-8",
    )

    oracle = ScenarioCapture(
        label="oracle",
        api={"config": {"status": 200, "body": {"status": "done"}}},
        job_lifecycles={},
        exports={"lingpy": "A\n"},
        persisted_json={},
    )
    rebuild = ScenarioCapture(
        label="rebuild",
        api={"config": {"status": 200, "body": {"status": "error"}}},
        job_lifecycles={},
        exports={"lingpy": "B\n"},
        persisted_json={},
    )

    report = build_diff_report(
        oracle,
        rebuild,
        context=_context(),
        allowlist_rules=load_allowlist_rules(allowlist_path),
    )

    assert report.raw_diff_count == 2
    assert report.allowlisted_diff_count == 1
    assert report.unallowlisted_diff_count == 1
    assert report.allowlisted_diffs[0].allowlist_rule_id == "perm-lingpy-fixture"
    assert report.unallowlisted_diffs[0].path == "$.api.config.body.status"


def test_render_markdown_report_summarizes_allowlisted_and_unallowlisted_diff_entries() -> None:
    oracle = ScenarioCapture(label="oracle", api={}, job_lifecycles={}, exports={}, persisted_json={})
    rebuild = ScenarioCapture(label="rebuild", api={}, job_lifecycles={}, exports={}, persisted_json={})
    report = DiffReport(
        raw_diffs=[
            DiffEntry(
                section="persisted_json",
                path="$.persisted_json.source_index.json.speakers.Base01.path",
                oracle_value="audio\\orig.wav",
                rebuild_value="audio/orig.wav",
                allowlist_rule_id=None,
                classification=None,
                permanence=None,
                reason=None,
                reason_ref=None,
            ),
            DiffEntry(
                section="exports",
                path="$.exports.lingpy",
                oracle_value="A\n",
                rebuild_value="B\n",
                allowlist_rule_id="perm-lingpy-fixture",
                classification="intentional",
                permanence="permanent",
                reason="Fixture TSV newline variance is intentionally ignored.",
                reason_ref="parity/deviations.md#perm-lingpy-fixture",
            ),
        ],
        allowlisted_diffs=[],
        unallowlisted_diffs=[],
    ).finalize()

    markdown = render_markdown_report(oracle, rebuild, report)

    assert "Raw diff count: **2**" in markdown
    assert "Allowlisted diff count: **1**" in markdown
    assert "Remaining unallowlisted diff count: **1**" in markdown
    assert "perm-lingpy-fixture" in markdown
    assert "Fixture TSV newline variance is intentionally ignored." in markdown
    assert "$.persisted_json.source_index.json.speakers.Base01.path" in markdown
