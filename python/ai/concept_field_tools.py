from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from concept_source_item import read_concepts_csv_rows, write_concepts_csv_rows

from .chat_tools import ChatToolSpec, ChatToolValidationError

if TYPE_CHECKING:
    from .chat_tools import ParseChatTools

CONCEPT_FIELD_COLUMNS = ("source_item", "source_survey", "custom_order")

CONCEPT_FIELD_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "set_concept_field": ChatToolSpec(
        name="set_concept_field",
        description=(
            "Set a constant string value on one column of multiple concept rows. "
            "Use for survey attribution, e.g. source_survey=KLQ for ids 1-136."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["column", "value", "filter"],
            "properties": {
                "column": {
                    "type": "string",
                    "enum": list(CONCEPT_FIELD_COLUMNS),
                    "description": "Concept CSV column to write.",
                },
                "value": {
                    "type": "string",
                    "maxLength": 200,
                    "description": "Constant value to set for every selected row. Commas and newlines are rejected.",
                },
                "filter": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Exactly one selector: id_range, ids, or all=true.",
                    "properties": {
                        "id_range": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 2,
                            "maxItems": 2,
                            "description": "Inclusive integer concept id range.",
                        },
                        "ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 1,
                            "maxItems": 1000,
                            "description": "Explicit integer concept ids.",
                        },
                        "all": {"type": "boolean", "description": "Set true to select all concept rows."},
                    },
                },
            },
        },
    ),
}


def _selected_ids(raw_filter: Dict[str, Any]) -> set[str] | None:
    selectors = [
        key
        for key in ("id_range", "ids", "all")
        if key in raw_filter and raw_filter.get(key) not in (None, False, [])
    ]
    if len(selectors) != 1:
        raise ChatToolValidationError("filter must provide exactly one of id_range, ids, or all=true")

    if selectors[0] == "all":
        if raw_filter.get("all") is not True:
            raise ChatToolValidationError("filter.all must be true")
        return None

    if selectors[0] == "ids":
        return {str(int(value)) for value in raw_filter.get("ids") or []}

    values = raw_filter.get("id_range") or []
    start, end = int(values[0]), int(values[1])
    low, high = sorted((start, end))
    return {str(value) for value in range(low, high + 1)}


def tool_set_concept_field(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    column = str(args.get("column") or "").strip()
    if column not in CONCEPT_FIELD_COLUMNS:
        raise ChatToolValidationError("column must be one of {0}".format(", ".join(CONCEPT_FIELD_COLUMNS)))

    value = str(args.get("value") or "")
    if "\n" in value or "\r" in value or "," in value:
        raise ChatToolValidationError("value may not contain comma or newline")

    raw_filter = args.get("filter")
    if not isinstance(raw_filter, dict):
        raise ChatToolValidationError("filter must be an object")
    selected_ids = _selected_ids(raw_filter)

    concepts_path = tools.project_root / "concepts.csv"
    if not concepts_path.exists():
        raise ChatToolValidationError("concepts.csv not found in project root")

    rows = read_concepts_csv_rows(concepts_path)
    selected_indexes: list[int] = []
    for index, row in enumerate(rows):
        cid = str(row.get("id") or "").strip()
        if selected_ids is None or cid in selected_ids:
            selected_indexes.append(index)

    if not selected_indexes:
        raise ChatToolValidationError("filter selected 0 concept rows")

    updated = 0
    for index in selected_indexes:
        if rows[index].get(column, "") != value:
            rows[index][column] = value
            updated += 1

    write_concepts_csv_rows(concepts_path, rows, atomic=True)
    return {
        "ok": True,
        "column": column,
        "value": value,
        "matched": len(selected_indexes),
        "updated": updated,
        "conceptsPath": "concepts.csv",
    }
