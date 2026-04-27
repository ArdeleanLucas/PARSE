from __future__ import annotations

import inspect
from typing import Any, Iterable

from adapters.mcp.error_envelope import execute_and_serialize
from adapters.mcp.schema import sync_registered_tool_metadata


def _python_annotation_for_schema(field_schema: Any) -> Any:
    if not isinstance(field_schema, dict):
        return Any
    field_type = field_schema.get("type")
    if isinstance(field_type, list):
        non_null = [item for item in field_type if item != "null"]
        field_type = non_null[0] if len(non_null) == 1 else None
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }.get(field_type, Any)


def _build_tool_signature(spec: Any) -> inspect.Signature:
    parameters_schema = spec.parameters if isinstance(getattr(spec, "parameters", None), dict) else {}
    properties = parameters_schema.get("properties", {}) if isinstance(parameters_schema, dict) else {}
    required = set(parameters_schema.get("required", []) or []) if isinstance(parameters_schema, dict) else set()

    parameters = []
    for field_name, field_schema in properties.items():
        parameters.append(
            inspect.Parameter(
                field_name,
                inspect.Parameter.KEYWORD_ONLY,
                default=inspect.Parameter.empty if field_name in required else None,
                annotation=_python_annotation_for_schema(field_schema),
            )
        )
    return inspect.Signature(parameters=parameters, return_annotation=str)


def _build_tool_handler(tool_name: str, executor: Any, spec: Any):
    def _handler(**kwargs: Any) -> str:
        filtered_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        return execute_and_serialize(executor, tool_name, filtered_kwargs)

    _handler.__name__ = tool_name
    _handler.__doc__ = spec.description
    _handler.__signature__ = _build_tool_signature(spec)
    _handler.__annotations__ = {
        parameter.name: parameter.annotation
        for parameter in _handler.__signature__.parameters.values()
    }
    _handler.__annotations__["return"] = str
    return _handler


def register_chat_tools(mcp: Any, tools: Any, selected_tool_names: Iterable[str], tool_annotations_cls: Any) -> None:
    for tool_name in selected_tool_names:
        spec = tools.tool_spec(tool_name)
        handler = _build_tool_handler(tool_name, tools.execute, spec)
        mcp.tool(name=tool_name)(handler)
        sync_registered_tool_metadata(mcp, tool_name, tools, tool_annotations_cls)


def register_workflow_tools(mcp: Any, workflow_tools: Any, selected_tool_names: Iterable[str], tool_annotations_cls: Any) -> None:
    for tool_name in selected_tool_names:
        spec = workflow_tools.tool_spec(tool_name)
        handler = _build_tool_handler(tool_name, workflow_tools.execute, spec)
        mcp.tool(name=tool_name)(handler)
        sync_registered_tool_metadata(mcp, tool_name, workflow_tools, tool_annotations_cls)


__all__ = ["register_chat_tools", "register_workflow_tools"]
