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


def _build_crewai_tool(client, spec: ParseToolSpec, BaseTool):
    args_model = build_args_model("{0}Args".format(spec.name.title().replace("_", "")), spec.parameters)

    class ParseCrewAITool(BaseTool):
        def _run(self, **kwargs):
            return client.call_tool(spec.name, kwargs)

    ParseCrewAITool.name = spec.name
    ParseCrewAITool.description = _tool_description(spec)
    ParseCrewAITool.args_schema = args_model
    return ParseCrewAITool()


def build_crewai_tools(client, mode: Optional[str] = None) -> List[object]:
    try:
        from crewai.tools import BaseTool
    except ImportError as exc:  # pragma: no cover - exercised in real installs
        raise ImportError("Install parse-mcp with the 'crewai' extra to build CrewAI tools.") from exc

    return [_build_crewai_tool(client, spec, BaseTool) for spec in client.list_tools(mode=mode)]
