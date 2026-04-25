import pathlib
import sys
from http import HTTPStatus
from unittest.mock import ANY

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.http.external_api_handlers import (
    ExternalApiHandlerError,
    HttpResponseSpec,
    build_mcp_exposure_response,
    build_mcp_tool_response,
    build_mcp_tools_response,
    execute_mcp_http_tool,
    match_builtin_docs_response,
)


class _FakeParseTools:
    def __init__(self) -> None:
        self.executed = []

    def execute(self, tool_name: str, raw_args):
        self.executed.append((tool_name, raw_args))
        return {"tool": tool_name, "args": raw_args, "family": "chat"}

    def tool_names(self):
        return ["project_context_read", "segment_read"]


class _FakeWorkflowTools:
    def __init__(self) -> None:
        self.executed = []

    def execute(self, tool_name: str, raw_args):
        self.executed.append((tool_name, raw_args))
        return {"tool": tool_name, "args": raw_args, "family": "workflow"}


def test_match_builtin_docs_response_returns_expected_specs() -> None:
    openapi = match_builtin_docs_response(
        "/openapi.json",
        base_url="http://127.0.0.1:8766",
        openapi_builder=lambda *, base_url: {"openapi": "3.1.0", "server": base_url},
        swagger_renderer=lambda _: "unused swagger",
        redoc_renderer=lambda _: "unused redoc",
    )
    docs = match_builtin_docs_response(
        "/docs",
        base_url="http://127.0.0.1:8766",
        openapi_builder=lambda *, base_url: {"openapi": base_url},
        swagger_renderer=lambda path: f"swagger:{path}",
        redoc_renderer=lambda _: "unused redoc",
    )
    redoc = match_builtin_docs_response(
        "/redoc",
        base_url="http://127.0.0.1:8766",
        openapi_builder=lambda *, base_url: {"openapi": base_url},
        swagger_renderer=lambda _: "unused swagger",
        redoc_renderer=lambda path: f"redoc:{path}",
    )

    assert openapi == HttpResponseSpec(
        status=HTTPStatus.OK,
        send_as="json",
        body={"openapi": "3.1.0", "server": "http://127.0.0.1:8766"},
    )
    assert docs == HttpResponseSpec(
        status=HTTPStatus.OK,
        send_as="text",
        body="swagger:/openapi.json",
        content_type="text/html; charset=utf-8",
    )
    assert redoc == HttpResponseSpec(
        status=HTTPStatus.OK,
        send_as="text",
        body="redoc:/openapi.json",
        content_type="text/html; charset=utf-8",
    )


def test_match_builtin_docs_response_returns_none_for_other_paths() -> None:
    assert match_builtin_docs_response(
        "/api/config",
        base_url="http://127.0.0.1:8766",
    ) is None


def test_build_mcp_exposure_response_returns_exposure_only() -> None:
    calls = []

    def fake_catalog_builder(**kwargs):
        calls.append(kwargs)
        return {
            "exposure": {"mode": kwargs["mode"], "mcpToolCount": 36},
            "tools": [{"name": "project_context_read"}],
        }

    payload = build_mcp_exposure_response(
        query_params={},
        project_root=pathlib.Path("/tmp/project"),
        parse_tools=_FakeParseTools(),
        workflow_tools=_FakeWorkflowTools(),
        catalog_builder=fake_catalog_builder,
    )

    assert payload == {"mode": "active", "mcpToolCount": 36}
    assert calls == [
        {
            "project_root": pathlib.Path("/tmp/project"),
            "mode": "active",
            "parse_tools": ANY,
            "workflow_tools": ANY,
        }
    ]


def test_build_mcp_tools_response_maps_invalid_mode_to_bad_request() -> None:
    with pytest.raises(ExternalApiHandlerError) as excinfo:
        build_mcp_tools_response(
            query_params={"mode": ["bogus"]},
            project_root=pathlib.Path("/tmp/project"),
            parse_tools=_FakeParseTools(),
            workflow_tools=_FakeWorkflowTools(),
            resolve_mode=lambda raw_mode: (_ for _ in ()).throw(ValueError(f"mode must be one of: active, default, all (got {raw_mode})")),
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert "mode must be one of" in excinfo.value.message


def test_build_mcp_tool_response_raises_not_found_for_unknown_tool() -> None:
    with pytest.raises(ExternalApiHandlerError) as excinfo:
        build_mcp_tool_response(
            "missing_tool",
            query_params={},
            project_root=pathlib.Path("/tmp/project"),
            parse_tools=_FakeParseTools(),
            workflow_tools=_FakeWorkflowTools(),
            get_tool_entry=lambda *args, **kwargs: None,
        )

    assert excinfo.value.status == HTTPStatus.NOT_FOUND
    assert excinfo.value.message == "Unknown MCP tool: missing_tool"


def test_execute_mcp_http_tool_rejects_non_object_args() -> None:
    with pytest.raises(ExternalApiHandlerError) as excinfo:
        execute_mcp_http_tool(
            "project_context_read",
            [],
            mode="active",
            project_root=pathlib.Path("/tmp/project"),
            parse_tools=_FakeParseTools(),
            workflow_tools=_FakeWorkflowTools(),
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "Tool arguments must be a JSON object"


def test_execute_mcp_http_tool_preserves_adapter_special_case() -> None:
    parse_tools = _FakeParseTools()
    workflow_tools = _FakeWorkflowTools()
    exposure_calls = []

    payload = execute_mcp_http_tool(
        "mcp_get_exposure_mode",
        {},
        mode="default",
        project_root=pathlib.Path("/tmp/project"),
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
        get_tool_entry=lambda *args, **kwargs: {"name": "mcp_get_exposure_mode", "family": "adapter"},
        catalog_builder=lambda **kwargs: {
            "count": 33,
            "exposure": {
                "configSource": "config/mcp_config.json",
                "exposeAllTools": False,
                "parseChatToolCount": 50,
                "workflowToolCount": 3,
                "mcpToolCount": 33,
            },
        },
        exposure_payload_builder=lambda **kwargs: exposure_calls.append(kwargs) or {"ok": True, **kwargs},
    )

    assert payload["ok"] is True
    assert payload["mcp_tool_count"] == 33
    assert parse_tools.executed == []
    assert workflow_tools.executed == []
    assert exposure_calls == [
        {
            "expose_all_tools": False,
            "config_source": "config/mcp_config.json",
            "parse_chat_tool_count": 50,
            "workflow_tool_count": 3,
            "mcp_tool_count": 33,
        }
    ]


def test_execute_mcp_http_tool_routes_workflow_family_to_workflow_runtime() -> None:
    parse_tools = _FakeParseTools()
    workflow_tools = _FakeWorkflowTools()

    payload = execute_mcp_http_tool(
        "run_full_annotation_pipeline",
        {"speaker": "Fail01"},
        mode="all",
        project_root=pathlib.Path("/tmp/project"),
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
        get_tool_entry=lambda *args, **kwargs: {"name": "run_full_annotation_pipeline", "family": "workflow"},
    )

    assert payload == {
        "tool": "run_full_annotation_pipeline",
        "args": {"speaker": "Fail01"},
        "family": "workflow",
    }
    assert workflow_tools.executed == [("run_full_annotation_pipeline", {"speaker": "Fail01"})]
    assert parse_tools.executed == []
