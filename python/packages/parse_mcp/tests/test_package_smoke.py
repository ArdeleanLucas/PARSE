import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import parse_mcp


def test_package_exports_public_entrypoints() -> None:
    assert hasattr(parse_mcp, "ParseMcpClient")
    assert hasattr(parse_mcp, "build_langchain_tools")
    assert hasattr(parse_mcp, "build_llamaindex_tools")
    assert hasattr(parse_mcp, "build_crewai_tools")
