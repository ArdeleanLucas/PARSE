import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from parse_mcp.models import ParseToolSpec, ParseToolAnnotations, ParseToolMeta


class _FakeClient:
    def __init__(self, spec):
        self.spec = spec
        self.calls = []

    def list_tools(self, mode="active"):
        return [self.spec]

    def call_tool(self, tool_name, arguments=None):
        self.calls.append((tool_name, arguments or {}))
        return {"tool": tool_name, "ok": True, "arguments": arguments or {}}


def test_build_crewai_tools_uses_discovery_schema_and_delegates_calls(monkeypatch) -> None:
    fake_tools_mod = types.ModuleType("crewai.tools")

    class FakeBaseTool:
        name = ""
        description = ""
        args_schema = None

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    fake_tools_mod.BaseTool = FakeBaseTool
    fake_root_mod = types.ModuleType("crewai")
    fake_root_mod.tools = fake_tools_mod
    monkeypatch.setitem(sys.modules, "crewai", fake_root_mod)
    monkeypatch.setitem(sys.modules, "crewai.tools", fake_tools_mod)

    from parse_mcp.crewai import build_crewai_tools

    spec = ParseToolSpec(
        name="project_context_read",
        family="chat",
        description="Read project context.",
        parameters={
            "type": "object",
            "properties": {
                "include": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        annotations=ParseToolAnnotations(readOnlyHint=True),
        meta=ParseToolMeta(x_parse={"mutability": "read_only", "supports_dry_run": False, "preconditions": [], "postconditions": []}),
    )
    client = _FakeClient(spec)

    tools = build_crewai_tools(client)

    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "project_context_read"
    assert tool.args_schema is not None
    result = tool._run(include=["project"])
    assert result["ok"] is True
    assert client.calls == [("project_context_read", {"include": ["project"]})]
