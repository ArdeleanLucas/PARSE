import io
import json
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from parse_mcp.client import ParseMcpClient


class _FakeHttpResponse:
    def __init__(self, payload):
        self._payload = payload
        self.headers = {"Content-Type": "application/json; charset=utf-8"}

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_client_lists_tools_via_http_bridge(monkeypatch) -> None:
    seen = []

    def fake_urlopen(request, timeout=0):
        seen.append((request.full_url, request.get_method(), request.data))
        return _FakeHttpResponse(
            {
                "mode": "active",
                "tools": [
                    {
                        "name": "project_context_read",
                        "family": "chat",
                        "description": "Read PARSE project context.",
                        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                        "annotations": {"readOnlyHint": True},
                        "meta": {"x-parse": {"mutability": "read_only", "supports_dry_run": False, "preconditions": [], "postconditions": []}},
                    }
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client = ParseMcpClient(base_url="http://127.0.0.1:8766")
    tools = client.list_tools()

    assert [tool.name for tool in tools] == ["project_context_read"]
    assert seen[0][0].endswith("/api/mcp/tools?mode=active")
    assert seen[0][1] == "GET"


def test_client_executes_tool_via_http_bridge(monkeypatch) -> None:
    seen = []

    def fake_urlopen(request, timeout=0):
        seen.append((request.full_url, request.get_method(), json.loads((request.data or b"{}").decode("utf-8"))))
        return _FakeHttpResponse({"tool": "project_context_read", "ok": True, "result": {"readOnly": True}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client = ParseMcpClient(base_url="http://127.0.0.1:8766")
    result = client.call_tool("project_context_read", {"include": ["project"]})

    assert result["ok"] is True
    assert seen[0][0].endswith("/api/mcp/tools/project_context_read")
    assert seen[0][1] == "POST"
    assert seen[0][2] == {"include": ["project"]}
