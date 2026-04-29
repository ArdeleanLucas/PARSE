from __future__ import annotations

from typing import Any, Dict, List, Optional


def _schema_ref(name: str) -> Dict[str, Any]:
    return {"$ref": "#/components/schemas/{0}".format(name)}


def _json_content(schema: Dict[str, Any]) -> Dict[str, Any]:
    return {"application/json": {"schema": schema}}


def _binary_content(content_type: str) -> Dict[str, Any]:
    return {content_type: {"schema": {"type": "string", "format": "binary"}}}


def _response(description: str, schema: Optional[Dict[str, Any]] = None, *, content_type: str = "application/json") -> Dict[str, Any]:
    payload: Dict[str, Any] = {"description": description}
    if schema is not None:
        payload["content"] = _json_content(schema) if content_type == "application/json" else {content_type: {"schema": schema}}
    return payload


def _parameter(name: str, where: str, schema: Dict[str, Any], *, required: bool = False, description: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "in": where,
        "required": required,
        "description": description,
        "schema": schema,
    }


def build_openapi_document(base_url: str = "http://127.0.0.1:8766") -> Dict[str, Any]:
    info_description = (
        "PARSE HTTP API for the browser workstation, local automation, and external agents. "
        "The general HTTP surface is local-trust and not bearer-protected; provider credentials are managed "
        "through /api/auth/* and stored locally in config/auth_tokens.json. The /api/mcp/* bridge publishes "
        "the PARSE MCP schema and exposes the active tool surface for external wrappers."
    )
    components = {
        "schemas": {
            "GenericObject": {"type": "object", "additionalProperties": True},
            "ErrorResponse": {
                "type": "object",
                "required": ["error"],
                "properties": {"error": {"type": "string"}},
                "additionalProperties": True,
            },
            "GenericJobResponse": {
                "type": "object",
                "properties": {
                    "jobId": {"type": "string"},
                    "job_id": {"type": "string"},
                    "status": {"type": "string"},
                    "progress": {"type": "number"},
                    "message": {"type": ["string", "null"]},
                    "result": {"type": ["object", "array", "string", "number", "boolean", "null"], "additionalProperties": True},
                    "error": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
            "AuthStatus": {
                "type": "object",
                "properties": {
                    "authenticated": {"type": "boolean"},
                    "flow_active": {"type": "boolean"},
                    "method": {"type": "string"},
                    "provider": {"type": "string"},
                    "user_code": {"type": "string"},
                    "verification_uri": {"type": "string"},
                    "expires_in": {"type": ["integer", "null"]},
                },
                "additionalProperties": True,
            },
            "ToolAnnotations": {
                "type": "object",
                "properties": {
                    "readOnlyHint": {"type": "boolean"},
                    "destructiveHint": {"type": "boolean"},
                    "openWorldHint": {"type": "boolean"},
                    "idempotentHint": {"type": "boolean"},
                },
                "additionalProperties": True,
            },
            "ToolMeta": {
                "type": "object",
                "properties": {
                    "x-parse": {"type": "object", "additionalProperties": True},
                },
                "additionalProperties": True,
            },
            "ToolSpec": {
                "type": "object",
                "required": ["name", "family", "description", "parameters", "annotations", "meta"],
                "properties": {
                    "name": {"type": "string"},
                    "family": {"type": "string", "enum": ["adapter", "chat", "workflow"]},
                    "description": {"type": "string"},
                    "parameters": {"type": "object", "additionalProperties": True},
                    "annotations": _schema_ref("ToolAnnotations"),
                    "meta": _schema_ref("ToolMeta"),
                },
                "additionalProperties": True,
            },
            "McpToolCatalog": {
                "type": "object",
                "required": ["mode", "count", "exposure", "tools"],
                "properties": {
                    "mode": {"type": "string", "enum": ["active", "default", "all"]},
                    "count": {"type": "integer"},
                    "exposure": {"type": "object", "additionalProperties": True},
                    "tools": {"type": "array", "items": _schema_ref("ToolSpec")},
                },
                "additionalProperties": True,
            },
            "ToolExecutionResponse": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "ok": {"type": "boolean"},
                    "result": {"type": ["object", "array", "string", "number", "boolean", "null"], "additionalProperties": True},
                    "error": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
        }
    }

    paths: Dict[str, Any] = {
        "/api/config": {
            "get": {"tags": ["Config"], "summary": "Read project configuration", "operationId": "getConfig", "responses": {"200": _response("Project configuration", _schema_ref("GenericObject")), "500": _response("Server error", _schema_ref("ErrorResponse"))}},
            "post": {"tags": ["Config"], "summary": "Update project configuration", "operationId": "postConfig", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Updated project configuration", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
            "put": {"tags": ["Config"], "summary": "Update project configuration", "operationId": "putConfig", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Updated project configuration", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/annotations/{speaker}": {
            "get": {"tags": ["Annotations"], "summary": "Read one speaker annotation record", "operationId": "getAnnotation", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True)], "responses": {"200": _response("Normalized annotation payload", _schema_ref("GenericObject")), "400": _response("Invalid speaker", _schema_ref("ErrorResponse")), "404": _response("Missing annotation", _schema_ref("ErrorResponse"))}},
            "post": {"tags": ["Annotations"], "summary": "Save one speaker annotation record", "operationId": "saveAnnotation", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True)], "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Saved annotation payload", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/stt-segments/{speaker}": {
            "get": {"tags": ["STT"], "summary": "Read cached STT segments", "operationId": "getSttSegments", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True)], "responses": {"200": _response("Cached STT segments", _schema_ref("GenericObject"))}},
        },
        "/api/pipeline/state/{speaker}": {
            "get": {"tags": ["Pipeline"], "summary": "Read coverage-aware pipeline state", "operationId": "getPipelineState", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True)], "responses": {"200": _response("Pipeline coverage state", _schema_ref("GenericObject"))}},
        },
        "/api/chat/session/{sessionId}": {
            "get": {"tags": ["Chat"], "summary": "Read one chat session", "operationId": "getChatSession", "parameters": [_parameter("sessionId", "path", {"type": "string"}, required=True)], "responses": {"200": _response("Chat session payload", _schema_ref("GenericObject")), "404": _response("Unknown chat session", _schema_ref("ErrorResponse"))}},
        },
        "/api/jobs": {
            "get": {"tags": ["Jobs"], "summary": "List jobs from the PARSE job registry", "operationId": "listJobs", "parameters": [_parameter("statuses", "query", {"type": "string"}), _parameter("types", "query", {"type": "string"}), _parameter("speaker", "query", {"type": "string"}), _parameter("limit", "query", {"type": "integer"})], "responses": {"200": _response("Active and recent jobs", _schema_ref("GenericObject"))}},
        },
        "/api/jobs/active": {
            "get": {"tags": ["Jobs"], "summary": "List currently running jobs", "operationId": "listActiveJobs", "responses": {"200": _response("Running jobs", _schema_ref("GenericObject"))}},
        },
        "/api/jobs/{jobId}": {
            "get": {"tags": ["Jobs"], "summary": "Read one job snapshot", "operationId": "getJob", "parameters": [_parameter("jobId", "path", {"type": "string"}, required=True)], "responses": {"200": _response("Job snapshot", _schema_ref("GenericJobResponse")), "404": _response("Unknown job", _schema_ref("ErrorResponse"))}},
        },
        "/api/jobs/{jobId}/logs": {
            "get": {"tags": ["Jobs"], "summary": "Read crash/log payloads for one job", "operationId": "getJobLogs", "parameters": [_parameter("jobId", "path", {"type": "string"}, required=True), _parameter("offset", "query", {"type": "integer"}), _parameter("limit", "query", {"type": "integer"})], "responses": {"200": _response("Structured job logs", _schema_ref("GenericObject")), "404": _response("Unknown job", _schema_ref("ErrorResponse"))}},
        },
        "/api/enrichments": {
            "get": {"tags": ["Compare"], "summary": "Read comparative enrichments", "operationId": "getEnrichments", "responses": {"200": _response("Comparative enrichments", _schema_ref("GenericObject"))}},
            "post": {"tags": ["Compare"], "summary": "Write comparative enrichments", "operationId": "saveEnrichments", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Saved enrichments", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/auth/status": {
            "get": {"tags": ["Auth"], "summary": "Read auth provider status", "operationId": "getAuthStatus", "responses": {"200": _response("Current auth state", _schema_ref("AuthStatus"))}},
        },
        "/api/auth/key": {
            "post": {"tags": ["Auth"], "summary": "Save a direct API key", "operationId": "saveApiKey", "requestBody": {"required": True, "content": _json_content({"type": "object", "properties": {"key": {"type": "string"}, "provider": {"type": "string"}}, "required": ["key"], "additionalProperties": False})}, "responses": {"200": _response("Updated auth status", _schema_ref("AuthStatus")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/auth/start": {
            "post": {"tags": ["Auth"], "summary": "Start OAuth/device auth flow", "operationId": "startAuthFlow", "responses": {"200": _response("Started auth flow", _schema_ref("GenericObject"))}},
        },
        "/api/auth/poll": {
            "post": {"tags": ["Auth"], "summary": "Poll OAuth/device auth flow", "operationId": "pollAuthFlow", "responses": {"200": _response("Auth poll result", _schema_ref("GenericObject"))}},
        },
        "/api/auth/logout": {
            "post": {"tags": ["Auth"], "summary": "Clear auth credentials", "operationId": "logoutAuth", "responses": {"200": _response("Logout result", _schema_ref("GenericObject"))}},
        },
        "/api/clef/clear": {
            "post": {"tags": ["Compare"], "summary": "Clear CLEF reference forms and optional caches", "operationId": "clearClefData", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("CLEF clear summary", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/worker/status": {
            "get": {"tags": ["Jobs"], "summary": "Read persistent worker health", "operationId": "getWorkerStatus", "responses": {"200": _response("Worker status", _schema_ref("GenericObject"))}},
        },
        "/api/export/lingpy": {
            "get": {"tags": ["Export"], "summary": "Download LingPy TSV export", "operationId": "downloadLingPyExport", "responses": {"200": {"description": "LingPy TSV export", "content": _binary_content("text/tab-separated-values")}}},
        },
        "/api/export/nexus": {
            "get": {"tags": ["Export"], "summary": "Download NEXUS export", "operationId": "downloadNexusExport", "responses": {"200": {"description": "NEXUS export", "content": _binary_content("application/octet-stream")}}},
        },
        "/api/contact-lexemes/coverage": {
            "get": {"tags": ["Compare"], "summary": "Read CLEF provider coverage", "operationId": "getContactLexemeCoverage", "responses": {"200": _response("CLEF coverage payload", _schema_ref("GenericObject"))}},
        },
        "/api/tags": {
            "get": {"tags": ["Tags"], "summary": "Read tag definitions and assignments", "operationId": "getTags", "responses": {"200": _response("Tags payload", _schema_ref("GenericObject"))}},
        },
        "/api/spectrogram": {
            "get": {"tags": ["Media"], "summary": "Generate or read spectrogram PNG", "operationId": "getSpectrogram", "parameters": [_parameter("speaker", "query", {"type": "string"}), _parameter("start", "query", {"type": "number"}), _parameter("end", "query", {"type": "number"}), _parameter("audio", "query", {"type": "string"}), _parameter("force", "query", {"type": "string"})], "responses": {"200": {"description": "Spectrogram image", "content": _binary_content("image/png")}}},
        },
        "/api/lexeme/search": {
            "get": {"tags": ["Search"], "summary": "Search lexeme/concept candidates", "operationId": "searchLexemeCandidates", "parameters": [_parameter("speaker", "query", {"type": "string"}), _parameter("variants", "query", {"type": "string"}), _parameter("concept_id", "query", {"type": "string"}), _parameter("language", "query", {"type": "string"}), _parameter("tiers", "query", {"type": "string"}), _parameter("limit", "query", {"type": "integer"}), _parameter("max_distance", "query", {"type": "number"})], "responses": {"200": _response("Candidate ranges", _schema_ref("GenericObject"))}},
        },
        "/api/onboard/speaker": {
            "post": {"tags": ["Onboarding"], "summary": "Upload raw audio and optional CSV files for one speaker", "operationId": "onboardSpeaker", "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"speaker_id": {"type": "string"}, "audio": {"type": "string", "format": "binary"}, "csv": {"type": "string", "format": "binary"}, "commentsCsv": {"type": "string", "format": "binary"}}, "required": ["speaker_id", "audio"], "additionalProperties": True}}}}, "responses": {"200": _response("Onboarding job started", _schema_ref("GenericJobResponse")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/onboard/speaker/status": {
            "post": {"tags": ["Onboarding"], "summary": "Poll onboarding job status", "operationId": "pollOnboardSpeaker", "requestBody": {"required": True, "content": _json_content({"type": "object", "properties": {"jobId": {"type": "string"}, "job_id": {"type": "string"}}, "additionalProperties": False})}, "responses": {"200": _response("Onboarding job status", _schema_ref("GenericJobResponse"))}},
        },
        "/api/normalize": {
            "post": {"tags": ["Audio"], "summary": "Start audio normalization", "operationId": "startNormalize", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Normalization job started", _schema_ref("GenericJobResponse"))}},
        },
        "/api/normalize/status": {
            "post": {"tags": ["Audio"], "summary": "Poll normalization status", "operationId": "pollNormalize", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Normalization status", _schema_ref("GenericJobResponse"))}},
        },
        "/api/stt": {
            "post": {"tags": ["STT"], "summary": "Start STT", "operationId": "startStt", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("STT job started", _schema_ref("GenericJobResponse"))}},
        },
        "/api/stt/status": {
            "post": {"tags": ["STT"], "summary": "Poll STT status", "operationId": "pollStt", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("STT status", _schema_ref("GenericJobResponse"))}},
        },
        "/api/suggest": {
            "post": {"tags": ["Annotations"], "summary": "Request annotation suggestions", "operationId": "requestSuggestions", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Suggestion payload", _schema_ref("GenericObject"))}},
        },
        "/api/chat/session": {
            "post": {"tags": ["Chat"], "summary": "Create or resume a chat session", "operationId": "startChatSession", "requestBody": {"required": False, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Chat session payload", _schema_ref("GenericObject"))}},
        },
        "/api/chat/run": {
            "post": {"tags": ["Chat"], "summary": "Start a chat run", "operationId": "runChat", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Chat job started", _schema_ref("GenericJobResponse"))}},
        },
        "/api/chat/run/status": {
            "post": {"tags": ["Chat"], "summary": "Poll chat run status", "operationId": "pollChat", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Chat job status", _schema_ref("GenericJobResponse"))}},
        },
        "/api/tags/merge": {
            "post": {"tags": ["Tags"], "summary": "Merge tag definitions", "operationId": "mergeTags", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Merged tags", _schema_ref("GenericObject"))}},
        },
        "/api/concepts/import": {
            "post": {"tags": ["Annotations"], "summary": "Import concepts CSV", "operationId": "importConcepts", "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]}}}}, "responses": {"200": _response("Imported concepts summary", _schema_ref("GenericObject"))}},
        },
        "/api/tags/import": {
            "post": {"tags": ["Tags"], "summary": "Import tags from CSV", "operationId": "importTags", "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]}}}}, "responses": {"200": _response("Imported tags summary", _schema_ref("GenericObject"))}},
        },
        "/api/lexeme-notes": {
            "post": {"tags": ["Compare"], "summary": "Write or delete a lexeme note", "operationId": "writeLexemeNote", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Lexeme notes result", _schema_ref("GenericObject"))}},
        },
        "/api/lexeme-notes/import": {
            "post": {"tags": ["Compare"], "summary": "Import lexeme notes from CSV", "operationId": "importLexemeNotes", "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"speaker_id": {"type": "string"}, "csv": {"type": "string", "format": "binary"}}, "required": ["speaker_id", "csv"]}}}}, "responses": {"200": _response("Imported lexeme notes summary", _schema_ref("GenericObject"))}},
        },
        "/api/offset/detect": {
            "post": {"tags": ["Offsets"], "summary": "Detect a constant timestamp offset", "operationId": "detectTimestampOffset", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Offset-detect job started or result payload", _schema_ref("GenericObject"))}},
        },
        "/api/offset/detect-from-pair": {
            "post": {"tags": ["Offsets"], "summary": "Detect a timestamp offset from trusted anchor pairs", "operationId": "detectTimestampOffsetFromPair", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Offset-detect-from-pair job started or result payload", _schema_ref("GenericObject"))}},
        },
        "/api/offset/apply": {
            "post": {"tags": ["Offsets"], "summary": "Apply a constant timestamp shift", "operationId": "applyTimestampOffset", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Timestamp shift result", _schema_ref("GenericObject"))}},
        },
        "/api/compute/status": {
            "post": {"tags": ["Compute"], "summary": "Poll any compute job by job ID", "operationId": "pollComputeAny", "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Compute job status", _schema_ref("GenericJobResponse"))}},
        },
        "/api/compute/{computeType}": {
            "post": {"tags": ["Compute"], "summary": "Start a compute job", "operationId": "startCompute", "parameters": [_parameter("computeType", "path", {"type": "string"}, required=True)], "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Compute job started", _schema_ref("GenericJobResponse")), "400": _response("Unknown or invalid compute type", _schema_ref("ErrorResponse"))}},
        },
        "/api/compute/{computeType}/status": {
            "post": {"tags": ["Compute"], "summary": "Poll a typed compute job", "operationId": "pollComputeTyped", "parameters": [_parameter("computeType", "path", {"type": "string"}, required=True)], "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Typed compute job status", _schema_ref("GenericJobResponse"))}},
        },
        "/api/{computeType}/status": {
            "post": {"tags": ["Compute"], "summary": "Compatibility alias for compute status", "operationId": "pollComputeCompatStatus", "parameters": [_parameter("computeType", "path", {"type": "string"}, required=True)], "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Compatibility compute job status", _schema_ref("GenericJobResponse"))}},
        },
        "/api/mcp/exposure": {
            "get": {"tags": ["MCP"], "summary": "Read the active MCP exposure configuration", "operationId": "getMcpExposure", "parameters": [_parameter("mode", "query", {"type": "string", "enum": ["active", "default", "all"]}, description="Exposure mode override.")], "responses": {"200": _response("MCP exposure payload", _schema_ref("GenericObject"))}},
        },
        "/api/mcp/tools": {
            "get": {"tags": ["MCP"], "summary": "List MCP tool schemas exposed by PARSE", "operationId": "listMcpTools", "parameters": [_parameter("mode", "query", {"type": "string", "enum": ["active", "default", "all"]}, description="Exposure mode override.")], "responses": {"200": _response("MCP tool catalog", _schema_ref("McpToolCatalog"))}},
        },
        "/api/mcp/tools/{toolName}": {
            "get": {"tags": ["MCP"], "summary": "Read one MCP tool schema", "operationId": "getMcpTool", "parameters": [_parameter("toolName", "path", {"type": "string"}, required=True), _parameter("mode", "query", {"type": "string", "enum": ["active", "default", "all"]})], "responses": {"200": _response("MCP tool schema", _schema_ref("ToolSpec")), "404": _response("Unknown or hidden tool", _schema_ref("ErrorResponse"))}},
            "post": {"tags": ["MCP"], "summary": "Execute one MCP-visible tool over HTTP", "operationId": "executeMcpTool", "parameters": [_parameter("toolName", "path", {"type": "string"}, required=True), _parameter("mode", "query", {"type": "string", "enum": ["active", "default", "all"]})], "requestBody": {"required": True, "content": _json_content({"type": "object", "additionalProperties": True})}, "responses": {"200": _response("Tool execution result", _schema_ref("ToolExecutionResponse")), "400": _response("Validation or execution error", _schema_ref("ErrorResponse")), "404": _response("Unknown or hidden tool", _schema_ref("ErrorResponse"))}},
        },
    }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "PARSE HTTP API",
            "version": "0.1.0",
            "description": info_description,
        },
        "servers": [{"url": base_url}],
        "tags": [
            {"name": "Annotations"},
            {"name": "Audio"},
            {"name": "Auth"},
            {"name": "Chat"},
            {"name": "Compare"},
            {"name": "Compute"},
            {"name": "Config"},
            {"name": "Export"},
            {"name": "Jobs"},
            {"name": "MCP"},
            {"name": "Media"},
            {"name": "Offsets"},
            {"name": "Onboarding"},
            {"name": "Search"},
            {"name": "STT"},
            {"name": "Tags"},
        ],
        "paths": paths,
        "components": components,
        "x-parse-auth": {
            "http_transport": "local-trust",
            "general_api_auth": "none",
            "provider_credentials": {
                "status_endpoint": "/api/auth/status",
                "api_key_endpoint": "/api/auth/key",
                "oauth_start_endpoint": "/api/auth/start",
                "oauth_poll_endpoint": "/api/auth/poll",
                "logout_endpoint": "/api/auth/logout",
                "storage": "config/auth_tokens.json",
            },
        },
    }


def render_swagger_ui_html(openapi_url: str = "/openapi.json") -> str:
    return """<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>PARSE API Docs</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />
  </head>
  <body>
    <div id=\"swagger-ui\"></div>
    <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
    <script>
      window.ui = SwaggerUIBundle({ url: %s, dom_id: '#swagger-ui' });
    </script>
  </body>
</html>
""" % (repr(openapi_url),)


def render_redoc_html(openapi_url: str = "/openapi.json") -> str:
    return """<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>PARSE API ReDoc</title>
    <script src=\"https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js\"></script>
  </head>
  <body>
    <div id=\"redoc-container\"></div>
    <script>
      Redoc.init(%s, {}, document.getElementById('redoc-container'));
    </script>
  </body>
</html>
""" % (repr(openapi_url),)
