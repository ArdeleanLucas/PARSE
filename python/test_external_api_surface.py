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
        "/api/survey-overlap",
        "/api/annotations/{speaker}",
        "/api/annotations/intervals/delete",
        "/api/annotations/{speaker}/ipa-candidates",
        "/api/annotations/{speaker}/ipa-review/{key}",
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
        "/api/exports/canonical-lexemes-report",
        "/api/concept-identity",
        "/api/compare/bundles",
        "/api/compare/canonical-lexemes/{bundleId}/{speaker}",
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
        "/api/concepts/relink-by-gloss",
        "/api/concepts/{conceptId}",
        "/api/concepts/{conceptId}/promote-survey-primary",
        "/api/concepts/{conceptId}/survey-links",
        "/api/concepts/by-tag",
        "/api/lexemes/rerun-by-tag",
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


def test_build_openapi_document_omits_removed_concept_duplicate_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")

    assert "/api/concepts/{conceptId}/duplicate" not in spec["paths"]
    assert "ConceptDuplicateResponse" not in spec["components"]["schemas"]


def test_build_openapi_document_covers_annotation_interval_delete_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    operation = spec["paths"]["/api/annotations/intervals/delete"]["post"]

    assert operation["operationId"] == "deleteAnnotationInterval"
    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AnnotationIntervalDeleteRequest"
    }
    assert set(operation["responses"]) == {"200", "400", "404", "500"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AnnotationIntervalDeleteResponse"
    }
    assert operation["x-parse"] == {"idempotent": False, "destructive": True, "backup": "<speaker>.parse.json.bak-<UTC>-pre-interval-delete"}

    components = spec["components"]["schemas"]
    assert components["AnnotationIntervalDeleteRequest"] == {
        "type": "object",
        "required": ["speaker", "concept_id", "start", "end"],
        "properties": {
            "speaker": {"type": "string"},
            "concept_id": {"type": "string"},
            "start": {"type": "number"},
            "end": {"type": "number"},
        },
        "additionalProperties": False,
    }
    assert components["AnnotationIntervalDeleteResponse"]["required"] == ["ok", "speaker", "concept_id", "start", "end", "removed", "backup_path", "tolerance_sec"]
    assert components["AnnotationIntervalDeleteResponse"]["properties"]["removed"] == {"$ref": "#/components/schemas/AnnotationIntervalDeleteRemoved"}
    assert components["AnnotationIntervalDeleteRemoved"]["properties"] == {
        "concept": {"type": "integer"},
        "ipa": {"type": "integer"},
        "ortho": {"type": "integer"},
        "ortho_words": {"type": "integer"},
        "speaker": {"type": "integer"},
    }


def test_build_openapi_document_covers_concept_delete_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    operation = spec["paths"]["/api/concepts/{conceptId}"]["delete"]

    assert operation["operationId"] == "deleteConcept"
    assert operation["parameters"] == [
        {
            "name": "conceptId",
            "in": "path",
            "required": True,
            "schema": {"type": "string", "pattern": "^[0-9]+$"},
        }
    ]
    assert set(operation["responses"]) == {"200", "400", "404", "409", "500"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptDeleteResponse"
    }
    assert operation["responses"]["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptDeleteConflict"
    }
    assert operation["x-parse"] == {"idempotent": False, "destructive": True}


def test_build_openapi_document_covers_relink_by_gloss_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    operation = spec["paths"]["/api/concepts/relink-by-gloss"]["post"]

    assert operation["operationId"] == "relinkConceptsByGloss"
    assert operation["requestBody"]["required"] is False
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RelinkByGlossRequest"
    }
    assert set(operation["responses"]) == {"200", "400", "500"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RelinkByGlossResponse"
    }
    components = spec["components"]["schemas"]
    assert components["RelinkByGlossResponse"]["required"] == ["ok", "applied", "algorithm", "groups", "fuzzy_candidates"]
    assert components["RelinkByGlossResponse"]["properties"]["annotation_rewrites"] == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }


