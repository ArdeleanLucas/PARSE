from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import Field, create_model


RUN_FULL_ANNOTATION_PIPELINE_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["speaker_id", "concept_list"],
    "properties": {
        "speaker_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "concept_list": {
            "type": "array",
            "minItems": 1,
            "maxItems": 500,
            "items": {"type": "string", "minLength": 1, "maxLength": 64},
        },
        "run_mode": {
            "type": "string",
            "enum": ["full", "concept-windows", "edited-only"],
            "default": "full",
        },
        "concept_ids": {
            "type": "array",
            "maxItems": 500,
            "items": {"type": "string", "minLength": 1, "maxLength": 64},
        },
        "dryRun": {"type": "boolean"},
    },
}


def _json_type_to_annotation(schema: Dict[str, Any]) -> Any:
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return Literal.__getitem__(tuple(enum_values))
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null = [item for item in schema_type if item != "null"]
        schema_type = non_null[0] if non_null else "object"
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        return List[_json_type_to_annotation(item_schema)]
    if schema_type == "object":
        return Dict[str, Any]
    return Any


def build_args_model(model_name: str, schema: Dict[str, Any]):
    properties = dict(schema.get("properties") or {})
    required = set(schema.get("required") or [])
    field_defs: Dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        field_schema = field_schema if isinstance(field_schema, dict) else {}
        annotation = _json_type_to_annotation(field_schema)
        description = str(field_schema.get("description") or "") or None
        default = ... if field_name in required else field_schema.get("default", None)
        field_defs[field_name] = (annotation, Field(default=default, description=description))
    return create_model(model_name, **field_defs)
