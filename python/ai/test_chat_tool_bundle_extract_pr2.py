from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools
from ai.tools.acoustic_starter_tools import (
    ACOUSTIC_STARTER_TOOL_HANDLERS,
    ACOUSTIC_STARTER_TOOL_NAMES,
    ACOUSTIC_STARTER_TOOL_SPECS,
)
from ai.tools.pipeline_orchestration_tools import (
    PIPELINE_ORCHESTRATION_TOOL_HANDLERS,
    PIPELINE_ORCHESTRATION_TOOL_NAMES,
    PIPELINE_ORCHESTRATION_TOOL_SPECS,
)


def test_second_pr_tool_bundles_publish_matching_spec_and_handler_sets(tmp_path) -> None:
    bundles = [
        (
            set(ACOUSTIC_STARTER_TOOL_NAMES),
            ACOUSTIC_STARTER_TOOL_SPECS,
            ACOUSTIC_STARTER_TOOL_HANDLERS,
        ),
        (
            set(PIPELINE_ORCHESTRATION_TOOL_NAMES),
            PIPELINE_ORCHESTRATION_TOOL_SPECS,
            PIPELINE_ORCHESTRATION_TOOL_HANDLERS,
        ),
    ]

    tools = ParseChatTools(project_root=tmp_path)

    for expected_names, specs, handlers in bundles:
        assert set(specs.keys()) == expected_names
        assert set(handlers.keys()) == expected_names
        for tool_name in expected_names:
            assert tool_name in tools.tool_names()
