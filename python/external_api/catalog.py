from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.chat_tools import ChatToolSpec, DEFAULT_MCP_TOOL_NAMES, ParseChatTools
from ai.workflow_tools import DEFAULT_MCP_WORKFLOW_TOOL_NAMES, WorkflowTools

MCP_CONFIG_FILENAME = "mcp_config.json"
CATALOG_MODES = {"active", "default", "all"}


def resolve_mcp_config_path(project_root_path: Path) -> Optional[Path]:
    project_root = Path(project_root_path).expanduser().resolve()
    candidates = [
        project_root / "config" / MCP_CONFIG_FILENAME,
        project_root / MCP_CONFIG_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def load_mcp_config(project_root_path: Path) -> Dict[str, Any]:
    config_path = resolve_mcp_config_path(project_root_path)
    if config_path is None:
        return {"expose_all_tools": False, "config_path": None}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"expose_all_tools": False, "config_path": str(config_path)}
    if not isinstance(payload, dict):
        return {"expose_all_tools": False, "config_path": str(config_path)}
    expose_all_tools = payload.get("expose_all_tools", False)
    if not isinstance(expose_all_tools, bool):
        expose_all_tools = False
    return {"expose_all_tools": expose_all_tools, "config_path": str(config_path)}


def resolve_catalog_mode(raw_mode: Optional[str]) -> str:
    mode = str(raw_mode or "active").strip().lower()
    if mode not in CATALOG_MODES:
        raise ValueError("mode must be one of: active, default, all")
    return mode


def selected_mcp_tool_names(all_tool_names: List[str], expose_all_tools: bool) -> List[str]:
    if expose_all_tools:
        return list(all_tool_names)
    available_names = set(all_tool_names)
    return [name for name in DEFAULT_MCP_TOOL_NAMES if name in available_names]


def mcp_exposure_payload(
    *,
    expose_all_tools: bool,
    config_source: Optional[str],
    parse_chat_tool_count: int,
    workflow_tool_count: int,
    mcp_tool_count: int,
) -> Dict[str, Any]:
    return {
        "tool": "mcp_get_exposure_mode",
        "ok": True,
        "result": {
            "readOnly": True,
            "previewOnly": True,
            "mode": "read-only",
            "exposeAllTools": expose_all_tools,
            "configSource": config_source,
            "parseChatToolCount": parse_chat_tool_count,
            "workflowToolCount": workflow_tool_count,
            "mcpToolCount": mcp_tool_count,
            "defaultParseMcpToolCount": len(DEFAULT_MCP_TOOL_NAMES),
            "defaultWorkflowMcpToolCount": len(DEFAULT_MCP_WORKFLOW_TOOL_NAMES),
        },
    }


def _adapter_tool_entry(exposure_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": "mcp_get_exposure_mode",
        "family": "adapter",
        "description": "Read the active MCP exposure mode, config source, and tool counts.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
        "meta": {
            "x-parse": {
                "mutability": "read_only",
                "supports_dry_run": False,
                "dry_run_parameter": None,
                "preconditions": [],
                "postconditions": [
                    {
                        "id": "mcp_exposure_reported",
                        "description": "The active MCP exposure mode, config source, and tool counts are returned.",
                        "severity": "required",
                        "kind": "reporting",
                    }
                ],
            }
        },
        "result": exposure_payload["result"],
    }


def build_mcp_tool_entry(spec: ChatToolSpec, family: str) -> Dict[str, Any]:
    return {
        "name": spec.name,
        "family": family,
        "description": spec.description,
        "parameters": json.loads(json.dumps(spec.parameters)),
        "annotations": spec.mcp_annotations_payload(),
        "meta": {"x-parse": spec.mcp_meta_payload()},
    }


def build_mcp_http_catalog(
    *,
    project_root: Path,
    mode: str = "active",
    parse_tools: Optional[ParseChatTools] = None,
    workflow_tools: Optional[WorkflowTools] = None,
) -> Dict[str, Any]:
    resolved_mode = resolve_catalog_mode(mode)
    project_root = Path(project_root).expanduser().resolve()
    parse_tools = parse_tools or ParseChatTools(project_root=project_root)
    workflow_tools = workflow_tools or WorkflowTools(project_root=project_root)

    config = load_mcp_config(project_root)
    if resolved_mode == "all":
        expose_all_tools = True
        config_source = config.get("config_path")
    elif resolved_mode == "default":
        expose_all_tools = False
        config_source = config.get("config_path")
    else:
        expose_all_tools = bool(config.get("expose_all_tools", False))
        config_source = config.get("config_path")

    all_parse_tool_names = parse_tools.tool_names()
    selected_parse_names = selected_mcp_tool_names(all_parse_tool_names, expose_all_tools)
    selected_workflow_names = list(DEFAULT_MCP_WORKFLOW_TOOL_NAMES)
    mcp_tool_count = len(selected_parse_names) + len(selected_workflow_names) + 1
    exposure = mcp_exposure_payload(
        expose_all_tools=expose_all_tools,
        config_source=config_source,
        parse_chat_tool_count=len(all_parse_tool_names),
        workflow_tool_count=len(selected_workflow_names),
        mcp_tool_count=mcp_tool_count,
    )

    tools: List[Dict[str, Any]] = []
    tools.append(_adapter_tool_entry(exposure))
    for name in selected_parse_names:
        tools.append(build_mcp_tool_entry(parse_tools.tool_spec(name), family="chat"))
    for name in selected_workflow_names:
        tools.append(build_mcp_tool_entry(workflow_tools.tool_spec(name), family="workflow"))

    tools.sort(key=lambda item: item["name"])
    return {
        "mode": resolved_mode,
        "count": len(tools),
        "exposure": exposure["result"],
        "tools": tools,
    }


def get_mcp_tool_entry(
    tool_name: str,
    *,
    project_root: Path,
    mode: str = "active",
    parse_tools: Optional[ParseChatTools] = None,
    workflow_tools: Optional[WorkflowTools] = None,
) -> Optional[Dict[str, Any]]:
    catalog = build_mcp_http_catalog(
        project_root=project_root,
        mode=mode,
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
    )
    target = str(tool_name or "").strip()
    for tool in catalog["tools"]:
        if tool["name"] == target:
            return tool
    return None
