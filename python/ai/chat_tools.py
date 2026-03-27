#!/usr/bin/env python3
"""Bounded PARSE-native chat tools for the built-in AI toolbox.

This module intentionally exposes a strict, read-only tool allowlist.
There is no arbitrary shell execution and no arbitrary filesystem access.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from compare import cognate_compute as cognate_compute_module
except Exception:
    cognate_compute_module = None

try:
    from compare import cross_speaker_match as cross_speaker_match_module
except Exception:
    cross_speaker_match_module = None


ANNOTATION_FILENAME_SUFFIX = ".parse.json"
ANNOTATION_LEGACY_FILENAME_SUFFIX = ".json"
SPEAKER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
TOKEN_RE = re.compile(r"[\w\u0600-\u06FF\u0750-\u077F]+", flags=re.UNICODE)
MUTATING_TOOL_NAME_RE = re.compile(
    r"(save|write|update|edit|patch|delete|remove|create|insert|import|rename|commit)",
    flags=re.IGNORECASE,
)
READ_ONLY_NOTICE = (
    "PARSE chat MVP is read-only. Tools can inspect/analyze data and run background previews, "
    "but they cannot persist annotation/config/enrichment writes."
)


class ChatToolError(Exception):
    """Base chat tool error."""


class ChatToolValidationError(ChatToolError):
    """Tool input validation error."""


class ChatToolExecutionError(ChatToolError):
    """Tool runtime error."""


@dataclass(frozen=True)
class ChatToolSpec:
    """Tool definition for OpenAI function-calling and validation."""

    name: str
    description: str
    parameters: Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_concept_id(value: Any) -> str:
    text = _normalize_space(value)
    if not text:
        return ""

    if text.startswith("#"):
        text = _normalize_space(text[1:])

    if ":" in text:
        text = _normalize_space(text.split(":", 1)[0])

    return text


def _concept_sort_key(concept_id: str) -> Tuple[int, float, str]:
    normalized = _normalize_concept_id(concept_id)
    try:
        return (0, float(normalized), normalized)
    except ValueError:
        return (1, float("inf"), normalized)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(default)

    return payload


def _json_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_schema_type(expected: str, value: Any) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _validate_schema(value: Any, schema: Dict[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, str):
        if not _matches_schema_type(expected_type, value):
            raise ChatToolValidationError(
                "{0} expected {1}, got {2}".format(path, expected_type, _json_type_name(value))
            )

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        if value not in enum_values:
            raise ChatToolValidationError(
                "{0} must be one of {1}".format(path, ", ".join([str(item) for item in enum_values]))
            )

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise ChatToolValidationError("{0} must be at least {1} characters".format(path, min_length))

        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            raise ChatToolValidationError("{0} must be <= {1} characters".format(path, max_length))

        pattern = schema.get("pattern")
        if isinstance(pattern, str) and pattern:
            if not re.match(pattern, value):
                raise ChatToolValidationError("{0} does not match required pattern".format(path))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and float(value) < float(minimum):
            raise ChatToolValidationError("{0} must be >= {1}".format(path, minimum))

        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and float(value) > float(maximum):
            raise ChatToolValidationError("{0} must be <= {1}".format(path, maximum))

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise ChatToolValidationError("{0} must contain at least {1} items".format(path, min_items))

        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            raise ChatToolValidationError("{0} must contain <= {1} items".format(path, max_items))

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, path="{0}[{1}]".format(path, index))

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    raise ChatToolValidationError("{0}.{1} is required".format(path, key))

        properties = schema.get("properties")
        if isinstance(properties, dict):
            additional_allowed = bool(schema.get("additionalProperties", True))
            for key, item_value in value.items():
                if key not in properties:
                    if not additional_allowed:
                        raise ChatToolValidationError("{0}.{1} is not allowed".format(path, key))
                    continue

                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    _validate_schema(item_value, child_schema, path="{0}.{1}".format(path, key))


def _deepcopy_jsonable(payload: Any) -> Any:
    return copy.deepcopy(payload)


class ParseChatTools:
    """Strict read-only tool allowlist for PARSE chat."""

    def __init__(
        self,
        project_root: Path,
        config_path: Optional[Path] = None,
        start_stt_job: Optional[Callable[[str, str, Optional[str]], str]] = None,
        get_job_snapshot: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.config_path = (Path(config_path).expanduser().resolve() if config_path else self.project_root / "config" / "ai_config.json")

        self.annotations_dir = self.project_root / "annotations"
        self.audio_dir = self.project_root / "audio"
        self.peaks_dir = self.project_root / "peaks"
        self.phonetic_rules_path = self.project_root / "config" / "phonetic_rules.json"
        self.sil_config_path = self.project_root / "config" / "sil_contact_languages.json"
        self.project_json_path = self.project_root / "project.json"
        self.source_index_path = self.project_root / "source_index.json"
        self.enrichments_path = self.project_root / "parse-enrichments.json"

        self._start_stt_job = start_stt_job
        self._get_job_snapshot = get_job_snapshot

        self._tool_specs: Dict[str, ChatToolSpec] = {
            "project_context_read": ChatToolSpec(
                name="project_context_read",
                description=(
                    "Read high-level PARSE project context (project metadata, source index summary, "
                    "annotation inventory, and enrichment summary). Read-only."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "include": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "string",
                                "enum": [
                                    "project",
                                    "source_index",
                                    "annotation_inventory",
                                    "enrichments_summary",
                                    "ai_config",
                                    "constraints",
                                ],
                            },
                        },
                        "maxSpeakers": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                },
            ),
            "annotation_read": ChatToolSpec(
                name="annotation_read",
                description=(
                    "Read one speaker annotation JSON safely from annotations/<speaker>.parse.json "
                    "with optional concept filtering. Read-only."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "conceptIds": {
                            "type": "array",
                            "maxItems": 250,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                        },
                        "includeTiers": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "string",
                                "enum": ["ipa", "ortho", "concept", "speaker"],
                            },
                        },
                        "maxIntervals": {"type": "integer", "minimum": 1, "maximum": 5000},
                    },
                },
            ),
            "stt_start": ChatToolSpec(
                name="stt_start",
                description=(
                    "Start a bounded STT background job for a project audio file. "
                    "Returns a jobId for polling with stt_status."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "sourceWav"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                        "language": {"type": "string", "minLength": 1, "maxLength": 32},
                    },
                },
            ),
            "stt_status": ChatToolSpec(
                name="stt_status",
                description="Read status/progress of an existing STT job.",
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["jobId"],
                    "properties": {
                        "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "includeSegments": {"type": "boolean"},
                        "maxSegments": {"type": "integer", "minimum": 1, "maximum": 300},
                    },
                },
            ),
            "cognate_compute_preview": ChatToolSpec(
                name="cognate_compute_preview",
                description=(
                    "Compute a read-only cognate/similarity preview from annotations. "
                    "Does not write parse-enrichments.json."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speakers": {
                            "type": "array",
                            "maxItems": 300,
                            "items": {"type": "string", "minLength": 1, "maxLength": 200},
                        },
                        "conceptIds": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                        },
                        "threshold": {"type": "number", "minimum": 0.01, "maximum": 2.0},
                        "contactLanguages": {
                            "type": "array",
                            "maxItems": 20,
                            "items": {"type": "string", "minLength": 1, "maxLength": 16},
                        },
                        "includeSimilarity": {"type": "boolean"},
                        "maxConcepts": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                },
            ),
            "cross_speaker_match_preview": ChatToolSpec(
                name="cross_speaker_match_preview",
                description=(
                    "Compute read-only cross-speaker match candidates from STT output and existing "
                    "annotations. Accepts sttJobId or inline sttSegments."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "sttJobId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "sttSegments": {
                            "type": "array",
                            "maxItems": 20000,
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "start": {"type": "number"},
                                    "end": {"type": "number"},
                                    "startSec": {"type": "number"},
                                    "endSec": {"type": "number"},
                                    "text": {"type": "string"},
                                    "ipa": {"type": "string"},
                                    "ortho": {"type": "string"},
                                },
                            },
                        },
                        "topK": {"type": "integer", "minimum": 1, "maximum": 20},
                        "minConfidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "maxConcepts": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                },
            ),
            "spectrogram_preview": ChatToolSpec(
                name="spectrogram_preview",
                description=(
                    "Read-only placeholder/backend hook for spectrogram preview requests. "
                    "Validates bounds and reports capability status."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sourceWav", "startSec", "endSec"],
                    "properties": {
                        "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                        "startSec": {"type": "number", "minimum": 0.0},
                        "endSec": {"type": "number", "minimum": 0.0},
                        "windowSize": {
                            "type": "integer",
                            "enum": [256, 512, 1024, 2048, 4096],
                        },
                    },
                },
            ),
        }

    def openai_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return OpenAI tool schema objects for the allowlisted tools."""
        payload: List[Dict[str, Any]] = []
        for spec in self._tool_specs.values():
            payload.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": _deepcopy_jsonable(spec.parameters),
                    },
                }
            )
        return payload

    def tool_names(self) -> List[str]:
        """Return sorted tool names in allowlist."""
        return sorted(self._tool_specs.keys())

    def _finalize_read_only_result(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = _deepcopy_jsonable(payload)
        result["mode"] = "read-only"
        result["readOnly"] = True
        if "previewOnly" not in result:
            result["previewOnly"] = True
        if "readOnlyNotice" not in result:
            result["readOnlyNotice"] = READ_ONLY_NOTICE
        return result

    def execute(self, tool_name: str, raw_args: Any) -> Dict[str, Any]:
        """Execute a validated allowlisted tool."""
        name = str(tool_name or "").strip()
        if name not in self._tool_specs:
            if MUTATING_TOOL_NAME_RE.search(name):
                raise ChatToolValidationError(
                    "Mutating tool calls are disabled: {0}. {1}".format(name, READ_ONLY_NOTICE)
                )
            raise ChatToolValidationError("Tool is not allowlisted: {0}".format(name))

        # Defense-in-depth: mutating tool names remain blocked even if added by mistake.
        if MUTATING_TOOL_NAME_RE.search(name):
            raise ChatToolValidationError(
                "Mutating tool calls are disabled in read-only mode: {0}.".format(name)
            )

        args = raw_args
        if args is None:
            args = {}
        if isinstance(args, str):
            text = args.strip()
            if not text:
                args = {}
            else:
                try:
                    args = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ChatToolValidationError(
                        "Tool arguments must be valid JSON: {0}".format(exc)
                    )

        if not isinstance(args, dict):
            raise ChatToolValidationError("Tool arguments must be a JSON object")

        spec = self._tool_specs[name]
        _validate_schema(args, spec.parameters)

        handler_name = "_tool_{0}".format(name)
        handler = getattr(self, handler_name, None)
        if not callable(handler):
            raise ChatToolExecutionError("Tool handler missing for {0}".format(name))

        result = handler(args)
        if not isinstance(result, dict):
            raise ChatToolExecutionError("Tool handler must return a JSON object")

        return {
            "tool": name,
            "ok": True,
            "result": self._finalize_read_only_result(result),
        }

    def _normalize_speaker(self, raw_speaker: Any) -> str:
        speaker = _normalize_space(raw_speaker)
        if not speaker:
            raise ChatToolValidationError("speaker is required")

        if not SPEAKER_PATTERN.match(speaker):
            raise ChatToolValidationError("speaker contains unsupported characters")

        return speaker

    def _resolve_project_path(self, raw_path: str, allowed_roots: Sequence[Path]) -> Path:
        value = str(raw_path or "").strip()
        if not value:
            raise ChatToolValidationError("Path is required")

        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate

        resolved = candidate.resolve()

        try:
            resolved.relative_to(self.project_root)
        except ValueError:
            raise ChatToolValidationError("Path escapes project root")

        if allowed_roots:
            allowed = False
            for root in allowed_roots:
                root_resolved = root.resolve()
                try:
                    resolved.relative_to(root_resolved)
                    allowed = True
                    break
                except ValueError:
                    continue

            if not allowed:
                safe_roots = [str(root.resolve()) for root in allowed_roots]
                raise ChatToolValidationError(
                    "Path is outside allowed roots: {0}".format(", ".join(safe_roots))
                )

        return resolved

    def _annotation_path_for_speaker(self, speaker: str) -> Optional[Path]:
        primary = (self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)).resolve()
        legacy = (self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_LEGACY_FILENAME_SUFFIX)).resolve()

        for candidate in [primary, legacy]:
            try:
                candidate.relative_to(self.annotations_dir.resolve())
            except ValueError:
                continue
            if candidate.exists() and candidate.is_file():
                return candidate

        return None

    def _tool_project_context_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        include_values = args.get("include")
        if not isinstance(include_values, list) or not include_values:
            include = [
                "project",
                "source_index",
                "annotation_inventory",
                "enrichments_summary",
                "constraints",
            ]
        else:
            include = [str(value) for value in include_values]

        max_speakers = int(args.get("maxSpeakers", 50) or 50)

        out: Dict[str, Any] = {
            "readOnly": True,
            "previewOnly": True,
            "fetchedAt": _utc_now_iso(),
        }

        if "project" in include:
            out["project"] = _read_json_file(self.project_json_path, {})

        if "source_index" in include:
            source_index = _read_json_file(self.source_index_path, {})
            speakers_block = source_index.get("speakers") if isinstance(source_index, dict) else {}
            speaker_summary: Dict[str, Any] = {}
            if isinstance(speakers_block, dict):
                speaker_names = sorted(speakers_block.keys())
                truncated = len(speaker_names) > max_speakers
                for speaker in speaker_names[:max_speakers]:
                    payload = speakers_block.get(speaker)
                    if not isinstance(payload, dict):
                        continue

                    source_wavs = payload.get("source_wavs")
                    if not isinstance(source_wavs, list):
                        source_wavs = []

                    primary_filename = ""
                    for source_entry in source_wavs:
                        if isinstance(source_entry, dict) and source_entry.get("is_primary"):
                            primary_filename = _normalize_space(source_entry.get("filename"))
                            break
                    if not primary_filename and source_wavs:
                        first = source_wavs[0]
                        if isinstance(first, dict):
                            primary_filename = _normalize_space(first.get("filename"))

                    speaker_summary[speaker] = {
                        "sourceCount": len(source_wavs),
                        "primarySource": primary_filename,
                        "hasCsv": bool(payload.get("has_csv")),
                    }

                out["source_index"] = {
                    "speakerCount": len(speaker_names),
                    "speakers": speaker_summary,
                    "truncated": truncated,
                    "maxSpeakers": max_speakers,
                }
            else:
                out["source_index"] = {
                    "speakerCount": 0,
                    "speakers": {},
                    "truncated": False,
                    "maxSpeakers": max_speakers,
                }

        if "annotation_inventory" in include:
            inventory = {
                "directory": str(self.annotations_dir),
                "exists": self.annotations_dir.exists(),
                "fileCount": 0,
                "sample": [],
            }
            if self.annotations_dir.exists() and self.annotations_dir.is_dir():
                files = sorted([path.name for path in self.annotations_dir.glob("*.json")])
                inventory["fileCount"] = len(files)
                inventory["sample"] = files[:20]
            out["annotation_inventory"] = inventory

        if "enrichments_summary" in include:
            enrichments = _read_json_file(self.enrichments_path, {})
            config = enrichments.get("config") if isinstance(enrichments, dict) else {}
            cognate_sets = enrichments.get("cognate_sets") if isinstance(enrichments, dict) else {}
            similarity = enrichments.get("similarity") if isinstance(enrichments, dict) else {}
            out["enrichments_summary"] = {
                "computedAt": (enrichments.get("computed_at") if isinstance(enrichments, dict) else None),
                "conceptCount": len(cognate_sets) if isinstance(cognate_sets, dict) else 0,
                "similarityConceptCount": len(similarity) if isinstance(similarity, dict) else 0,
                "speakersIncluded": (
                    list(config.get("speakers_included", []))
                    if isinstance(config, dict)
                    else []
                ),
            }

        if "ai_config" in include:
            ai_config = _read_json_file(self.config_path, {})
            chat_config = ai_config.get("chat") if isinstance(ai_config, dict) else {}
            llm_config = ai_config.get("llm") if isinstance(ai_config, dict) else {}
            out["ai_config"] = {
                "llm": {
                    "provider": _normalize_space(llm_config.get("provider")) if isinstance(llm_config, dict) else "",
                    "model": _normalize_space(llm_config.get("model")) if isinstance(llm_config, dict) else "",
                    "api_key_env": _normalize_space(llm_config.get("api_key_env")) if isinstance(llm_config, dict) else "",
                },
                "chat": {
                    "provider": _normalize_space(chat_config.get("provider")) if isinstance(chat_config, dict) else "",
                    "model": _normalize_space(chat_config.get("model")) if isinstance(chat_config, dict) else "",
                    "reasoning_effort": _normalize_space(chat_config.get("reasoning_effort")) if isinstance(chat_config, dict) else "",
                    "read_only": bool(chat_config.get("read_only", True)) if isinstance(chat_config, dict) else True,
                    "attachments_supported": bool(chat_config.get("attachments_supported", False)) if isinstance(chat_config, dict) else False,
                    "max_user_message_chars": _coerce_int(chat_config.get("max_user_message_chars", 8000), 8000) if isinstance(chat_config, dict) else 8000,
                    "max_session_messages": _coerce_int(chat_config.get("max_session_messages", 200), 200) if isinstance(chat_config, dict) else 200,
                },
            }

        if "constraints" in include:
            out["constraints"] = {
                "mode": "read-only",
                "writesAllowed": False,
                "attachmentsSupported": False,
                "readOnlyNotice": READ_ONLY_NOTICE,
                "toolAllowlist": self.tool_names(),
                "safeRoots": [str(self.project_root / "annotations"), str(self.project_root / "audio"), str(self.project_root / "config")],
            }

        return out

    def _tier_intervals(self, annotation: Mapping[str, Any], tier_name: str) -> List[Dict[str, Any]]:
        tiers = annotation.get("tiers") if isinstance(annotation, Mapping) else None
        if not isinstance(tiers, Mapping):
            return []

        target = None
        if tier_name in tiers and isinstance(tiers.get(tier_name), Mapping):
            target = tiers.get(tier_name)
        else:
            for key, value in tiers.items():
                if isinstance(key, str) and key.lower() == tier_name.lower() and isinstance(value, Mapping):
                    target = value
                    break

        if not isinstance(target, Mapping):
            return []

        intervals = target.get("intervals")
        if not isinstance(intervals, list):
            return []

        out: List[Dict[str, Any]] = []
        for item in intervals:
            if isinstance(item, dict):
                start = _coerce_float(item.get("start"), 0.0)
                end = _coerce_float(item.get("end"), start)
                text = str(item.get("text") or "")
                if end < start:
                    continue
                out.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                    }
                )

        out.sort(key=lambda row: (float(row.get("start", 0.0)), float(row.get("end", 0.0))))
        return out

    def _tool_annotation_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        speaker = self._normalize_speaker(args.get("speaker"))
        include_tiers = args.get("includeTiers")
        if isinstance(include_tiers, list) and include_tiers:
            tiers = [str(item).strip().lower() for item in include_tiers if str(item).strip()]
        else:
            tiers = ["ipa", "ortho", "concept", "speaker"]

        max_intervals = int(args.get("maxIntervals", 500) or 500)

        concept_ids_raw = args.get("conceptIds")
        concept_filter: List[str] = []
        if isinstance(concept_ids_raw, list):
            seen: Dict[str, bool] = {}
            for value in concept_ids_raw:
                concept_id = _normalize_concept_id(value)
                if concept_id and concept_id not in seen:
                    seen[concept_id] = True
                    concept_filter.append(concept_id)

        path = self._annotation_path_for_speaker(speaker)
        if path is None:
            return {
                "readOnly": True,
                "speaker": speaker,
                "status": "not_found",
                "message": "Annotation file not found for speaker",
            }

        annotation = _read_json_file(path, {})
        if not isinstance(annotation, dict):
            raise ChatToolExecutionError("Annotation file is not a JSON object")

        concept_intervals = self._tier_intervals(annotation, "concept")

        selected_ranges: List[Tuple[float, float]] = []
        if concept_filter:
            for interval in concept_intervals:
                concept_id = _normalize_concept_id(interval.get("text"))
                if concept_id in concept_filter:
                    selected_ranges.append((float(interval["start"]), float(interval["end"])))

        def interval_selected(interval: Mapping[str, Any]) -> bool:
            if not selected_ranges:
                return True

            start = _coerce_float(interval.get("start"), 0.0)
            end = _coerce_float(interval.get("end"), start)
            for range_start, range_end in selected_ranges:
                if (min(end, range_end) - max(start, range_start)) > 0:
                    return True
                if abs(start - range_start) <= 0.0005 and abs(end - range_end) <= 0.0005:
                    return True
            return False

        tier_payload: Dict[str, Any] = {}
        truncation: Dict[str, bool] = {}

        for tier_name in tiers:
            intervals = self._tier_intervals(annotation, tier_name)
            filtered = [interval for interval in intervals if interval_selected(interval)]
            truncated = len(filtered) > max_intervals
            tier_payload[tier_name] = filtered[:max_intervals]
            truncation[tier_name] = truncated

        return {
            "readOnly": True,
            "speaker": speaker,
            "source": str(path),
            "conceptFilter": concept_filter,
            "tiers": tier_payload,
            "truncated": truncation,
            "maxIntervals": max_intervals,
            "metadata": annotation.get("metadata") if isinstance(annotation.get("metadata"), dict) else {},
        }

    def _tool_stt_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._start_stt_job is None:
            raise ChatToolExecutionError("STT start callback is unavailable")

        speaker = self._normalize_speaker(args.get("speaker"))
        source_wav = str(args.get("sourceWav") or "").strip()
        if not source_wav:
            raise ChatToolValidationError("sourceWav is required")

        safe_path = self._resolve_project_path(source_wav, allowed_roots=[self.audio_dir])
        project_relative = str(safe_path.relative_to(self.project_root))

        language_raw = args.get("language")
        language = str(language_raw).strip() if language_raw is not None else None
        if language == "":
            language = None

        job_id = self._start_stt_job(speaker, project_relative, language)

        return {
            "readOnly": True,
            "previewOnly": True,
            "jobId": job_id,
            "status": "running",
            "speaker": speaker,
            "sourceWav": project_relative,
            "message": "STT job started. Poll with stt_status.",
        }

    def _tool_stt_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._get_job_snapshot is None:
            raise ChatToolExecutionError("Job snapshot callback is unavailable")

        job_id = str(args.get("jobId") or "").strip()
        if not job_id:
            raise ChatToolValidationError("jobId is required")

        include_segments = bool(args.get("includeSegments", False))
        max_segments = int(args.get("maxSegments", 30) or 30)

        snapshot = self._get_job_snapshot(job_id)
        if snapshot is None:
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "not_found",
                "message": "Unknown jobId",
            }

        if snapshot.get("type") != "stt":
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "invalid_job_type",
                "expected": "stt",
                "actual": snapshot.get("type"),
            }

        result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
        payload: Dict[str, Any] = {
            "readOnly": True,
            "jobId": job_id,
            "status": snapshot.get("status"),
            "progress": snapshot.get("progress"),
            "segmentsProcessed": snapshot.get("segmentsProcessed"),
            "totalSegments": snapshot.get("totalSegments"),
            "error": snapshot.get("error"),
            "speaker": result.get("speaker"),
            "sourceWav": result.get("sourceWav"),
        }

        if include_segments and isinstance(result.get("segments"), list):
            segments = result.get("segments", [])
            payload["segments"] = segments[:max_segments]
            payload["segmentsTruncated"] = len(segments) > max_segments
            payload["segmentCount"] = len(segments)

        return payload

    def _tool_cognate_compute_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if cognate_compute_module is None:
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "unavailable",
                "message": "compare.cognate_compute module is unavailable",
            }

        threshold = _coerce_float(args.get("threshold"), 0.60)
        if threshold <= 0:
            raise ChatToolValidationError("threshold must be > 0")

        include_similarity = bool(args.get("includeSimilarity", True))
        max_concepts = int(args.get("maxConcepts", 40) or 40)

        speaker_values = args.get("speakers")
        speaker_filter: List[str] = []
        if isinstance(speaker_values, list):
            seen: Dict[str, bool] = {}
            for raw_speaker in speaker_values:
                speaker = _normalize_space(raw_speaker)
                if speaker and speaker not in seen:
                    seen[speaker] = True
                    speaker_filter.append(speaker)

        concept_values = args.get("conceptIds")
        concept_filter: List[str] = []
        if isinstance(concept_values, list):
            seen_concepts: Dict[str, bool] = {}
            for raw_concept in concept_values:
                concept_id = _normalize_concept_id(raw_concept)
                if concept_id and concept_id not in seen_concepts:
                    seen_concepts[concept_id] = True
                    concept_filter.append(concept_id)

        contact_override_raw = args.get("contactLanguages")
        contact_override: List[str] = []
        if isinstance(contact_override_raw, list):
            contact_override = [str(item).strip().lower() for item in contact_override_raw if str(item).strip()]

        contact_languages_from_config, refs_by_concept = cognate_compute_module.load_contact_language_data(
            self.sil_config_path
        )
        contact_languages = contact_override or contact_languages_from_config

        forms_by_concept, discovered_speakers = cognate_compute_module.load_annotations(self.annotations_dir)

        speaker_filter_set = set(speaker_filter)
        concept_filter_set = set(concept_filter)

        filtered_forms: Dict[str, List[Any]] = {}
        for raw_concept_id, records in forms_by_concept.items():
            concept_id = _normalize_concept_id(raw_concept_id)
            if not concept_id:
                continue
            if concept_filter_set and concept_id not in concept_filter_set:
                continue

            kept: List[Any] = []
            for record in records:
                speaker = _normalize_space(getattr(record, "speaker", ""))
                if speaker_filter_set and speaker not in speaker_filter_set:
                    continue
                kept.append(record)

            if kept:
                filtered_forms[concept_id] = kept

        if concept_filter:
            selected_concepts = [concept for concept in concept_filter if concept in filtered_forms]
        else:
            selected_concepts = sorted(filtered_forms.keys(), key=_concept_sort_key)

        truncated = len(selected_concepts) > max_concepts
        if truncated:
            selected_concepts = selected_concepts[:max_concepts]
            filtered_forms = {
                concept_id: filtered_forms.get(concept_id, [])
                for concept_id in selected_concepts
                if concept_id in filtered_forms
            }

        concept_specs = [
            cognate_compute_module.ConceptSpec(concept_id=concept_id, label="")
            for concept_id in selected_concepts
        ]

        cognate_sets = cognate_compute_module._compute_cognate_sets_with_lingpy(
            filtered_forms,
            concept_specs,
            threshold,
        )

        similarity: Dict[str, Any] = {}
        if include_similarity:
            similarity = cognate_compute_module.compute_similarity_scores(
                forms_by_concept=filtered_forms,
                concepts=concept_specs,
                contact_languages=contact_languages,
                refs_by_concept=refs_by_concept,
            )

        if speaker_filter:
            speakers_included = sorted([speaker for speaker in discovered_speakers if speaker in speaker_filter_set])
        else:
            speakers_included = sorted(discovered_speakers)

        preview_payload = {
            "computed_at": _utc_now_iso(),
            "config": {
                "contact_languages": list(contact_languages),
                "speakers_included": speakers_included,
                "concepts_included": selected_concepts,
                "lexstat_threshold": round(float(threshold), 3),
            },
            "cognate_sets": cognate_sets,
            "similarity": similarity,
            "borrowing_flags": {},
            "manual_overrides": {},
        }

        return {
            "readOnly": True,
            "previewOnly": True,
            "appliedToProjectState": False,
            "truncated": truncated,
            "maxConcepts": max_concepts,
            "summary": {
                "conceptCount": len(preview_payload["config"]["concepts_included"]),
                "speakerCount": len(preview_payload["config"]["speakers_included"]),
                "hasSimilarity": include_similarity,
            },
            "enrichmentsPreview": preview_payload,
            "note": "Preview only. parse-enrichments.json was not modified.",
        }

    def _segments_from_payload(self, payload: Sequence[Any]) -> List[Any]:
        if cross_speaker_match_module is None:
            return []

        segments: List[Any] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue

            start_sec = _coerce_float(item.get("start", item.get("startSec", 0.0)), 0.0)
            end_sec = _coerce_float(item.get("end", item.get("endSec", start_sec)), start_sec)
            if end_sec < start_sec:
                end_sec = start_sec

            text = _normalize_space(item.get("text"))
            ipa = _normalize_space(item.get("ipa"))
            ortho = _normalize_space(item.get("ortho", text))

            token_source = "{0} {1}".format(ipa, text)
            tokens = [token for token in TOKEN_RE.findall(token_source.lower()) if token]
            deduped_tokens: List[str] = []
            seen: Dict[str, bool] = {}
            for token in tokens:
                if token in seen:
                    continue
                seen[token] = True
                deduped_tokens.append(token)

            segments.append(
                cross_speaker_match_module.SegmentRecord(
                    index=index,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    text=text,
                    ipa=ipa,
                    ortho=ortho,
                    tokens=deduped_tokens,
                )
            )

        segments.sort(key=lambda row: (float(getattr(row, "start_sec", 0.0)), float(getattr(row, "end_sec", 0.0))))
        for new_index, segment in enumerate(segments):
            segment.index = new_index

        return segments

    def _tool_cross_speaker_match_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if cross_speaker_match_module is None:
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "unavailable",
                "message": "compare.cross_speaker_match module is unavailable",
            }

        top_k = int(args.get("topK", 5) or 5)
        min_confidence = _coerce_float(args.get("minConfidence"), 0.35)
        min_confidence = max(0.0, min(1.0, min_confidence))
        max_concepts = int(args.get("maxConcepts", 100) or 100)

        speaker = _normalize_space(args.get("speaker"))
        raw_segments: List[Any] = []
        source_label = ""

        stt_job_id = _normalize_space(args.get("sttJobId"))
        if stt_job_id:
            if self._get_job_snapshot is None:
                raise ChatToolExecutionError("Job snapshot callback is unavailable")

            snapshot = self._get_job_snapshot(stt_job_id)
            if snapshot is None:
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "status": "not_found",
                    "jobId": stt_job_id,
                    "message": "Unknown sttJobId",
                }

            if snapshot.get("type") != "stt":
                raise ChatToolValidationError("sttJobId does not point to an STT job")

            if snapshot.get("status") != "complete":
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "status": snapshot.get("status"),
                    "jobId": stt_job_id,
                    "progress": snapshot.get("progress"),
                    "message": "STT job is not complete yet",
                }

            result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
            if not speaker:
                speaker = _normalize_space(result.get("speaker") or snapshot.get("meta", {}).get("speaker"))

            segments_obj = result.get("segments")
            if isinstance(segments_obj, list):
                raw_segments = segments_obj
                source_label = "sttJob:{0}".format(stt_job_id)

        if not raw_segments:
            inline_segments = args.get("sttSegments")
            if isinstance(inline_segments, list):
                raw_segments = inline_segments
                source_label = "inline"

        if not raw_segments:
            raise ChatToolValidationError("Provide sttJobId or sttSegments")

        if not speaker:
            speaker = "unknown"

        segments = self._segments_from_payload(raw_segments)
        profiles = cross_speaker_match_module.load_concept_profiles(self.annotations_dir)
        rules = cross_speaker_match_module.load_rules_from_file(self.phonetic_rules_path)

        result_payload = cross_speaker_match_module.match_cross_speaker(
            speaker_id=speaker,
            segments=segments,
            profiles=profiles,
            rules=rules,
            top_k=max(1, int(top_k)),
            min_confidence=min_confidence,
        )

        matches = result_payload.get("matches") if isinstance(result_payload, dict) else []
        if not isinstance(matches, list):
            matches = []

        truncated = len(matches) > max_concepts
        if truncated and isinstance(result_payload, dict):
            result_payload["matches"] = matches[:max_concepts]

        return {
            "readOnly": True,
            "previewOnly": True,
            "appliedToProjectState": False,
            "source": source_label,
            "summary": {
                "segmentCount": len(segments),
                "profileCount": len(profiles),
                "matchConceptCount": len(result_payload.get("matches", [])) if isinstance(result_payload, dict) else 0,
                "truncated": truncated,
                "maxConcepts": max_concepts,
            },
            "matchPreview": result_payload,
            "note": "Preview only. No annotation/enrichment writes were performed.",
        }

    def _tool_spectrogram_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        source_wav = str(args.get("sourceWav") or "").strip()
        if not source_wav:
            raise ChatToolValidationError("sourceWav is required")

        start_sec = _coerce_float(args.get("startSec"), 0.0)
        end_sec = _coerce_float(args.get("endSec"), 0.0)
        if end_sec <= start_sec:
            raise ChatToolValidationError("endSec must be greater than startSec")

        window_size = int(args.get("windowSize", 2048) or 2048)

        safe_audio = self._resolve_project_path(source_wav, allowed_roots=[self.audio_dir])

        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "placeholder",
            "message": (
                "Spectrogram preview backend hook acknowledged, but binary/image generation "
                "is not wired in this MVP."
            ),
            "request": {
                "sourceWav": str(safe_audio.relative_to(self.project_root)),
                "startSec": round(start_sec, 3),
                "endSec": round(end_sec, 3),
                "windowSize": window_size,
            },
            "backendHook": {
                "implemented": False,
                "plannedEndpoint": "/api/compute/spectrograms",
                "notes": "Client-side spectrogram worker remains the active rendering path.",
            },
        }


__all__ = [
    "ChatToolError",
    "ChatToolValidationError",
    "ChatToolExecutionError",
    "ChatToolSpec",
    "ParseChatTools",
]
