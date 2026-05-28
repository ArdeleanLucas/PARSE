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
            "Tag": {
                "type": "object",
                "required": ["id", "label", "color", "concepts", "lexemeTargets"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "concepts": {"type": "array", "items": {"type": "string"}},
                    "lexemeTargets": {
                        "type": "array",
                        "items": {"type": "string", "pattern": "^[^:]+::[^:]+$"},
                    },
                },
                "additionalProperties": False,
            },
            "TagsPayload": {
                "type": "object",
                "required": ["tags"],
                "properties": {"tags": {"type": "array", "items": _schema_ref("Tag")}},
                "additionalProperties": False,
            },
            "IpaCandidate": {
                "type": "object",
                "required": ["candidate_id", "model", "model_version", "raw_ipa", "decoded_at", "timing_basis", "confidence"],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "model": {"type": "string"},
                    "model_version": {"type": "string"},
                    "raw_ipa": {"type": "string", "description": "Verbatim wav2vec2 IPA decode; not normalized or filtered."},
                    "decoded_at": {"type": "string", "format": "date-time"},
                    "timing_basis": {"type": "string", "enum": ["audition_cue", "manual_anchor", "forced_aligned", "silence_split", "approximate", "stt_segment"]},
                    "confidence": {"type": ["number", "null"]},
                },
                "additionalProperties": True,
            },
            "IpaReviewState": {
                "type": "object",
                "required": ["status", "suggested_ipa", "resolution_type", "evidence_sources", "notes"],
                "properties": {
                    "status": {"type": "string", "enum": ["needs_review", "auto_accepted", "accepted", "rejected"]},
                    "suggested_ipa": {"type": "string"},
                    "resolution_type": {"type": "string"},
                    "evidence_sources": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "IpaCandidatesPayload": {
                "type": "object",
                "required": ["candidates", "review"],
                "properties": {
                    "candidates": {"type": "object", "additionalProperties": {"type": "array", "items": _schema_ref("IpaCandidate")}},
                    "review": {"type": "object", "additionalProperties": _schema_ref("IpaReviewState")},
                },
                "additionalProperties": False,
            },
            "AnnotationIntervalDeleteRequest": {
                "type": "object",
                "required": ["speaker", "concept_id", "start", "end"],
                "properties": {
                    "speaker": {"type": "string"},
                    "concept_id": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                },
                "additionalProperties": False,
            },
            "AnnotationIntervalDeleteRemoved": {
                "type": "object",
                "required": ["concept", "ipa", "ortho", "ortho_words", "speaker"],
                "properties": {
                    "concept": {"type": "integer"},
                    "ipa": {"type": "integer"},
                    "ortho": {"type": "integer"},
                    "ortho_words": {"type": "integer"},
                    "speaker": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            "AnnotationIntervalDeleteResponse": {
                "type": "object",
                "required": ["ok", "speaker", "concept_id", "start", "end", "removed", "backup_path", "tolerance_sec"],
                "properties": {
                    "ok": {"type": "boolean", "const": True},
                    "speaker": {"type": "string"},
                    "concept_id": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "removed": _schema_ref("AnnotationIntervalDeleteRemoved"),
                    "backup_path": {"type": "string"},
                    "tolerance_sec": {"type": "number"},
                },
                "additionalProperties": False,
            },
            "ErrorResponse": {
                "type": "object",
                "required": ["error"],
                "properties": {"error": {"type": "string"}},
                "additionalProperties": True,
            },
            "ConceptCsvRow": {
                "type": "object",
                "required": ["id", "concept_en", "source_item", "source_survey", "custom_order"],
                "properties": {
                    "id": {"type": "string"},
                    "concept_en": {"type": "string"},
                    "source_item": {"type": "string"},
                    "source_survey": {"type": "string"},
                    "custom_order": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "ConceptSurveyLinks": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "SurveyDisplaySettings": {
                "type": "object",
                "required": ["display_label", "display_color"],
                "properties": {
                    "display_label": {"type": "string"},
                    "display_color": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "SurveyOverlapState": {
                "type": "object",
                "required": [
                    "version",
                    "color_coding_enabled",
                    "surveys",
                    "concept_survey_links",
                    "speaker_choices",
                    "speaker_concept_survey_links",
                ],
                "properties": {
                    "version": {"type": "integer"},
                    "color_coding_enabled": {"type": "boolean"},
                    "surveys": {"type": "object", "additionalProperties": _schema_ref("SurveyDisplaySettings")},
                    "concept_survey_links": {"type": "object", "additionalProperties": _schema_ref("ConceptSurveyLinks")},
                    "speaker_choices": {"type": "object", "additionalProperties": _schema_ref("ConceptSurveyLinks")},
                    "speaker_concept_survey_links": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "additionalProperties": _schema_ref("ConceptSurveyLinks"),
                        },
                    },
                },
                "additionalProperties": False,
            },
            "ConceptEntry": {
                "type": "object",
                "required": ["id", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "source_item": {"type": "string"},
                    "source_survey": {"type": "string"},
                    "custom_order": {"type": "number"},
                    "surveys": _schema_ref("ConceptSurveyLinks"),
                    "speaker_surveys": _schema_ref("ConceptSurveyLinks"),
                },
                "additionalProperties": False,
            },
            "ConceptSurveyLinkPostRequest": {
                "type": "object",
                "required": ["survey_id", "source_item"],
                "properties": {
                    "survey_id": {"type": "string"},
                    "source_item": {"type": "string"},
                    "speaker": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "ConceptPromoteSurveyPrimaryRequest": {
                "type": "object",
                "required": ["survey_id", "source_item"],
                "properties": {
                    "survey_id": {"type": "string"},
                    "source_item": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "ConceptSurveyLinkDeleteRequest": {
                "type": "object",
                "required": ["survey_id"],
                "properties": {
                    "survey_id": {"type": "string"},
                    "source_item": {"type": "string"},
                    "speaker": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "ConceptSurveyLinkResponse": {
                "type": "object",
                "required": ["ok", "concept"],
                "properties": {
                    "ok": {"type": "boolean", "const": True},
                    "concept": _schema_ref("ConceptEntry"),
                    "survey_overlap": _schema_ref("SurveyOverlapState"),
                },
                "additionalProperties": False,
            },
            "RelinkByGlossGroup": {
                "type": "object",
                "required": ["keep_concept_id", "merge_concept_ids"],
                "properties": {
                    "canonical_gloss": {"type": "string"},
                    "keep_concept_id": {"type": "string"},
                    "merge_concept_ids": {"type": "array", "items": {"type": "string"}},
                    "labels": {"type": "object", "additionalProperties": {"type": "string"}},
                    "links_by_survey": {"type": "object", "additionalProperties": {"type": "string"}},
                    "source_rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["concept_id", "concept_en"],
                            "properties": {
                                "concept_id": {"type": "string"},
                                "concept_en": {"type": "string"},
                                "source_survey": {"type": "string"},
                                "source_item": {"type": "string"},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "keep_reason": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "RelinkByGlossFuzzyCandidate": {
                "type": "object",
                "required": ["incoming_label", "candidate_label", "reason"],
                "properties": {
                    "incoming_label": {"type": "string"},
                    "candidate_label": {"type": "string"},
                    "candidate_concept_id": {"type": "string"},
                    "reason": {"type": "string", "enum": ["parenthetical_stripped_match", "comma_token_match"]},
                },
                "additionalProperties": False,
            },
            "RelinkByGlossRequest": {
                "type": "object",
                "properties": {
                    "apply": {"type": "boolean"},
                    "accepted_groups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["keep_concept_id", "merge_concept_ids"],
                            "properties": {
                                "keep_concept_id": {"type": "string"},
                                "merge_concept_ids": {"type": "array", "items": {"type": "string"}},
                            },
                            "additionalProperties": True,
                        },
                    },
                },
                "additionalProperties": True,
            },
            "RelinkByGlossResponse": {
                "type": "object",
                "required": ["ok", "applied", "algorithm", "groups", "fuzzy_candidates"],
                "properties": {
                    "ok": {"type": "boolean", "const": True},
                    "applied": {"type": "boolean"},
                    "algorithm": {"type": "string"},
                    "groups": {"type": "array", "items": _schema_ref("RelinkByGlossGroup")},
                    "fuzzy_candidates": {"type": "array", "items": _schema_ref("RelinkByGlossFuzzyCandidate")},
                    "backup_paths": {"type": "array", "items": {"type": "string"}},
                    "annotation_rewrites": {"type": "object", "additionalProperties": {"type": "integer"}},
                },
                "additionalProperties": True,
            },
            "ConceptDeleteResponse": {
                "type": "object",
                "required": ["ok", "deleted_id"],
                "properties": {
                    "ok": {"type": "boolean", "const": True},
                    "deleted_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "ConceptDeleteConflict": {
                "type": "object",
                "required": ["error", "blocking_speakers"],
                "properties": {
                    "error": {"type": "string"},
                    "blocking_speakers": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
            "TagFilteredSpeakerSelector": {
                "description": "Either the literal string 'all' (every workspace speaker) or an explicit list of speaker ids.",
                "oneOf": [
                    {"type": "string", "enum": ["all"]},
                    {"type": "array", "items": {"type": "string"}},
                ],
            },
            "ConceptsByTagRequest": {
                "type": "object",
                "required": ["tagLabels"],
                "properties": {
                    "tagLabels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Non-empty list of tag labels to resolve against the global tag vocabulary.",
                    },
                    "match": {
                        "type": "string",
                        "enum": ["any", "all"],
                        "default": "any",
                        "description": "'any' selects concepts carrying at least one resolved tag; 'all' requires every label to resolve unambiguously and every concept to carry every resolved tag.",
                    },
                    "speakers": _schema_ref("TagFilteredSpeakerSelector"),
                },
                "additionalProperties": False,
            },
            "ConceptByTagHit": {
                "type": "object",
                "required": ["conceptId", "name", "start", "end", "tags"],
                "properties": {
                    "conceptId": {"type": "string"},
                    "name": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Resolved tag labels (not ids)."},
                },
                "additionalProperties": False,
            },
            "ConceptsByTagPerSpeaker": {
                "type": "object",
                "required": ["conceptCount", "concepts"],
                "properties": {
                    "conceptCount": {"type": "integer"},
                    "concepts": {"type": "array", "items": _schema_ref("ConceptByTagHit")},
                },
                "additionalProperties": False,
            },
            "ConceptsByTagResponse": {
                "type": "object",
                "required": ["totalConcepts", "perSpeaker", "unknownTags", "ambiguousTags"],
                "properties": {
                    "totalConcepts": {"type": "integer"},
                    "perSpeaker": {
                        "type": "object",
                        "additionalProperties": _schema_ref("ConceptsByTagPerSpeaker"),
                    },
                    "unknownTags": {"type": "array", "items": {"type": "string"}},
                    "ambiguousTags": {
                        "type": "object",
                        "additionalProperties": {"type": "array", "items": {"type": "string"}},
                        "description": "Map from requested label to the candidate tag ids that share it; rerun refuses to disambiguate.",
                    },
                },
                "additionalProperties": False,
            },
            "LexemesRerunByTagRequest": {
                "type": "object",
                "required": ["tagLabels", "field"],
                "properties": {
                    "tagLabels": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "match": {"type": "string", "enum": ["any", "all"], "default": "any"},
                    "field": {"type": "string", "enum": ["ipa", "ortho", "both"]},
                    "pad": {"type": "number", "enum": [0.0, 0.2, 0.5], "default": 0.2},
                    "speakers": _schema_ref("TagFilteredSpeakerSelector"),
                    "async": {"type": "boolean", "default": True, "description": "Default true starts a tracked compute job and returns 202 + jobId. Set false only for deprecated synchronous compatibility."},
                },
                "additionalProperties": False,
            },
            "LexemeRerunByTagResultEntry": {
                "type": "object",
                "required": ["speaker", "conceptId", "field", "status"],
                "properties": {
                    "speaker": {"type": "string"},
                    "conceptId": {"type": "string"},
                    "field": {"type": "string", "enum": ["ipa", "ortho"]},
                    "status": {"type": "string", "enum": ["ok", "error"]},
                    "text": {"type": "string", "description": "Decoded ortho/ipa value when status='ok'."},
                    "confidence": {"type": "number"},
                    "confidence_source": {"type": "string", "enum": ["avg_logprob", "constant_fallback"]},
                    "confidence_n_tokens": {"type": "integer", "minimum": 0},
                    "statusCode": {"type": "integer", "description": "Per-interval HTTP status preserved when status='error' (404 concept, 409 lock, 500 runner)."},
                    "error": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "LexemesRerunByTagResponse": {
                "type": "object",
                "required": ["jobId", "resolved", "total", "results"],
                "properties": {
                    "jobId": {"type": ["string", "null"], "description": "Null only for deprecated synchronous async=false responses; completed async job results omit jobId and preserve resolved/total/results."},
                    "resolved": _schema_ref("ConceptsByTagResponse"),
                    "total": {"type": "integer"},
                    "results": {"type": "array", "items": _schema_ref("LexemeRerunByTagResultEntry")},
                },
                "additionalProperties": False,
            },
            "CompareCandidate": {"type": ["object", "null"], "properties": {"ipa": {"type": "string"}, "ortho": {"type": "string"}, "start_sec": {"type": "number"}, "end_sec": {"type": "number"}, "source_wav": {"type": "string"}}, "additionalProperties": False},
            "CanonicalLexemeSelection": {"type": "object", "required": ["csv_row_id", "source"], "properties": {"csv_row_id": {"type": "string"}, "survey_id": {"type": "string"}, "source_item": {"type": "string"}, "bucket_key": {"type": "string"}, "variant_label": {"type": "string"}, "realization_index": {"type": "integer", "minimum": 0}, "selected_at": {"type": "string"}, "source": {"type": "string", "enum": ["manual", "migration:canonical_realizations", "default:single-candidate"]}}, "additionalProperties": False},
            "CompareVariant": {"type": "object", "required": ["csv_row_id", "variant_label", "concept_en"], "properties": {"csv_row_id": {"type": "string"}, "variant_label": {"type": "string"}, "concept_en": {"type": "string"}}, "additionalProperties": False},
            "CompareBucket": {"type": "object", "required": ["bucket_key", "survey_id", "source_item", "variants"], "properties": {"bucket_key": {"type": "string"}, "survey_id": {"type": "string"}, "source_item": {"type": "string"}, "variants": {"type": "array", "items": _schema_ref("CompareVariant")}}, "additionalProperties": False},
            "CompareBundle": {
                "type": "object",
                "required": ["bundle_id", "label", "row_ids", "buckets", "candidates", "canonical", "warnings"],
                "properties": {
                    "bundle_id": {"type": "string"},
                    "label": {"type": "string"},
                    "row_ids": {"type": "array", "items": {"type": "string"}},
                    "buckets": {"type": "array", "items": _schema_ref("CompareBucket")},
                    "candidates": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": _schema_ref("CompareCandidate")}},
                    "canonical": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": _schema_ref("CanonicalLexemeSelection")}},
                    "concept_survey_links": {"type": "object", "additionalProperties": _schema_ref("ConceptSurveyLinks")},
                    "speaker_choices": {"type": "object", "additionalProperties": _schema_ref("ConceptSurveyLinks")},
                    "speaker_concept_survey_links": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "additionalProperties": _schema_ref("ConceptSurveyLinks"),
                        },
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
            "CompareBundlesResponse": {"type": "object", "required": ["bundles"], "properties": {"bundles": {"type": "array", "items": _schema_ref("CompareBundle")}}, "additionalProperties": False},
            "CanonicalLexemePutRequest": {"type": "object", "required": ["csv_row_id"], "properties": {"csv_row_id": {"type": "string"}, "realization_index": {"type": "integer", "minimum": 0}}, "additionalProperties": False},
            "CanonicalLexemeMutationResponse": {"type": "object", "required": ["bundle"], "properties": {"bundle": _schema_ref("CompareBundle")}, "additionalProperties": False},
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
            "OnboardSpeakerOverlapConcept": {
                "type": "object",
                "required": ["concept_id", "concept_en", "surveys", "auto_detected"],
                "properties": {
                    "concept_id": {"type": "string"},
                    "concept_en": {"type": "string"},
                    "surveys": {"type": "object", "additionalProperties": {"type": "string"}},
                    "auto_detected": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "OnboardSpeakerPreview": {
                "type": "object",
                "required": ["preview", "speaker", "overlap_concepts"],
                "properties": {
                    "preview": {"type": "boolean", "const": True},
                    "speaker": {"type": "string"},
                    "overlap_concepts": {"type": "array", "items": _schema_ref("OnboardSpeakerOverlapConcept")},
                },
                "additionalProperties": False,
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
        "/api/survey-overlap": {
            "get": {"tags": ["Config"], "summary": "Read survey-overlap sidecar state", "description": "Returns the SurveyOverlapState payload directly (no envelope, no success wrapper).", "operationId": "getSurveyOverlap", "responses": {"200": _response("Survey-overlap sidecar state", _schema_ref("GenericObject")), "500": _response("Server error", _schema_ref("ErrorResponse"))}},
            "post": {
                "tags": ["Config"],
                "summary": "Patch survey labels, links, color toggle, and per-speaker choices",
                "description": "Survey-overlap patches merge by default. Optional boolean flags reset_surveys, reset_speaker_choices, and reset_concept_survey_links clear those sections before any supplied replacement entries are merged. The response is the SurveyOverlapState payload directly (no envelope, no success wrapper).",
                "operationId": "postSurveyOverlap",
                "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))},
                "responses": {"200": _response("Updated survey-overlap state", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse"))},
            },
        },
        "/api/annotations/{speaker}": {
            "get": {"tags": ["Annotations"], "summary": "Read one speaker annotation record", "operationId": "getAnnotation", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True)], "responses": {"200": _response("Normalized annotation payload", _schema_ref("GenericObject")), "400": _response("Invalid speaker", _schema_ref("ErrorResponse")), "404": _response("Missing annotation", _schema_ref("ErrorResponse"))}},
            "post": {"tags": ["Annotations"], "summary": "Save one speaker annotation record", "operationId": "saveAnnotation", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True)], "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Saved annotation payload", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/annotations/intervals/delete": {
            "post": {"tags": ["Annotations"], "summary": "Delete one elicitation interval from a speaker annotation", "description": "Removes the concept-tier interval matching speaker, concept_id, start, and end, plus IPA/ortho/ortho_words/speaker mirror-tier rows at the same time range. The canonical concept row is not deleted. A .bak-<UTC>-pre-interval-delete backup is created before mutation.", "operationId": "deleteAnnotationInterval", "requestBody": {"required": True, "content": _json_content(_schema_ref("AnnotationIntervalDeleteRequest"))}, "responses": {"200": _response("Deleted interval summary", _schema_ref("AnnotationIntervalDeleteResponse")), "400": _response("Validation error", _schema_ref("ErrorResponse")), "404": _response("Missing annotation or matching interval", _schema_ref("ErrorResponse")), "500": _response("Server error", _schema_ref("ErrorResponse"))}, "x-parse": {"idempotent": False, "destructive": True, "backup": "<speaker>.parse.json.bak-<UTC>-pre-interval-delete"}},
        },
        "/api/annotations/{speaker}/ipa-candidates": {
            "get": {"tags": ["Annotations"], "summary": "Read IPA candidate and review sidecars for one speaker", "operationId": "getIpaCandidates", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True)], "responses": {"200": _response("IPA candidate/review sidecars", _schema_ref("IpaCandidatesPayload")), "400": _response("Invalid speaker", _schema_ref("ErrorResponse")), "404": _response("Missing annotation", _schema_ref("ErrorResponse"))}},
        },
        "/api/annotations/{speaker}/ipa-review/{key}": {
            "put": {"tags": ["Annotations"], "summary": "Persist IPA candidate review state", "operationId": "putIpaReview", "parameters": [_parameter("speaker", "path", {"type": "string"}, required=True), _parameter("key", "path", {"type": "string"}, required=True, description="<concept_id>::<tier>::<interval_index>")], "requestBody": {"required": True, "content": _json_content(_schema_ref("GenericObject"))}, "responses": {"200": _response("Persisted review state", _schema_ref("GenericObject")), "400": _response("Validation error", _schema_ref("ErrorResponse")), "404": _response("Missing annotation", _schema_ref("ErrorResponse"))}},
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
        "/api/exports/canonical-lexemes-report": {
            "get": {"tags": ["Export"], "summary": "Download readable canonical lexeme TSV report", "operationId": "downloadCanonicalLexemesReport", "responses": {"200": {"description": "Canonical lexeme TSV report", "content": _binary_content("text/tab-separated-values")}}},
        },
        "/api/compare/bundles": {
            "get": {"tags": ["Compare"], "summary": "Read compare bundle/bucket/variant payload", "operationId": "getCompareBundles", "parameters": [_parameter("speaker", "query", {"type": "string"}, description="Optional speaker id to restrict candidates."), _parameter("bundle_id", "query", {"type": "string"}, description="Optional bundle id to fetch one bundle.")], "responses": {"200": _response("Compare bundles", _schema_ref("CompareBundlesResponse"))}},
        },
        "/api/compare/canonical-lexemes/{bundleId}/{speaker}": {
            "put": {"tags": ["Compare"], "summary": "Set a speaker canonical lexeme for one bundle", "operationId": "putCanonicalLexeme", "parameters": [_parameter("bundleId", "path", {"type": "string"}), _parameter("speaker", "path", {"type": "string"})], "requestBody": {"required": True, "content": _json_content(_schema_ref("CanonicalLexemePutRequest"))}, "responses": {"200": _response("Updated compare bundle", _schema_ref("CanonicalLexemeMutationResponse")), "400": _response("Invalid bundle/csv row/realization request", _schema_ref("ErrorResponse")), "404": _response("Bundle not found", _schema_ref("ErrorResponse")), "409": _response("Selection is stale under active speaker survey overrides", _schema_ref("ErrorResponse"))}},
            "delete": {"tags": ["Compare"], "summary": "Clear a speaker canonical lexeme for one bundle", "operationId": "deleteCanonicalLexeme", "parameters": [_parameter("bundleId", "path", {"type": "string"}), _parameter("speaker", "path", {"type": "string"})], "responses": {"200": _response("Updated compare bundle", _schema_ref("CanonicalLexemeMutationResponse")), "404": _response("Bundle not found", _schema_ref("ErrorResponse"))}},
        },
        "/api/contact-lexemes/coverage": {
            "get": {"tags": ["Compare"], "summary": "Read CLEF provider coverage", "operationId": "getContactLexemeCoverage", "responses": {"200": _response("CLEF coverage payload", _schema_ref("GenericObject"))}},
        },
        "/api/tags": {
            "get": {"tags": ["Tags"], "summary": "Read global concept tags", "operationId": "getTags", "responses": {"200": _response("Tags payload", _schema_ref("TagsPayload"))}},
            "put": {"tags": ["Tags"], "summary": "Replace global concept tags", "operationId": "replaceTags", "requestBody": {"required": True, "content": _json_content(_schema_ref("TagsPayload"))}, "responses": {"200": _response("Tags payload", _schema_ref("TagsPayload")), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
        },
        "/api/spectrogram": {
            "get": {"tags": ["Media"], "summary": "Generate or read spectrogram PNG", "operationId": "getSpectrogram", "parameters": [_parameter("speaker", "query", {"type": "string"}), _parameter("start", "query", {"type": "number"}), _parameter("end", "query", {"type": "number"}), _parameter("audio", "query", {"type": "string"}), _parameter("force", "query", {"type": "string"})], "responses": {"200": {"description": "Spectrogram image", "content": _binary_content("image/png")}}},
        },
        "/api/lexeme/search": {
            "get": {"tags": ["Search"], "summary": "Search lexeme/concept candidates", "operationId": "searchLexemeCandidates", "parameters": [_parameter("speaker", "query", {"type": "string"}), _parameter("variants", "query", {"type": "string"}), _parameter("concept_id", "query", {"type": "string"}), _parameter("language", "query", {"type": "string"}), _parameter("tiers", "query", {"type": "string"}), _parameter("limit", "query", {"type": "integer"}), _parameter("max_distance", "query", {"type": "number"})], "responses": {"200": _response("Candidate ranges", _schema_ref("GenericObject"))}},
        },
        "/api/onboard/speaker": {
            "post": {"tags": ["Onboarding"], "summary": "Upload raw audio and optional CSV files for one speaker", "operationId": "onboardSpeaker", "parameters": [_parameter("preview", "query", {"type": "boolean"}, description="Validate the multipart import and return overlap_concepts without writing files or starting a job.")], "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"speaker_id": {"type": "string"}, "audio": {"type": "string", "format": "binary"}, "csv": {"type": "string", "format": "binary"}, "commentsCsv": {"type": "string", "format": "binary"}, "survey_choices": {"type": "string", "description": "Optional JSON speaker_choices payload. Accepts {speaker: {concept_id: survey_id}} or a bare {concept_id: survey_id} map for the importing speaker."}}, "required": ["speaker_id", "audio"], "additionalProperties": True}}}}, "responses": {"200": _response("Onboarding job started or import-overlap preview", {"oneOf": [_schema_ref("GenericJobResponse"), _schema_ref("OnboardSpeakerPreview")]}), "400": _response("Validation error", _schema_ref("ErrorResponse"))}},
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
        "/api/concepts/relink-by-gloss": {
            "post": {
                "tags": ["Annotations"],
                "summary": "Dry-run or apply strict cross-survey concept relinking by canonical gloss",
                "description": "Dry-run returns strict canonical-gloss groups and fuzzy manual-review candidates. apply=true migrates accepted strict groups, backs up touched files, unions survey links, rewrites concept_id references, and removes merged concepts.csv rows. Fuzzy candidates are never applied automatically.",
                "operationId": "relinkConceptsByGloss",
                "requestBody": {"required": False, "content": _json_content(_schema_ref("RelinkByGlossRequest"))},
                "responses": {
                    "200": _response("Relink-by-gloss dry-run or apply response", _schema_ref("RelinkByGlossResponse")),
                    "400": _response("Invalid accepted group, stale group, or fuzzy candidate submitted for apply", _schema_ref("ErrorResponse")),
                    "500": _response("Backup or write failure", _schema_ref("ErrorResponse")),
                },
                "x-parse": {"idempotent": False, "algorithm": "canonical_survey_gloss:v1-strict"},
            },
        },
        "/api/concepts/{conceptId}": {
            "delete": {"tags": ["Annotations"], "summary": "Delete one unannotated canonical concept row", "operationId": "deleteConcept", "parameters": [{"name": "conceptId", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^[0-9]+$"}}], "responses": {"200": _response("Deleted concept row", _schema_ref("ConceptDeleteResponse")), "400": _response("Invalid concept id", _schema_ref("ErrorResponse")), "404": _response("Concept row not found", _schema_ref("ErrorResponse")), "409": _response("Concept has annotated intervals and cannot be deleted", _schema_ref("ConceptDeleteConflict")), "500": _response("Write failure", _schema_ref("ErrorResponse"))}, "x-parse": {"idempotent": False, "destructive": True}},
        },
        "/api/concepts/{conceptId}/promote-survey-primary": {
            "post": {
                "tags": ["Annotations"],
                "summary": "Promote one linked survey item to the concepts.csv primary link",
                "description": "Moves the current concepts.csv source_survey/source_item pair into concept_survey_links, removes the requested sidecar link, and rewrites the CSV primary to the requested survey item. This endpoint is global and does not accept a speaker field.",
                "operationId": "promoteConceptSurveyPrimary",
                "parameters": [{"name": "conceptId", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^[0-9]+$"}}],
                "requestBody": {"required": True, "content": _json_content(_schema_ref("ConceptPromoteSurveyPrimaryRequest"))},
                "responses": {
                    "200": _response("Promoted concept primary survey link", _schema_ref("ConceptSurveyLinkResponse")),
                    "400": _response("Invalid concept id, missing fields, or requested pair not currently linked", _schema_ref("ErrorResponse")),
                    "404": _response("Concept row not found", _schema_ref("ErrorResponse")),
                    "500": _response("Sidecar or CSV write failure", _schema_ref("ErrorResponse")),
                },
                "x-parse": {"idempotent": False},
            },
        },
        "/api/concepts/{conceptId}/survey-links": {
            "post": {
                "tags": ["Annotations"],
                "summary": "Add or replace one cross-survey link for a concept",
                "description": "Adds a sidecar concept_survey_links entry for an existing concept. Requires survey_id and source_item. Returns the ConceptSurveyLinkResponse contract used by the React client.",
                "operationId": "setConceptSurveyLink",
                "parameters": [{"name": "conceptId", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^[0-9]+(,[0-9]+)*$"}}],
                "requestBody": {"required": True, "content": _json_content(_schema_ref("ConceptSurveyLinkPostRequest"))},
                "responses": {
                    "200": _response("Updated concept survey link", _schema_ref("ConceptSurveyLinkResponse")),
                    "400": _response("Empty body, invalid JSON, missing survey_id, or missing source_item", _schema_ref("ErrorResponse")),
                    "404": _response("Concept row not found", _schema_ref("ErrorResponse")),
                    "409": _response("Concept survey link conflict", _schema_ref("ErrorResponse")),
                },
            },
            "delete": {
                "tags": ["Annotations"],
                "summary": "Remove one sidecar cross-survey link from a concept",
                "description": "Removes a sidecar concept_survey_links entry. source_item is optional so callers can delete by survey only; attempts to delete a legacy concepts.csv link return 409.",
                "operationId": "deleteConceptSurveyLink",
                "parameters": [{"name": "conceptId", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^[0-9]+(,[0-9]+)*$"}}],
                "requestBody": {"required": True, "content": _json_content(_schema_ref("ConceptSurveyLinkDeleteRequest"))},
                "responses": {
                    "200": _response("Updated concept survey link state", _schema_ref("ConceptSurveyLinkResponse")),
                    "400": _response("Empty body, invalid JSON, or missing survey_id", _schema_ref("ErrorResponse")),
                    "404": _response("Concept row not found", _schema_ref("ErrorResponse")),
                    "409": _response("Legacy CSV link cannot be removed or source_item mismatch", _schema_ref("ErrorResponse")),
                },
            },
        },
        "/api/tags/import": {
            "post": {"tags": ["Tags"], "summary": "Import tags from CSV", "operationId": "importTags", "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]}}}}, "responses": {"200": _response("Imported tags summary", _schema_ref("GenericObject"))}},
        },
        "/api/concepts/by-tag": {
            "post": {
                "tags": ["Annotations"],
                "summary": "List concepts carrying selected tags, grouped by speaker",
                "description": "Resolves tagLabels against the global tag vocabulary, expands the speakers selector, and returns matched concepts per speaker without mutating any state. match='all' rejects unknown or ambiguous tagLabels with HTTP 400; match='any' returns them in unknownTags / ambiguousTags so the caller can surface them.",
                "operationId": "listConceptsByTag",
                "requestBody": {"required": True, "content": _json_content(_schema_ref("ConceptsByTagRequest"))},
                "responses": {
                    "200": _response("Per-speaker concept hits", _schema_ref("ConceptsByTagResponse")),
                    "400": _response("Invalid tagLabels, match, speakers shape, or 'all'-mode unresolved labels", _schema_ref("ErrorResponse")),
                    "404": _response("Unknown named speaker in speakers list", _schema_ref("ErrorResponse")),
                },
                "x-parse": {"idempotent": True},
            },
        },
        "/api/lexemes/rerun-by-tag": {
            "post": {
                "tags": ["Annotations"],
                "summary": "Start tracked ORTH/IPA/both rerun job for concepts matched by tags",
                "description": "Default behavior resolves tagLabels and speakers, starts compute job lexemes_rerun_by_tag, and returns 202 + jobId for frontend polling. Set async=false only for deprecated synchronous compatibility, which immediately loops over the matched concept windows and returns the legacy resolved/total/results payload with jobId:null. pad must be one of 0.0, 0.2, 0.5. Ambiguous tagLabels return HTTP 409 before job creation. match='all' with unresolved labels returns HTTP 400. Per-concept errors are surfaced inside results[*] without aborting the batch.",
                "operationId": "rerunLexemesByTag",
                "requestBody": {"required": True, "content": _json_content(_schema_ref("LexemesRerunByTagRequest"))},
                "responses": {
                    "202": _response("Tagged-only rerun compute job started", _schema_ref("GenericJobResponse")),
                    "200": _response("Deprecated async=false per-concept rerun results plus resolved query", _schema_ref("LexemesRerunByTagResponse")),
                    "400": _response("Invalid tagLabels, match, field, pad, speakers, or 'all'-mode unresolved labels", _schema_ref("ErrorResponse")),
                    "404": _response("Unknown named speaker in speakers list", _schema_ref("ErrorResponse")),
                    "409": _response("Ambiguous tagLabels (rerun refuses to disambiguate)", _schema_ref("ErrorResponse")),
                },
                "x-parse": {"idempotent": False},
            },
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
