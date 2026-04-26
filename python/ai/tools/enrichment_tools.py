from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict

from ..chat_tools import (
    ChatToolSpec,
    ChatToolValidationError,
    _normalize_concept_id,
    _project_loaded_condition,
    _read_json_file,
    _tool_condition,
    _utc_now_iso,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


ENRICHMENT_TOOL_NAMES = (
    "enrichments_read",
    "enrichments_write",
    "lexeme_notes_read",
    "lexeme_notes_write",
)


ENRICHMENT_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "enrichments_read": ChatToolSpec(
                    name="enrichments_read",
                    description=(
                        "Read parse-enrichments.json (cognate sets, similarities, borrowing flags, "
                        "lexeme notes). Optionally filter to specific top-level keys."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "keys": {
                                "type": "array",
                                "maxItems": 16,
                                "items": {"type": "string", "minLength": 1, "maxLength": 64},
                                "description": (
                                    "Optional list of top-level keys to return "
                                    "(e.g. [\"cognate_sets\", \"lexeme_notes\"]). "
                                    "Omit to return the full payload."
                                ),
                            },
                        },
                    },
                ),
    "enrichments_write": ChatToolSpec(
                    name="enrichments_write",
                    description=(
                        "Write keys into parse-enrichments.json. By default merges (shallow) into the "
                        "existing file; pass merge=false for a full replacement. Use with care — this "
                        "file contains cognate sets and borrowing flags."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["enrichments"],
                        "properties": {
                            "enrichments": {
                                "type": "object",
                                "description": "Object to merge into (or replace) parse-enrichments.json.",
                            },
                            "merge": {
                                "type": "boolean",
                                "description": "If true (default), shallow-merge into existing data. If false, replace entirely.",
                            },
                            "dryRun": {
                                "type": "boolean",
                                "description": "If true, preview the resulting top-level keys without writing parse-enrichments.json.",
                            },
                        },
                    },
                    mutability="mutating",
                    supports_dry_run=True,
                    dry_run_parameter="dryRun",
                    preconditions=(
                        _project_loaded_condition(),
                        _tool_condition(
                            "enrichments_payload_provided",
                            "The caller must supply an enrichments object to merge or replace.",
                            kind="input_shape",
                        ),
                    ),
                    postconditions=(
                        _tool_condition(
                            "enrichments_file_updated",
                            "When dryRun=false, parse-enrichments.json is merged or replaced with the supplied payload.",
                            kind="filesystem_write",
                        ),
                    ),
                ),
    "lexeme_notes_read": ChatToolSpec(
                    name="lexeme_notes_read",
                    description=(
                        "Read lexeme-level notes from parse-enrichments.json. "
                        "Optionally filter by speaker and/or conceptId."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "speaker": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "Filter to a single speaker.",
                            },
                            "conceptId": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 128,
                                "description": "Filter to a single concept ID.",
                            },
                        },
                    },
                ),
    "lexeme_notes_write": ChatToolSpec(
                    name="lexeme_notes_write",
                    description=(
                        "Write or delete a single lexeme note in parse-enrichments.json "
                        "(speaker + conceptId key). Supports userNote and importNote fields."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["speaker", "conceptId"],
                        "properties": {
                            "speaker": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "Speaker ID whose lexeme note will be updated.",
                            },
                            "conceptId": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 128,
                                "description": "Concept ID whose note entry will be created, updated, or deleted.",
                            },
                            "userNote": {
                                "type": "string",
                                "maxLength": 4096,
                                "description": "Human-authored note text to store under user_note.",
                            },
                            "importNote": {
                                "type": "string",
                                "maxLength": 4096,
                                "description": "Machine/import provenance note to store under import_note.",
                            },
                            "delete": {
                                "type": "boolean",
                                "description": "If true, removes the note entry for this speaker+concept.",
                            },
                            "dryRun": {
                                "type": "boolean",
                                "description": "If true, preview the resulting lexeme_notes block without writing parse-enrichments.json.",
                            },
                        },
                    },
                    mutability="mutating",
                    supports_dry_run=True,
                    dry_run_parameter="dryRun",
                    preconditions=(
                        _project_loaded_condition(),
                        _tool_condition(
                            "speaker_and_concept_provided",
                            "The caller must provide both speaker and conceptId to identify a single lexeme-note entry.",
                            kind="input_shape",
                        ),
                    ),
                    postconditions=(
                        _tool_condition(
                            "lexeme_note_written",
                            "When dryRun=false, the targeted lexeme_notes entry is created, updated, or deleted in parse-enrichments.json.",
                            kind="filesystem_write",
                        ),
                    ),
                ),
}


