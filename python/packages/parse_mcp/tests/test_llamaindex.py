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


def test_build_llamaindex_tools_uses_discovery_schema_and_delegates_calls(monkeypatch) -> None:
    fake_tools_mod = types.ModuleType("llama_index.core.tools")

    class FakeFunctionTool:
        def __init__(self, fn, name, description, fn_schema):
            self.fn = fn
            self.metadata = types.SimpleNamespace(name=name, description=description)
            self.fn_schema = fn_schema

        @classmethod
        def from_defaults(cls, fn=None, name=None, description=None, fn_schema=None):
            return cls(fn, name, description, fn_schema)

    fake_tools_mod.FunctionTool = FakeFunctionTool
    fake_core_mod = types.ModuleType("llama_index.core")
    fake_core_mod.tools = fake_tools_mod
    fake_root_mod = types.ModuleType("llama_index")
    fake_root_mod.core = fake_core_mod
    monkeypatch.setitem(sys.modules, "llama_index", fake_root_mod)
    monkeypatch.setitem(sys.modules, "llama_index.core", fake_core_mod)
    monkeypatch.setitem(sys.modules, "llama_index.core.tools", fake_tools_mod)

    from parse_mcp.llamaindex import build_llamaindex_tools

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

    tools = build_llamaindex_tools(client)

    assert len(tools) == 1
    tool = tools[0]
    assert tool.metadata.name == "project_context_read"
    assert tool.fn_schema is not None
    result = tool.fn(include=["project"])
    assert result["ok"] is True
    assert client.calls == [("project_context_read", {"include": ["project"]})]