def test_build_openapi_document_covers_concept_survey_links_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    path = spec["paths"]["/api/concepts/{conceptId}/survey-links"]

    assert set(path) == {"post", "delete"}
    shared_parameter = {
        "name": "conceptId",
        "in": "path",
        "required": True,
        "schema": {"type": "string", "pattern": "^[0-9]+(,[0-9]+)*$"},
    }

    post = path["post"]
    assert post["operationId"] == "setConceptSurveyLink"
    assert post["parameters"] == [shared_parameter]
    assert post["requestBody"]["required"] is True
    assert post["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptSurveyLinkPostRequest"
    }
    assert set(post["responses"]) == {"200", "400", "404", "409"}
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptSurveyLinkResponse"
    }

    delete = path["delete"]
    assert delete["operationId"] == "deleteConceptSurveyLink"
    assert delete["parameters"] == [shared_parameter]
    assert delete["requestBody"]["required"] is True
    assert delete["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptSurveyLinkDeleteRequest"
    }
    assert set(delete["responses"]) == {"200", "400", "404", "409"}
    assert delete["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptSurveyLinkResponse"
    }

    components = spec["components"]["schemas"]
    assert components["ConceptSurveyLinkPostRequest"] == {
        "type": "object",
        "required": ["survey_id", "source_item"],
        "properties": {
            "survey_id": {"type": "string"},
            "source_item": {"type": "string"},
            "speaker": {"type": "string"},
        },
        "additionalProperties": False,
    }
    assert components["ConceptSurveyLinkDeleteRequest"] == {
        "type": "object",
        "required": ["survey_id"],
        "properties": {
            "survey_id": {"type": "string"},
            "source_item": {"type": "string"},
            "speaker": {"type": "string"},
        },
        "additionalProperties": False,
    }
    assert components["ConceptEntry"]["properties"]["speaker_surveys"] == {"$ref": "#/components/schemas/ConceptSurveyLinks"}
    assert components["SurveyOverlapState"]["required"] == [
        "version",
        "color_coding_enabled",
        "surveys",
        "concept_survey_links",
        "speaker_choices",
        "speaker_concept_survey_links",
    ]
    assert components["SurveyOverlapState"]["properties"]["speaker_concept_survey_links"] == {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "additionalProperties": {"$ref": "#/components/schemas/ConceptSurveyLinks"},
        },
    }
    assert components["ConceptSurveyLinkResponse"]["required"] == ["ok", "concept"]
    assert components["ConceptSurveyLinkResponse"]["properties"]["ok"] == {"type": "boolean", "const": True}
    assert components["ConceptSurveyLinkResponse"]["properties"]["concept"] == {"$ref": "#/components/schemas/ConceptEntry"}
    assert components["ConceptSurveyLinkResponse"]["properties"]["survey_overlap"] == {"$ref": "#/components/schemas/SurveyOverlapState"}


def test_build_openapi_document_covers_promote_survey_primary_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    operation = spec["paths"]["/api/concepts/{conceptId}/promote-survey-primary"]["post"]

    assert operation["operationId"] == "promoteConceptSurveyPrimary"
    assert operation["parameters"] == [
        {
            "name": "conceptId",
            "in": "path",
            "required": True,
            "schema": {"type": "string", "pattern": "^[0-9]+$"},
        }
    ]
    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptPromoteSurveyPrimaryRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptSurveyLinkResponse"
    }
    assert set(operation["responses"]) == {"200", "400", "404", "500"}

    assert spec["components"]["schemas"]["ConceptPromoteSurveyPrimaryRequest"] == {
        "type": "object",
        "required": ["survey_id", "source_item"],
        "properties": {
            "survey_id": {"type": "string"},
            "source_item": {"type": "string"},
        },
        "additionalProperties": False,
    }


def test_build_openapi_document_covers_concepts_by_tag_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    operation = spec["paths"]["/api/concepts/by-tag"]["post"]

    assert operation["operationId"] == "listConceptsByTag"
    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptsByTagRequest"
    }
    assert set(operation["responses"]) == {"200", "400", "404"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptsByTagResponse"
    }
    assert operation["x-parse"] == {"idempotent": True}

    components = spec["components"]["schemas"]
    assert components["ConceptsByTagRequest"]["required"] == ["tagLabels"]
    assert components["ConceptsByTagRequest"]["properties"]["match"]["enum"] == ["any", "all"]
    assert components["ConceptsByTagRequest"]["properties"]["speakers"] == {
        "$ref": "#/components/schemas/TagFilteredSpeakerSelector"
    }
    assert components["ConceptsByTagResponse"]["required"] == [
        "totalConcepts",
        "perSpeaker",
        "unknownTags",
        "ambiguousTags",
    ]
    assert components["ConceptByTagHit"]["required"] == ["conceptId", "name", "start", "end", "tags"]
    speaker_selector = components["TagFilteredSpeakerSelector"]
    assert speaker_selector["oneOf"][0] == {"type": "string", "enum": ["all"]}
    assert speaker_selector["oneOf"][1] == {"type": "array", "items": {"type": "string"}}


