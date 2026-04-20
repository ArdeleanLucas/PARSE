"""Cross-check MCP tool registrations against ParseChatTools.

Prevents phantom-tool regressions — the MCP adapter forwards every call
through ParseChatTools.execute(), so registering an MCP tool that isn't
in the allowlist produces a runtime ChatToolValidationError on the
client side. A test at import time catches that before shipping.
"""
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ai.chat_tools import ParseChatTools


def _has_mcp() -> bool:
    try:
        import mcp.server.fastmcp  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_every_mcp_tool_is_allowlisted_in_parse_chat_tools(tmp_path) -> None:
    import asyncio

    from adapters.mcp_adapter import create_mcp_server

    # Minimal project root — the tools only need the path to exist; individual
    # tool calls exercise filesystem paths but this test only lists tools.
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    mcp_names = {t.name for t in mcp_tools}

    chat_names = set(ParseChatTools(project_root=tmp_path).tool_names())

    phantom = mcp_names - chat_names
    assert not phantom, (
        "MCP tools that are NOT in ParseChatTools.tool_names() will raise "
        "ChatToolValidationError at runtime. Phantom tools: {0}".format(sorted(phantom))
    )


def test_contact_lexeme_lookup_is_allowlisted(tmp_path) -> None:
    """contact_lexeme_lookup specifically — the bug that motivated this test."""
    tools = ParseChatTools(project_root=tmp_path)
    assert "contact_lexeme_lookup" in tools.tool_names()


def test_contact_lexeme_lookup_is_read_only_via_schema(tmp_path) -> None:
    """Tool should be schema-clean and not expose an 'overwrite' mutation lever."""
    tools = ParseChatTools(project_root=tmp_path)
    spec = tools._tool_specs["contact_lexeme_lookup"]
    assert "overwrite" not in spec.parameters.get("properties", {})
    assert spec.parameters.get("additionalProperties") is False
