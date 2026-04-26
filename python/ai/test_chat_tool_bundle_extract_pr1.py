from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools
from ai.tools.job_status_tools import JOB_STATUS_TOOL_HANDLERS, JOB_STATUS_TOOL_NAMES, JOB_STATUS_TOOL_SPECS
from ai.tools.preview_tools import PREVIEW_TOOL_HANDLERS, PREVIEW_TOOL_NAMES, PREVIEW_TOOL_SPECS
from ai.tools.project_read_tools import (
    PROJECT_READ_TOOL_HANDLERS,
    PROJECT_READ_TOOL_NAMES,
    PROJECT_READ_TOOL_SPECS,
)


def test_first_pr_tool_bundles_publish_matching_spec_and_handler_sets(tmp_path) -> None:
    bundles = [
        (set(PROJECT_READ_TOOL_NAMES), PROJECT_READ_TOOL_SPECS, PROJECT_READ_TOOL_HANDLERS),
        (set(PREVIEW_TOOL_NAMES), PREVIEW_TOOL_SPECS, PREVIEW_TOOL_HANDLERS),
        (set(JOB_STATUS_TOOL_NAMES), JOB_STATUS_TOOL_SPECS, JOB_STATUS_TOOL_HANDLERS),
    ]

    tools = ParseChatTools(project_root=tmp_path)

    for expected_names, specs, handlers in bundles:
        assert set(specs.keys()) == expected_names
        assert set(handlers.keys()) == expected_names
        for tool_name in expected_names:
            assert tool_name in tools.tool_names()
