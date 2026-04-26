from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools
from ai.tools.memory_tools import (
    MEMORY_TOOL_HANDLERS,
    MEMORY_TOOL_NAMES,
    MEMORY_TOOL_SPECS,
)
from ai.tools.tag_import_tools import (
    TAG_IMPORT_TOOL_HANDLERS,
    TAG_IMPORT_TOOL_NAMES,
    TAG_IMPORT_TOOL_SPECS,
)


def test_third_pr_a_tool_bundles_publish_matching_spec_and_handler_sets(tmp_path) -> None:
    bundles = [
        (set(TAG_IMPORT_TOOL_NAMES), TAG_IMPORT_TOOL_SPECS, TAG_IMPORT_TOOL_HANDLERS),
        (set(MEMORY_TOOL_NAMES), MEMORY_TOOL_SPECS, MEMORY_TOOL_HANDLERS),
    ]

    tools = ParseChatTools(project_root=tmp_path)

    for expected_names, specs, handlers in bundles:
        assert set(specs.keys()) == expected_names
        assert set(handlers.keys()) == expected_names
        for tool_name in expected_names:
            assert tool_name in tools.tool_names()
