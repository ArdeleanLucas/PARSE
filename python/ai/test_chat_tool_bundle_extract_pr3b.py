from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools
from ai.tools.speaker_import_tools import (
    SPEAKER_IMPORT_TOOL_HANDLERS,
    SPEAKER_IMPORT_TOOL_NAMES,
    SPEAKER_IMPORT_TOOL_SPECS,
)


def test_third_pr_b_tool_bundle_publishes_matching_spec_and_handler_sets(tmp_path) -> None:
    expected_names = set(SPEAKER_IMPORT_TOOL_NAMES)
    tools = ParseChatTools(project_root=tmp_path)

    assert set(SPEAKER_IMPORT_TOOL_SPECS.keys()) == expected_names
    assert set(SPEAKER_IMPORT_TOOL_HANDLERS.keys()) == expected_names
    for tool_name in expected_names:
        assert tool_name in tools.tool_names()
