from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools
from ai.tools.artifact_tools import ARTIFACT_TOOL_HANDLERS, ARTIFACT_TOOL_NAMES, ARTIFACT_TOOL_SPECS
from ai.tools.comparative_tools import COMPARATIVE_TOOL_HANDLERS, COMPARATIVE_TOOL_NAMES, COMPARATIVE_TOOL_SPECS
from ai.tools.contact_lexeme_tools import CONTACT_LEXEME_TOOL_HANDLERS, CONTACT_LEXEME_TOOL_NAMES, CONTACT_LEXEME_TOOL_SPECS
from ai.tools.enrichment_tools import ENRICHMENT_TOOL_HANDLERS, ENRICHMENT_TOOL_NAMES, ENRICHMENT_TOOL_SPECS
from ai.tools.export_tools import EXPORT_TOOL_HANDLERS, EXPORT_TOOL_NAMES, EXPORT_TOOL_SPECS
from ai.tools.transform_tools import TRANSFORM_TOOL_HANDLERS, TRANSFORM_TOOL_NAMES, TRANSFORM_TOOL_SPECS


def test_fourth_pr_tool_bundles_publish_matching_spec_and_handler_sets(tmp_path) -> None:
    bundles = [
        (set(COMPARATIVE_TOOL_NAMES), COMPARATIVE_TOOL_SPECS, COMPARATIVE_TOOL_HANDLERS),
        (set(CONTACT_LEXEME_TOOL_NAMES), CONTACT_LEXEME_TOOL_SPECS, CONTACT_LEXEME_TOOL_HANDLERS),
        (set(ENRICHMENT_TOOL_NAMES), ENRICHMENT_TOOL_SPECS, ENRICHMENT_TOOL_HANDLERS),
        (set(EXPORT_TOOL_NAMES), EXPORT_TOOL_SPECS, EXPORT_TOOL_HANDLERS),
        (set(TRANSFORM_TOOL_NAMES), TRANSFORM_TOOL_SPECS, TRANSFORM_TOOL_HANDLERS),
        (set(ARTIFACT_TOOL_NAMES), ARTIFACT_TOOL_SPECS, ARTIFACT_TOOL_HANDLERS),
    ]

    tools = ParseChatTools(project_root=tmp_path)

    for expected_names, specs, handlers in bundles:
        assert set(specs.keys()) == expected_names
        assert set(handlers.keys()) == expected_names
        for tool_name in expected_names:
            assert tool_name in tools.tool_names()
