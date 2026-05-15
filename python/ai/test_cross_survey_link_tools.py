from __future__ import annotations

import shutil
from pathlib import Path

from ai.chat_tools import REGISTRY, ParseChatTools
from survey_overlap import load_survey_overlap_state, update_survey_overlap_state

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
        {"concept_id": "2", "concept_en": "father (vocative)", "links": {"klq": "2.5"}},
        {"concept_id": "5", "concept_en": "stone", "links": {"klq": "5.0"}},
    ]


def test_populate_cross_survey_links_tool_replace_mode(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    update_survey_overlap_state(
        workspace,
        {
            "concept_survey_links": {"99": {"jbil": "999"}},
            "speaker_choices": {"speaker-a": {"1": "jbil"}},
        },
    )
    tools = ParseChatTools(project_root=workspace)

    result = tools.execute(
        "populate_cross_survey_links",
        {"referencePath": "reference.csv", "dryRun": False, "singleWordOnly": True, "replace": True},
    )
    state = load_survey_overlap_state(workspace)

    assert result["ok"] is True
    payload = result["result"]
    assert payload["dryRun"] is False
    assert payload["sidecar_diff"]["replace_mode"] is True
    assert payload["sidecar_diff"]["added"] == {"1": {"klq": "1.5"}, "2": {"klq": "2.5"}, "5": {"klq": "5.0"}}
    assert state["concept_survey_links"] == {"1": {"klq": "1.5"}, "2": {"klq": "2.5"}, "5": {"klq": "5.0"}}
    assert state["speaker_choices"] == {"speaker-a": {"1": "jbil"}}
