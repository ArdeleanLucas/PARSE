import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server
from external_api.catalog import build_mcp_http_catalog
from external_api.openapi import build_openapi_document


@contextmanager
def _serve_parse_http() -> str:
    server._chat_tools_runtime = None
    server._chat_orchestrator_runtime = None
    httpd = server._BoundedThreadHTTPServer(("127.0.0.1", 0), server.RangeRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{0}".format(httpd.server_port)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        server._chat_tools_runtime = None
        server._chat_orchestrator_runtime = None


def test_build_openapi_document_includes_mcp_bridge_and_auth_paths() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")

    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "PARSE HTTP API"
    assert spec["servers"] == [{"url": "http://127.0.0.1:8766"}]
    assert "/api/config" in spec["paths"]
    assert "/api/auth/status" in spec["paths"]
    assert "/api/clef/clear" in spec["paths"]
    assert "/api/mcp/exposure" in spec["paths"]
    assert "/api/mcp/tools" in spec["paths"]
    assert "/api/mcp/tools/{toolName}" in spec["paths"]
    assert spec["paths"]["/api/mcp/tools/{toolName}"]["post"]["operationId"] == "executeMcpTool"


def test_build_openapi_document_covers_the_current_http_route_surface() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    assert set(spec["paths"].keys()) == {
        "/api/config",
        "/api/annotations/{speaker}",
        "/api/stt-segments/{speaker}",
        "/api/pipeline/state/{speaker}",
        "/api/chat/session/{sessionId}",
        "/api/jobs",
        "/api/jobs/active",
        "/api/jobs/{jobId}",
        "/api/jobs/{jobId}/logs",
        "/api/enrichments",
        "/api/auth/status",
        "/api/auth/key",
        "/api/auth/start",
        "/api/auth/poll",
        "/api/auth/logout",
        "/api/clef/clear",
        "/api/worker/status",
        "/api/export/lingpy",
        "/api/export/nexus",
        "/api/contact-lexemes/coverage",
        "/api/tags",
        "/api/spectrogram",
        "/api/lexeme/search",
        "/api/onboard/speaker",
        "/api/onboard/speaker/status",
        "/api/normalize",
        "/api/normalize/status",
        "/api/stt",
        "/api/stt/status",
        "/api/suggest",
        "/api/chat/session",
        "/api/chat/run",
        "/api/chat/run/status",
        "/api/tags/merge",
        "/api/concepts/import",
        "/api/tags/import",
        "/api/lexeme-notes",
        "/api/lexeme-notes/import",
        "/api/offset/detect",
        "/api/offset/detect-from-pair",
        "/api/offset/apply",
        "/api/compute/status",
        "/api/compute/{computeType}",
        "/api/compute/{computeType}/status",
        "/api/{computeType}/status",
        "/api/mcp/exposure",
        "/api/mcp/tools",
        "/api/mcp/tools/{toolName}",
    }


def test_build_openapi_document_keeps_lexeme_media_search_contract_honest() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")

    spectrogram_params = {param["name"] for param in spec["paths"]["/api/spectrogram"]["get"]["parameters"]}
    assert spectrogram_params == {"speaker", "start", "end", "audio", "force"}

    lexeme_search_params = {param["name"] for param in spec["paths"]["/api/lexeme/search"]["get"]["parameters"]}
    assert lexeme_search_params == {"speaker", "variants", "concept_id", "language", "tiers", "limit", "max_distance"}

    import_schema = spec["paths"]["/api/lexeme-notes/import"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert import_schema["required"] == ["speaker_id", "csv"]
    assert import_schema["properties"]["speaker_id"] == {"type": "string"}
    assert import_schema["properties"]["csv"] == {"type": "string", "format": "binary"}

    onboard_schema = spec["paths"]["/api/onboard/speaker"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert onboard_schema["required"] == ["speaker_id", "audio"]
    assert onboard_schema["properties"]["commentsCsv"] == {"type": "string", "format": "binary"}


def test_build_mcp_http_catalog_defaults_to_full_safe_surface_without_config(tmp_path: pathlib.Path) -> None:
    catalog = build_mcp_http_catalog(project_root=tmp_path, mode="default")

    tool_names = {tool["name"] for tool in catalog["tools"]}
    assert catalog["mode"] == "default"
    assert catalog["count"] == 61
    assert catalog["exposure"]["mcpToolCount"] == 61
    assert catalog["exposure"]["defaultParseMcpToolCount"] == 57
    assert "audio_normalize_start" in tool_names
    assert "clef_clear_data" in tool_names
    assert "csv_only_reimport" in tool_names
    assert "revert_csv_reimport" in tool_names
    assert "export_annotations_csv" in tool_names
    assert "transcript_reformat" in tool_names


def test_build_mcp_http_catalog_active_mode_preserves_legacy_surface_for_explicit_false_config(tmp_path: pathlib.Path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config" / "mcp_config.json"
    config_path.write_text('{"expose_all_tools": false}', encoding="utf-8")

    catalog = build_mcp_http_catalog(project_root=tmp_path, mode="active")

    tool_names = {tool["name"] for tool in catalog["tools"]}
    assert catalog["mode"] == "active"
    assert catalog["count"] == 42
    assert catalog["exposure"]["configSource"] == str(config_path)
    assert catalog["exposure"]["mcpToolCount"] == 42
    assert catalog["exposure"]["defaultParseMcpToolCount"] == 57
    assert "annotation_read" in tool_names
    assert "csv_only_reimport" in tool_names
    assert "revert_csv_reimport" in tool_names
    assert "audio_normalize_start" not in tool_names
    assert "clef_clear_data" not in tool_names
    assert "export_annotations_csv" not in tool_names


def test_build_mcp_http_catalog_includes_workflow_specs_and_safety_metadata(tmp_path: pathlib.Path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "mcp_config.json").write_text('{"expose_all_tools": false}', encoding="utf-8")

    catalog = build_mcp_http_catalog(project_root=tmp_path, mode="all")

    assert catalog["mode"] == "all"
    assert catalog["exposure"]["workflowToolCount"] == 3
    tool_names = {tool["name"] for tool in catalog["tools"]}
    assert "project_context_read" in tool_names
    assert "run_full_annotation_pipeline" in tool_names

    workflow_spec = next(tool for tool in catalog["tools"] if tool["name"] == "run_full_annotation_pipeline")
    assert workflow_spec["family"] == "workflow"
    assert workflow_spec["parameters"]["type"] == "object"
    assert workflow_spec["meta"]["x-parse"]["supports_dry_run"] is True


def test_http_openapi_and_docs_endpoints_are_served(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    with _serve_parse_http() as base_url:
        with urllib.request.urlopen(base_url + "/openapi.json", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
            content_type = response.headers.get("Content-Type", "")
        assert payload["openapi"] == "3.1.0"
        assert "/api/mcp/tools" in payload["paths"]
        assert content_type.startswith("application/json")

        with urllib.request.urlopen(base_url + "/docs", timeout=10) as response:
            swagger_html = response.read().decode("utf-8")
        assert "SwaggerUIBundle" in swagger_html
        assert "/openapi.json" in swagger_html

        with urllib.request.urlopen(base_url + "/redoc", timeout=10) as response:
            redoc_html = response.read().decode("utf-8")
        assert "Redoc.init" in redoc_html
        assert "/openapi.json" in redoc_html


def test_http_mcp_bridge_lists_and_executes_tools(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    with _serve_parse_http() as base_url:
        with urllib.request.urlopen(base_url + "/api/mcp/tools?mode=all", timeout=10) as response:
            catalog = json.loads(response.read().decode("utf-8"))
        names = {tool["name"] for tool in catalog["tools"]}
        assert "project_context_read" in names
        assert "run_full_annotation_pipeline" in names

        request = urllib.request.Request(
            url=base_url + "/api/mcp/tools/project_context_read?mode=all",
            data=json.dumps({"include": ["project"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["tool"] == "project_context_read"
        assert payload["ok"] is True
        assert "result" in payload


def test_http_mcp_bridge_starts_from_clean_chat_runtime(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    server._chat_tools_runtime = object()
    server._chat_orchestrator_runtime = object()

    with _serve_parse_http() as base_url:
        with urllib.request.urlopen(base_url + "/api/mcp/tools?mode=all", timeout=10) as response:
            catalog = json.loads(response.read().decode("utf-8"))

    names = {tool["name"] for tool in catalog["tools"]}
    assert "project_context_read" in names


def test_http_mcp_bridge_rejects_invalid_mode_with_400(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    with _serve_parse_http() as base_url:
        try:
            urllib.request.urlopen(base_url + "/api/mcp/tools?mode=bogus", timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
            assert "mode must be one of" in payload["error"]
        else:
            raise AssertionError("Expected HTTP 400 for invalid mode")
