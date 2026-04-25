"""Helpers for the PARSE built-in docs and HTTP MCP bridge surface."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Mapping, Optional, Sequence

from ai.chat_tools import ChatToolExecutionError, ChatToolValidationError, ParseChatTools
from ai.workflow_tools import WorkflowTools
from external_api.catalog import build_mcp_http_catalog, get_mcp_tool_entry, mcp_exposure_payload, resolve_catalog_mode
from external_api.openapi import build_openapi_document, render_redoc_html, render_swagger_ui_html


@dataclass(frozen=True)
class HttpResponseSpec:
    status: HTTPStatus
    send_as: Literal["json", "text"]
    body: Any
    content_type: Optional[str] = None


@dataclass(frozen=True)
class ExternalApiHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


CatalogBuilder = Callable[..., Dict[str, Any]]
ToolEntryGetter = Callable[..., Optional[Dict[str, Any]]]
ExposurePayloadBuilder = Callable[..., Dict[str, Any]]
ModeResolver = Callable[[str], str]


_DOCS_HTML_CONTENT_TYPE = "text/html; charset=utf-8"
_OPENAPI_PATH = "/openapi.json"


def match_builtin_docs_response(
    request_path: str,
    *,
    base_url: str,
    openapi_builder: Callable[..., Dict[str, Any]] = build_openapi_document,
    swagger_renderer: Callable[[str], str] = render_swagger_ui_html,
    redoc_renderer: Callable[[str], str] = render_redoc_html,
) -> Optional[HttpResponseSpec]:
    if request_path == _OPENAPI_PATH:
        return HttpResponseSpec(
            status=HTTPStatus.OK,
            send_as="json",
            body=openapi_builder(base_url=base_url),
        )
    if request_path == "/docs":
        return HttpResponseSpec(
            status=HTTPStatus.OK,
            send_as="text",
            body=swagger_renderer(_OPENAPI_PATH),
            content_type=_DOCS_HTML_CONTENT_TYPE,
        )
    if request_path == "/redoc":
        return HttpResponseSpec(
            status=HTTPStatus.OK,
            send_as="text",
            body=redoc_renderer(_OPENAPI_PATH),
            content_type=_DOCS_HTML_CONTENT_TYPE,
        )
    return None


def resolve_requested_catalog_mode(
    query_params: Mapping[str, Sequence[str]],
    *,
    resolve_mode: ModeResolver = resolve_catalog_mode,
) -> str:
    raw_mode = (query_params.get("mode") or ["active"])[0]
    try:
        return resolve_mode(str(raw_mode))
    except ValueError as exc:
        raise ExternalApiHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc


def _build_mcp_catalog_for_request(
    *,
    query_params: Mapping[str, Sequence[str]],
    project_root: Path,
    parse_tools: ParseChatTools,
    workflow_tools: WorkflowTools,
    resolve_mode: ModeResolver = resolve_catalog_mode,
    catalog_builder: CatalogBuilder = build_mcp_http_catalog,
) -> tuple[str, Dict[str, Any]]:
    mode = resolve_requested_catalog_mode(query_params, resolve_mode=resolve_mode)
    catalog = catalog_builder(
        project_root=project_root,
        mode=mode,
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
    )
    return mode, catalog


def build_mcp_exposure_response(
    *,
    query_params: Mapping[str, Sequence[str]],
    project_root: Path,
    parse_tools: ParseChatTools,
    workflow_tools: WorkflowTools,
    resolve_mode: ModeResolver = resolve_catalog_mode,
    catalog_builder: CatalogBuilder = build_mcp_http_catalog,
) -> Dict[str, Any]:
    _, catalog = _build_mcp_catalog_for_request(
        query_params=query_params,
        project_root=project_root,
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
        resolve_mode=resolve_mode,
        catalog_builder=catalog_builder,
    )
    return dict(catalog.get("exposure") or {})


def build_mcp_tools_response(
    *,
    query_params: Mapping[str, Sequence[str]],
    project_root: Path,
    parse_tools: ParseChatTools,
    workflow_tools: WorkflowTools,
    resolve_mode: ModeResolver = resolve_catalog_mode,
    catalog_builder: CatalogBuilder = build_mcp_http_catalog,
) -> Dict[str, Any]:
    _, catalog = _build_mcp_catalog_for_request(
        query_params=query_params,
        project_root=project_root,
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
        resolve_mode=resolve_mode,
        catalog_builder=catalog_builder,
    )
    return catalog


def build_mcp_tool_response(
    tool_name: str,
    *,
    query_params: Mapping[str, Sequence[str]],
    project_root: Path,
    parse_tools: ParseChatTools,
    workflow_tools: WorkflowTools,
    resolve_mode: ModeResolver = resolve_catalog_mode,
    get_tool_entry: ToolEntryGetter = get_mcp_tool_entry,
) -> Dict[str, Any]:
    mode = resolve_requested_catalog_mode(query_params, resolve_mode=resolve_mode)
    tool_entry = get_tool_entry(
        tool_name,
        project_root=project_root,
        mode=mode,
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
    )
    if tool_entry is None:
        raise ExternalApiHandlerError(HTTPStatus.NOT_FOUND, "Unknown MCP tool: {0}".format(tool_name))
    return tool_entry


def execute_mcp_http_tool(
    tool_name: str,
    raw_args: Dict[str, Any],
    *,
    mode: str,
    project_root: Path,
    parse_tools: ParseChatTools,
    workflow_tools: WorkflowTools,
    get_tool_entry: ToolEntryGetter = get_mcp_tool_entry,
    catalog_builder: CatalogBuilder = build_mcp_http_catalog,
    exposure_payload_builder: ExposurePayloadBuilder = mcp_exposure_payload,
) -> Dict[str, Any]:
    if not isinstance(raw_args, dict):
        raise ExternalApiHandlerError(HTTPStatus.BAD_REQUEST, "Tool arguments must be a JSON object")

    tool_entry = get_tool_entry(
        tool_name,
        project_root=project_root,
        mode=mode,
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
    )
    if tool_entry is None:
        raise ExternalApiHandlerError(HTTPStatus.NOT_FOUND, "Unknown MCP tool: {0}".format(tool_name))

    family = str(tool_entry.get("family") or "chat")
    try:
        if family == "adapter" and tool_name == "mcp_get_exposure_mode":
            catalog = catalog_builder(
                project_root=project_root,
                mode=mode,
                parse_tools=parse_tools,
                workflow_tools=workflow_tools,
            )
            exposure = catalog.get("exposure") or {}
            return exposure_payload_builder(
                expose_all_tools=bool(exposure.get("exposeAllTools", False)),
                config_source=exposure.get("configSource"),
                parse_chat_tool_count=int(exposure.get("parseChatToolCount", len(parse_tools.tool_names()))),
                workflow_tool_count=int(exposure.get("workflowToolCount", 0)),
                mcp_tool_count=int(exposure.get("mcpToolCount", catalog.get("count", 0))),
            )
        if family == "workflow":
            return workflow_tools.execute(tool_name, raw_args)
        return parse_tools.execute(tool_name, raw_args)
    except (ChatToolValidationError, ChatToolExecutionError, ValueError) as exc:
        raise ExternalApiHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
