from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai.chat_tools import (
    DEFAULT_MCP_HOLD_BACK_TOOL_NAMES,
    DEFAULT_MCP_TOOL_NAMES,
    LEGACY_CURATED_MCP_TOOL_NAMES,
    REGISTRY,
)


def test_default_mcp_tool_names_lock_full_safe_surface() -> None:
    assert len(LEGACY_CURATED_MCP_TOOL_NAMES) == 38
    assert len(DEFAULT_MCP_TOOL_NAMES) == 57
    assert set(LEGACY_CURATED_MCP_TOOL_NAMES) < set(DEFAULT_MCP_TOOL_NAMES)
    assert len(set(DEFAULT_MCP_TOOL_NAMES)) == len(DEFAULT_MCP_TOOL_NAMES)


def test_default_mcp_tool_names_cover_registry_except_documented_hold_backs() -> None:
    registry_names = set(REGISTRY.keys())
    default_names = set(DEFAULT_MCP_TOOL_NAMES)
    hold_back_names = set(DEFAULT_MCP_HOLD_BACK_TOOL_NAMES)

    assert hold_back_names <= registry_names
    assert registry_names - default_names == hold_back_names