def test_build_openapi_document_covers_lexemes_rerun_by_tag_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    operation = spec["paths"]["/api/lexemes/rerun-by-tag"]["post"]

    assert operation["operationId"] == "rerunLexemesByTag"
    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/LexemesRerunByTagRequest"
    }
    assert set(operation["responses"]) == {"200", "202", "400", "404", "409"}
    assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GenericJobResponse"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/LexemesRerunByTagResponse"
    }
    assert operation["x-parse"] == {"idempotent": False}

    components = spec["components"]["schemas"]
    assert components["LexemesRerunByTagRequest"]["required"] == ["tagLabels", "field"]
    assert components["LexemesRerunByTagRequest"]["properties"]["field"]["enum"] == ["ipa", "ortho", "both"]
    assert components["LexemesRerunByTagRequest"]["properties"]["pad"]["enum"] == [0.0, 0.2, 0.5]
    assert components["LexemesRerunByTagResponse"]["required"] == ["jobId", "resolved", "total", "results"]
    assert components["LexemesRerunByTagResponse"]["properties"]["resolved"] == {
        "$ref": "#/components/schemas/ConceptsByTagResponse"
    }
    assert components["LexemeRerunByTagResultEntry"]["required"] == [
        "speaker",
        "conceptId",
        "field",
        "status",
    ]
    assert components["LexemeRerunByTagResultEntry"]["properties"]["status"]["enum"] == ["ok", "error"]
    assert components["LexemeRerunByTagResultEntry"]["properties"]["field"]["enum"] == ["ipa", "ortho"]
    assert components["LexemeRerunByTagResultEntry"]["properties"]["confidence"] == {"type": "number"}
    assert components["LexemeRerunByTagResultEntry"]["properties"]["confidence_source"] == {
        "type": "string",
        "enum": ["avg_logprob", "constant_fallback"],
    }
    assert components["LexemeRerunByTagResultEntry"]["properties"]["confidence_n_tokens"] == {"type": "integer", "minimum": 0}


def test_build_openapi_document_covers_survey_overlap_read_write_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    path = spec["paths"]["/api/survey-overlap"]

    assert set(path) == {"get", "post"}
    assert path["get"]["operationId"] == "getSurveyOverlap"
    assert path["post"]["operationId"] == "postSurveyOverlap"
    assert path["post"]["requestBody"]["required"] is True
    description = path["post"]["description"]
    assert "reset_surveys" in description
    assert "reset_speaker_choices" in description
    assert "reset_concept_survey_links" in description
    assert "boolean" in description
    # Response shape contract — bare SurveyOverlapState, no envelope.
    assert "no envelope" in description
    get_description = path["get"].get("description", "")
    assert "no envelope" in get_description


