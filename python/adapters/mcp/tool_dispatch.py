from __future__ import annotations

from typing import Any, Iterable

from adapters.mcp.error_envelope import execute_and_serialize
from adapters.mcp.schema import sync_registered_tool_metadata


def _build_tool_handler(tool_name: str, executor: Any, description: str):
    def _handler(**kwargs: Any) -> str:
        return execute_and_serialize(executor, tool_name, dict(kwargs))

    _handler.__name__ = f"mcp_{tool_name}"
    _handler.__doc__ = description
    return _handler


def register_chat_tools(mcp: Any, tools: Any, selected_tool_names: Iterable[str], tool_annotations_cls: Any) -> None:
    for tool_name in selected_tool_names:
        spec = tools.tool_spec(tool_name)
        handler = _build_tool_handler(tool_name, tools.execute, spec.description)
        mcp.tool(name=tool_name)(handler)
        sync_registered_tool_metadata(mcp, tool_name, tools, tool_annotations_cls)


def register_workflow_tools(mcp: Any, workflow_tools: Any, selected_tool_names: Iterable[str], tool_annotations_cls: Any) -> None:
    for tool_name in selected_tool_names:
        spec = workflow_tools.tool_spec(tool_name)
        handler = _build_tool_handler(tool_name, workflow_tools.execute, spec.description)
        mcp.tool(name=tool_name)(handler)
        sync_registered_tool_metadata(mcp, tool_name, workflow_tools, tool_annotations_cls)


__all__ = ["register_chat_tools", "register_workflow_tools"]
