from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools
from ai.tools.offset_apply_tools import (
    OFFSET_APPLY_TOOL_HANDLERS,
    OFFSET_APPLY_TOOL_NAMES,
    OFFSET_APPLY_TOOL_SPECS,
)
from ai.tools.offset_detection_tools import (
    OFFSET_DETECTION_TOOL_HANDLERS,
    OFFSET_DETECTION_TOOL_NAMES,
    OFFSET_DETECTION_TOOL_SPECS,
)


def test_third_pr_c_tool_bundles_publish_matching_spec_and_handler_sets(tmp_path) -> None:
    bundles = [
        (set(OFFSET_DETECTION_TOOL_NAMES), OFFSET_DETECTION_TOOL_SPECS, OFFSET_DETECTION_TOOL_HANDLERS),
        (set(OFFSET_APPLY_TOOL_NAMES), OFFSET_APPLY_TOOL_SPECS, OFFSET_APPLY_TOOL_HANDLERS),
    ]

    tools = ParseChatTools(project_root=tmp_path)

    for expected_names, specs, handlers in bundles:
        assert set(specs.keys()) == expected_names
        assert set(handlers.keys()) == expected_names
        for tool_name in expected_names:
            assert tool_name in tools.tool_names()
