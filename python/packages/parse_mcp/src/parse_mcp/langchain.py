from __future__ import annotations

from typing import List, Optional

from ._schema import build_args_model
from .models import ParseToolSpec


def _tool_description(spec: ParseToolSpec) -> str:
    x_parse = spec.meta.x_parse
    mutability = str(x_parse.get("mutability") or "read_only")
    supports_dry_run = bool(x_parse.get("supports_dry_run", False))
    suffix = " Mutability: {0}.".format(mutability)
    if supports_dry_run:
        suffix += " Supports dry-run previews."
    return spec.description + suffix


def build_langchain_tools(client, mode: Optional[str] = None) -> List[object]:
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:  # pragma: no cover - exercised in real installs
        raise ImportError("Install parse-mcp with the 'langchain' extra to build LangChain tools.") from exc

    tools = []
    for spec in client.list_tools(mode=mode):
        args_schema = build_args_model("{0}Args".format(spec.name.title().replace("_", "")), spec.parameters)

        def _runner(_tool_name: str = spec.name, **kwargs):
            return client.call_tool(_tool_name, kwargs)

        tools.append(
            StructuredTool.from_function(
                func=_runner,
                name=spec.name,
                description=_tool_description(spec),
                args_schema=args_schema,
            )
        )
    return tools
