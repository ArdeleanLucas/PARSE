from __future__ import annotations

import csv
import json
from pathlib import Path

from ai.chat_tools import DEFAULT_MCP_TOOL_NAMES, LEGACY_CURATED_MCP_TOOL_NAMES, REGISTRY, ParseChatTools


def _write_polluted_workspace(workspace: Path) -> None:
    (workspace / "annotations").mkdir(parents=True)
    (workspace / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "53,big (A),F01,Fail01,1\n"
        "634,big,F01,Fail01,2\n",
        encoding="utf-8",
    )
    (workspace / "annotations" / "Fail01.parse.json").write_text(
        json.dumps({"tiers": {"concept": {"intervals": [
            {"start": 0, "end": 1, "text": "big (B)", "concept_id": "634"}
        ]}}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (workspace / "parse-tags.json").write_text(
        json.dumps([{"id": "custom-sk-concept-list", "concepts": ["53", "634"]}], indent=2) + "\n",
        encoding="utf-8",
    )


def test_migration_tool_is_registered_for_default_mcp_surface() -> None:
    assert "migrate_concept_suffix_pollution" in REGISTRY
    assert "migrate_concept_suffix_pollution" in LEGACY_CURATED_MCP_TOOL_NAMES
    assert "migrate_concept_suffix_pollution" in DEFAULT_MCP_TOOL_NAMES


def test_migration_tool_dry_run_returns_structured_summary(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_polluted_workspace(workspace)

    payload = ParseChatTools(project_root=tmp_path).execute(
        "migrate_concept_suffix_pollution",
        {"workspace": str(workspace), "dryRun": True},
    )

    result = payload["result"]
    assert payload["ok"] is True
    assert result["dryRun"] is True
    assert result["mergeMapCount"] == 1
    assert result["mergeMap"] == {"634": "53"}
    assert result["backups"] == []
    rows = list(csv.DictReader((workspace / "concepts.csv").open(encoding="utf-8-sig")))
    assert {row["id"] for row in rows} == {"53", "634"}


def test_migration_tool_verify_only_reports_audit_payload(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_polluted_workspace(workspace)

    payload = ParseChatTools(project_root=tmp_path).execute(
        "migrate_concept_suffix_pollution",
        {"workspace": str(workspace), "verifyOnly": True},
    )

    result = payload["result"]
    assert result["ok"] is False
    assert any("suffix" in item for item in result["postMigrationViolations"])
    assert result["crossSurveyLinkViolations"] == []


def test_migration_tool_rejects_missing_workspace(tmp_path: Path) -> None:
    payload = ParseChatTools(project_root=tmp_path).execute(
        "migrate_concept_suffix_pollution",
        {"workspace": str(tmp_path / "missing"), "dryRun": True},
    )

    result = payload["result"]
    assert result["ok"] is False
    assert result["errorKind"] == "invalid_args"
    assert "workspace path does not exist" in result["error"]
