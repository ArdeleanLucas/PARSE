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


def test_build_langchain_tools_uses_discovery_schema_and_delegates_calls(monkeypatch) -> None:
    fake_tools_mod = types.ModuleType("langchain_core.tools")

    class FakeStructuredTool:
        def __init__(self, func, name, description, args_schema):
            self.func = func
            self.name = name
            self.description = description
            self.args_schema = args_schema

        @classmethod
        def from_function(cls, func=None, name=None, description=None, args_schema=None, coroutine=None):
            return cls(func, name, description, args_schema)

    fake_tools_mod.StructuredTool = FakeStructuredTool
    fake_root_mod = types.ModuleType("langchain_core")
    fake_root_mod.tools = fake_tools_mod
    monkeypatch.setitem(sys.modules, "langchain_core", fake_root_mod)
    monkeypatch.setitem(sys.modules, "langchain_core.tools", fake_tools_mod)

    from parse_mcp.langchain import build_langchain_tools

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

    tools = build_langchain_tools(client)

    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "project_context_read"
    assert tool.args_schema is not None
    result = tool.func(include=["project"])
    assert result["ok"] is True
    assert client.calls == [("project_context_read", {"include": ["project"]})]
