from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .models import ParseToolSpec


class ParseMcpClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8766", mode: str = "active") -> None:
        self.base_url = str(base_url or "http://127.0.0.1:8766").rstrip("/")
        self.mode = str(mode or "active").strip().lower() or "active"

    def _request_json(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url="{0}{1}".format(self.base_url, path),
            data=data,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads((response.read() or b"{}").decode("utf-8"))

    def get_exposure(self, mode: Optional[str] = None) -> Dict[str, Any]:
        selected_mode = urllib.parse.quote(str(mode or self.mode), safe="")
        return self._request_json("GET", "/api/mcp/exposure?mode={0}".format(selected_mode))

    def list_tools(self, mode: Optional[str] = None) -> List[ParseToolSpec]:
        selected_mode = urllib.parse.quote(str(mode or self.mode), safe="")
        payload = self._request_json("GET", "/api/mcp/tools?mode={0}".format(selected_mode))
        return [ParseToolSpec.from_payload(item) for item in list(payload.get("tools") or [])]

    def get_tool(self, tool_name: str, mode: Optional[str] = None) -> ParseToolSpec:
        safe_name = urllib.parse.quote(str(tool_name or "").strip(), safe="")
        selected_mode = urllib.parse.quote(str(mode or self.mode), safe="")
        payload = self._request_json("GET", "/api/mcp/tools/{0}?mode={1}".format(safe_name, selected_mode))
        return ParseToolSpec.from_payload(payload)

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None, mode: Optional[str] = None) -> Dict[str, Any]:
        safe_name = urllib.parse.quote(str(tool_name or "").strip(), safe="")
        path = "/api/mcp/tools/{0}".format(safe_name)
        if mode is not None:
            selected_mode = urllib.parse.quote(str(mode or self.mode), safe="")
            path = "{0}?mode={1}".format(path, selected_mode)
        return self._request_json("POST", path, payload=dict(arguments or {}))
