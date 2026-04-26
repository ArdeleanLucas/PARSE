from __future__ import annotations

import json
from typing import Any


def sync_registered_tool_metadata(mcp: Any, tool_name: str, spec_provider: Any, tool_annotations_cls: Any) -> None:
    spec = spec_provider.tool_spec(tool_name)
    registered = mcp._tool_manager._tools.get(tool_name)
    if registered is None:
        return
    registered.description = spec.description
    registered.parameters = json.loads(json.dumps(spec.parameters))
    annotation_payload = spec.mcp_annotations_payload()
    registered.annotations = tool_annotations_cls(**annotation_payload) if tool_annotations_cls is not None else None
    registered.meta = {"x-parse": spec.mcp_meta_payload()}


__all__ = ["sync_registered_tool_metadata"]
