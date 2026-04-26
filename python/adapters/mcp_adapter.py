#!/usr/bin/env python3
"""PARSE MCP adapter orchestrator."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("parse.mcp_adapter")

_ADAPTER_DIR = Path(__file__).resolve().parent
_PYTHON_DIR = _ADAPTER_DIR.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from adapters.mcp.env_config import (
    DEFAULT_MCP_WORKFLOW_TOOL_NAMES,
    _load_mcp_config,
    _load_repo_parse_env,
    _mcp_exposure_payload,
    _resolve_external_read_roots,
    _resolve_memory_path,
    _resolve_onboard_http_timeout,
    _resolve_project_root,
    _selected_mcp_tool_names,
)
from adapters.mcp.transport import (
    _build_job_logs_callback,
    _build_jobs_callback,
    _build_jobs_list_callback,
    _build_normalize_callback,
    _build_onboard_callback,
    _build_pipeline_callbacks,
    _build_stt_callbacks,
)
from adapters.mcp.schema import sync_registered_tool_metadata
from adapters.mcp.tool_dispatch import register_chat_tools, register_workflow_tools
from adapters.mcp.error_envelope import serialize_tool_result

_MCP_AVAILABLE = False
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    _MCP_AVAILABLE = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]
    ToolAnnotations = None  # type: ignore[assignment,misc]


def create_mcp_server(project_root: Optional[str] = None) -> "FastMCP":
    """Create and return the PARSE MCP server with all tools registered."""
    if not _MCP_AVAILABLE:
        raise ImportError(
            "MCP server requires the 'mcp' package. Install with: pip install 'mcp[cli]'"
        )

    from ai.chat_tools import ParseChatTools
    from ai.workflow_tools import WorkflowTools

    root = _resolve_project_root(project_root)
    applied_env = _load_repo_parse_env(root)
    external_roots = _resolve_external_read_roots()
    memory_path = _resolve_memory_path(root)
    logger.info("PARSE MCP server starting with project root: %s", root)
    if applied_env:
        logger.info(
            "Loaded .parse-env overrides: %s",
            ", ".join("{0}={1}".format(k, v) for k, v in sorted(applied_env.items())),
        )
    if external_roots:
        logger.info("External read roots: %s", ", ".join(str(r) for r in external_roots))
    logger.info("Chat memory path: %s", memory_path)

    start_stt, get_snapshot = _build_stt_callbacks()
    pipeline_state_cb, start_compute_cb = _build_pipeline_callbacks()
    onboard_callback = _build_onboard_callback()
    normalize_cb = _build_normalize_callback()
    jobs_cb = _build_jobs_callback()
    jobs_list_cb = _build_jobs_list_callback()
    job_logs_cb = _build_job_logs_callback()

    tools = ParseChatTools(
        project_root=root,
        start_stt_job=start_stt,
        get_job_snapshot=get_snapshot,
        list_jobs=jobs_list_cb,
        get_job_logs=job_logs_cb,
        external_read_roots=external_roots,
        memory_path=memory_path,
        onboard_speaker=onboard_callback,
        pipeline_state=pipeline_state_cb,
        start_compute_job=start_compute_cb,
        start_normalize_job=normalize_cb,
        list_active_jobs=jobs_cb,
    )
    workflow_tools = WorkflowTools(
        project_root=root,
        start_stt_job=start_stt,
        get_job_snapshot=get_snapshot,
        external_read_roots=external_roots,
        memory_path=memory_path,
        onboard_speaker=onboard_callback,
        pipeline_state=pipeline_state_cb,
        start_compute_job=start_compute_cb,
        start_normalize_job=normalize_cb,
        list_active_jobs=jobs_cb,
    )

    mcp_config = _load_mcp_config(root)
    expose_all_tools = mcp_config.get("expose_all_tools", False)
    all_mcp_tool_names = ParseChatTools.get_all_tool_names()
    selected_mcp_tool_names = _selected_mcp_tool_names(all_mcp_tool_names, expose_all_tools)
    selected_workflow_tool_names = list(DEFAULT_MCP_WORKFLOW_TOOL_NAMES)
    all_registered_tool_names = list(selected_mcp_tool_names) + list(selected_workflow_tool_names)

    mcp = FastMCP(
        "parse",
        instructions=(
            "PARSE — Phonetic Analysis & Review Source Explorer. Linguistic fieldwork tools "
            "for annotation, cross-speaker comparison, cognate analysis, STT pipeline control, "
            "and contact-language lookup."
        ),
    )

    @mcp.tool(name="mcp_get_exposure_mode")
    def mcp_get_exposure_mode() -> str:
        """Read the active MCP exposure mode, config source, and tool counts."""
        payload = _mcp_exposure_payload(
            expose_all_tools=expose_all_tools,
            config_source=mcp_config.get("config_path"),
            parse_chat_tool_count=len(all_mcp_tool_names),
            workflow_tool_count=len(selected_workflow_tool_names),
            mcp_tool_count=len(all_registered_tool_names) + 1,
        )
        return serialize_tool_result(payload)

    register_chat_tools(mcp, tools, selected_mcp_tool_names, ToolAnnotations)
    register_workflow_tools(mcp, workflow_tools, selected_workflow_tool_names, ToolAnnotations)

    logger.info(
        "MCP exposing %s tools (parse_chat=%s, workflow=%s, expose_all_tools=%s)",
        len(all_registered_tool_names),
        len(selected_mcp_tool_names),
        len(selected_workflow_tool_names),
        str(expose_all_tools).lower(),
    )
    return mcp


def main() -> None:
    """Start the PARSE MCP server on stdio."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="PARSE MCP Server")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Path to PARSE project root (default: $PARSE_PROJECT_ROOT or auto-detect)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging on stderr",
    )
    args = parser.parse_args()

    if not _MCP_AVAILABLE:
        print(
            "Error: MCP server requires the 'mcp' package.\n"
            "Install with: pip install 'mcp[cli]'",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, stream=sys.stderr)
    server = create_mcp_server(project_root=args.project_root)

    async def _run() -> None:
        await server.run_stdio_async()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


__all__ = [
    'DEFAULT_MCP_WORKFLOW_TOOL_NAMES',
    '_MCP_AVAILABLE',
    '_build_job_logs_callback',
    '_build_jobs_callback',
    '_build_jobs_list_callback',
    '_build_normalize_callback',
    '_build_onboard_callback',
    '_build_pipeline_callbacks',
    '_build_stt_callbacks',
    '_load_mcp_config',
    '_load_repo_parse_env',
    '_mcp_exposure_payload',
    '_resolve_external_read_roots',
    '_resolve_memory_path',
    '_resolve_onboard_http_timeout',
    '_resolve_project_root',
    '_selected_mcp_tool_names',
    'create_mcp_server',
    'main',
    'register_chat_tools',
    'register_workflow_tools',
    'sync_registered_tool_metadata',
]


if __name__ == "__main__":
    main()