def test_build_openapi_document_restores_old_tags_shape_and_put_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    tags_path = spec["paths"]["/api/tags"]

    assert set(tags_path) == {"get", "put"}
    assert tags_path["get"]["summary"] == "Read global concept tags"
    assert tags_path["get"]["operationId"] == "getTags"
    assert tags_path["put"]["summary"] == "Replace global concept tags"
    assert tags_path["put"]["operationId"] == "replaceTags"
    assert "requestBody" in tags_path["put"]


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

    onboard_post = spec["paths"]["/api/onboard/speaker"]["post"]
    onboard_schema = onboard_post["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert onboard_schema["required"] == ["speaker_id", "audio"]
    assert onboard_schema["properties"]["commentsCsv"] == {"type": "string", "format": "binary"}
    assert onboard_schema["properties"]["survey_choices"]["type"] == "string"
    assert "speaker_choices" in onboard_schema["properties"]["survey_choices"]["description"]
    preview_param = next(param for param in onboard_post["parameters"] if param["name"] == "preview")
    assert preview_param["in"] == "query"
    assert preview_param["schema"] == {"type": "boolean"}
    response_schema = onboard_post["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema == {"oneOf": [{"$ref": "#/components/schemas/GenericJobResponse"}, {"$ref": "#/components/schemas/OnboardSpeakerPreview"}]}


def test_build_mcp_http_catalog_defaults_to_full_safe_surface_without_config(tmp_path: pathlib.Path) -> None:
    catalog = build_mcp_http_catalog(project_root=tmp_path, mode="default")

    tool_names = {tool["name"] for tool in catalog["tools"]}
    assert catalog["mode"] == "default"
    assert catalog["count"] == 72
    assert catalog["exposure"]["mcpToolCount"] == 72
    assert catalog["exposure"]["defaultParseMcpToolCount"] == 68
    assert "delete_speaker" in tool_names
    assert "audio_normalize_start" in tool_names
    assert "clef_clear_data" in tool_names
    assert "csv_only_reimport" in tool_names
    assert "onboard_lexical_speaker" in tool_names
    assert "revert_csv_reimport" in tool_names
    assert "populate_cross_survey_links" in tool_names
    assert "export_annotations_csv" in tool_names
    assert "export_review_data" in tool_names
    assert "transcript_reformat" in tool_names


def test_build_mcp_http_catalog_active_mode_preserves_legacy_surface_for_explicit_false_config(tmp_path: pathlib.Path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config" / "mcp_config.json"
    config_path.write_text('{"expose_all_tools": false}', encoding="utf-8")

    catalog = build_mcp_http_catalog(project_root=tmp_path, mode="active")

    tool_names = {tool["name"] for tool in catalog["tools"]}
    assert catalog["mode"] == "active"
    assert catalog["count"] == 49
    assert catalog["exposure"]["configSource"] == str(config_path)
    assert catalog["exposure"]["mcpToolCount"] == 49
    assert catalog["exposure"]["defaultParseMcpToolCount"] == 68
    assert "annotation_read" in tool_names
    assert "csv_only_reimport" in tool_names
    assert "onboard_lexical_speaker" in tool_names
    assert "revert_csv_reimport" in tool_names
    assert "populate_cross_survey_links" in tool_names
    assert "audio_normalize_start" not in tool_names
    assert "clef_clear_data" not in tool_names
    assert "export_annotations_csv" not in tool_names
    assert "export_review_data" in tool_names


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


def test_build_openapi_document_covers_compare_bundle_contract() -> None:
    spec = build_openapi_document(base_url="http://127.0.0.1:8766")
    components = spec["components"]["schemas"]
    for name in [
        "ConceptIdentityConcept",
        "ConceptIdentityOverrideRequest",
        "ConceptIdentityResponse",
        "CompareBundle",
        "CompareBucket",
        "CompareVariant",
        "CompareCandidate",
        "CanonicalLexemeSelection",
        "CompareBundlesResponse",
        "CanonicalLexemePutRequest",
    ]:
        assert name in components

    concept_identity_path = spec["paths"]["/api/concept-identity"]
    assert set(concept_identity_path) == {"get", "post"}
    assert concept_identity_path["get"]["operationId"] == "getConceptIdentity"
    assert concept_identity_path["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptIdentityResponse"
    }
    assert concept_identity_path["post"]["operationId"] == "writeConceptIdentityOverride"
    assert concept_identity_path["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConceptIdentityOverrideRequest"
    }
    assert spec["paths"]["/api/compare/bundles"]["get"]["operationId"] == "getCompareBundles"
    canonical_path = spec["paths"]["/api/compare/canonical-lexemes/{bundleId}/{speaker}"]
    assert set(canonical_path) == {"put", "delete"}
    assert canonical_path["put"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CanonicalLexemePutRequest"
    }
    compare_bundle = components["CompareBundle"]
    assert compare_bundle["required"] == ["bundle_id", "uid", "label", "row_ids", "buckets", "candidates", "canonical", "warnings"]
    assert compare_bundle["properties"]["uid"] == {"type": "string"}
    assert components["CompareBundlesResponse"]["required"] == ["bundles", "identity_warnings"]
    assert compare_bundle["properties"]["concept_survey_links"] == {
        "type": "object",
        "additionalProperties": {"$ref": "#/components/schemas/ConceptSurveyLinks"},
    }
    assert compare_bundle["properties"]["speaker_choices"] == {
        "type": "object",
        "additionalProperties": {"$ref": "#/components/schemas/ConceptSurveyLinks"},
    }
    assert compare_bundle["properties"]["speaker_concept_survey_links"] == {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "additionalProperties": {"$ref": "#/components/schemas/ConceptSurveyLinks"},
        },
    }
    assert spec["paths"]["/api/exports/canonical-lexemes-report"]["get"]["operationId"] == "downloadCanonicalLexemesReport"
