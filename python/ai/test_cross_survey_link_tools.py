from __future__ import annotations

import shutil
from pathlib import Path

from ai.chat_tools import REGISTRY, ParseChatTools

FIXTURE = Path(__file__).parents[1] / "test_fixtures" / "cross_survey_links_workspace"


def copy_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace)
    return workspace


def test_populate_cross_survey_links_tool_is_registered() -> None:
    assert "populate_cross_survey_links" in REGISTRY


def test_populate_cross_survey_links_tool_happy_path_dry_run(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    tools = ParseChatTools(project_root=workspace)

    result = tools.execute(
        "populate_cross_survey_links",
        {"referencePath": "reference.csv", "dryRun": True, "singleWordOnly": True},
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["dryRun"] is True
    assert payload["would_add"] == [
        {"concept_id": "1", "concept_en": "nose", "links": {"klq": "1.5"}},
        {"concept_id": "5", "concept_en": "stone", "links": {"klq": "5.0"}},
    ]
