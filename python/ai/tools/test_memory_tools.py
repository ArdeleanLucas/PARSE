from __future__ import annotations

import pathlib
import sys
from types import MethodType

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools.memory_tools import tool_parse_memory_read, tool_parse_memory_upsert_section


def test_tool_parse_memory_upsert_and_read_round_trip_directly(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    def _display_override(self, path):
        return "memory/parse-memory.md"

    tools._display_readable_path = MethodType(_display_override, tools)

    upsert = tool_parse_memory_upsert_section(
        tools,
        {"section": "Speakers", "body": "- Faili01", "dryRun": False},
    )

    assert upsert["ok"] is True
    assert upsert["path"] == "memory/parse-memory.md"
    assert upsert["action"] == "create"

    read_back = tool_parse_memory_read(tools, {"section": "Speakers"})
    assert read_back["ok"] is True
    assert read_back["path"] == "memory/parse-memory.md"
    assert "## Speakers" in read_back["content"]
    assert "- Faili01" in read_back["content"]


def test_tool_parse_memory_upsert_dry_run_does_not_write_directly(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    preview = tool_parse_memory_upsert_section(
        tools,
        {"section": "Notes", "body": "hello", "dryRun": True},
    )

    assert preview["ok"] is True
    assert preview["dryRun"] is True
    assert not (tmp_path / "parse-memory.md").exists()