def enrichments_read(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Return parse-enrichments.json, optionally filtered to specified top-level keys."""
        payload = _read_json_file(tools.enrichments_path, {})
        if not isinstance(payload, dict):
            payload = {}
        keys = args.get("keys")
        if isinstance(keys, list) and keys:
            payload = {k: payload[k] for k in keys if k in payload}
        return {"readOnly": True, "enrichments": payload}


def enrichments_write(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Shallow-merge (default) or replace parse-enrichments.json with the provided object."""
        incoming = args.get("enrichments")
        if not isinstance(incoming, dict):
            raise ChatToolValidationError("enrichments must be an object")

        merge = bool(args.get("merge", True))
        if merge:
            existing = _read_json_file(tools.enrichments_path, {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update(incoming)
            payload = existing
        else:
            payload = incoming

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "dryRun": True,
                "merge": merge,
                "incomingKeys": list(incoming.keys()),
                "resultingKeys": list(payload.keys()),
                "path": str(tools.enrichments_path),
            }

        tools.enrichments_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {"success": True, "keys": list(payload.keys())}


def lexeme_notes_read(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Return lexeme_notes block from enrichments, optionally filtered by speaker / conceptId."""
        enrichments = _read_json_file(tools.enrichments_path, {})
        notes: Any = enrichments.get("lexeme_notes") or {}
        if not isinstance(notes, dict):
            notes = {}

        speaker_filter = str(args.get("speaker") or "").strip()
        concept_filter = _normalize_concept_id(args.get("conceptId") or "")

        if speaker_filter:
            notes = {speaker_filter: notes.get(speaker_filter, {})}
        if concept_filter:
            filtered: Dict[str, Any] = {}
            for sp, sp_notes in notes.items():
                if isinstance(sp_notes, dict) and concept_filter in sp_notes:
                    filtered[sp] = {concept_filter: sp_notes[concept_filter]}
            notes = filtered

        return {"readOnly": True, "lexeme_notes": notes}


def lexeme_notes_write(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert or delete a single (speaker, conceptId) lexeme note inside parse-enrichments.json."""
        speaker = tools._normalize_speaker(args.get("speaker"))
        concept_id = _normalize_concept_id(args.get("conceptId") or "")
        if not concept_id:
            raise ChatToolValidationError("conceptId is required")

        payload = _read_json_file(tools.enrichments_path, {})
        if not isinstance(payload, dict):
            payload = {}

        notes_block = payload.get("lexeme_notes")
        if not isinstance(notes_block, dict):
            notes_block = {}
            payload["lexeme_notes"] = notes_block

        speaker_block = notes_block.get(speaker)
        if not isinstance(speaker_block, dict):
            speaker_block = {}
            notes_block[speaker] = speaker_block

        if bool(args.get("delete", False)):
            speaker_block.pop(concept_id, None)
            if not speaker_block:
                notes_block.pop(speaker, None)
        else:
            entry = speaker_block.get(concept_id)
            if not isinstance(entry, dict):
                entry = {}
            if "userNote" in args:
                entry["user_note"] = str(args.get("userNote") or "")
            if "importNote" in args:
                entry["import_note"] = str(args.get("importNote") or "")
            entry["updated_at"] = _utc_now_iso()
            speaker_block[concept_id] = entry

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "dryRun": True,
                "speaker": speaker,
                "conceptId": concept_id,
                "delete": bool(args.get("delete", False)),
                "lexeme_notes": payload.get("lexeme_notes") or {},
            }

        tools.enrichments_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {"success": True, "lexeme_notes": payload.get("lexeme_notes") or {}}


ENRICHMENT_TOOL_HANDLERS = {
    "enrichments_read": enrichments_read,
    "enrichments_write": enrichments_write,
    "lexeme_notes_read": lexeme_notes_read,
    "lexeme_notes_write": lexeme_notes_write,
}


__all__ = [
    "ENRICHMENT_TOOL_NAMES",
    "ENRICHMENT_TOOL_SPECS",
    "ENRICHMENT_TOOL_HANDLERS",
    "enrichments_read",
    "enrichments_write",
    "lexeme_notes_read",
    "lexeme_notes_write",
]
