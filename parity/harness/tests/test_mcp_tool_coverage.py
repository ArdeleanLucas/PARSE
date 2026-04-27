from __future__ import annotations

from pathlib import Path
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
PYTHON_DIR = ROOT / "python"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from ai.chat_tools import REGISTRY
from ai.workflow_tools import DEFAULT_MCP_WORKFLOW_TOOL_NAMES
from parity.harness.runner import ScenarioCapture, compare_capture_sections
from parity.harness.diff.mcp_tools import (
    ALL_TARGET_TOOL_NAMES,
    PARITY_EXTRA_CHAT_TOOL_NAMES,
    list_chat_tool_fixture_names,
    list_workflow_tool_fixture_names,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "mcp-tool-payloads"


def test_chat_tool_fixtures_cover_registry_and_bnd_port_wave_extras() -> None:
    assert FIXTURE_DIR.exists()
    fixture_names = set(list_chat_tool_fixture_names(FIXTURE_DIR))
    assert set(REGISTRY).issubset(fixture_names)
    assert set(PARITY_EXTRA_CHAT_TOOL_NAMES).issubset(fixture_names)



def test_all_target_tool_names_include_bnd_port_wave_extras() -> None:
    assert set(PARITY_EXTRA_CHAT_TOOL_NAMES).issubset(set(ALL_TARGET_TOOL_NAMES))



def test_workflow_tool_fixture_count_matches_workflow_registry() -> None:
    assert len(list_workflow_tool_fixture_names(FIXTURE_DIR)) == len(DEFAULT_MCP_WORKFLOW_TOOL_NAMES)



def test_compare_capture_sections_includes_mcp_tools() -> None:
    oracle = ScenarioCapture(
        label="oracle",
        api={},
        job_lifecycles={},
        exports={},
        persisted_json={},
        mcp_tools={"tools": {"annotation_read": {"success": {"ok": True}}}},
    )
    rebuild = ScenarioCapture(
        label="rebuild",
        api={},
        job_lifecycles={},
        exports={},
        persisted_json={},
        mcp_tools={"tools": {"annotation_read": {"success": {"ok": False}}}},
    )

    diffs = compare_capture_sections(oracle, rebuild)
    assert any(diff.section == "mcp_tools" for diff in diffs)
    assert any(diff.path == "$.mcp_tools.tools.annotation_read.success.ok" for diff in diffs)
