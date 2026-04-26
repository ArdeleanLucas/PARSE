from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Tuple

from ..chat_tools import (
    ChatToolExecutionError,
    ChatToolSpec,
    READ_ONLY_NOTICE,
    WRITE_ALLOWED_TOOL_NAMES,
    _coerce_float,
    _coerce_int,
    _normalize_concept_id,
    _normalize_space,
    _read_json_file,
    _utc_now_iso,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


PROJECT_READ_TOOL_NAMES = (
    "project_context_read",
    "annotation_read",
    "speakers_list",
)


PROJECT_READ_TOOL_SPECS: Dict[str, ChatToolSpec] = {
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
    "speakers_list": ChatToolSpec(
        name="speakers_list",
        description=(
            "List speakers that currently have annotation files in annotations/. "
            "Read-only inventory helper."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    ),
}


def _tier_intervals(annotation: Mapping[str, Any], tier_name: str) -> List[Dict[str, Any]]:
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


def tool_project_context_read(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
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
        out["project"] = _read_json_file(tools.project_json_path, {})

    if "source_index" in include:
        source_index = _read_json_file(tools.source_index_path, {})
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
            "directory": str(tools.annotations_dir),
            "exists": tools.annotations_dir.exists(),
            "fileCount": 0,
            "sample": [],
        }
        if tools.annotations_dir.exists() and tools.annotations_dir.is_dir():
            files = sorted([path.name for path in tools.annotations_dir.glob("*.json")])
            inventory["fileCount"] = len(files)
            inventory["sample"] = files[:20]
        out["annotation_inventory"] = inventory

    if "enrichments_summary" in include:
        enrichments = _read_json_file(tools.enrichments_path, {})
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
        ai_config = _read_json_file(tools.config_path, {})
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
            "mode": "mostly-read-only",
            "writesAllowed": False,
            "writeAllowedTools": sorted(WRITE_ALLOWED_TOOL_NAMES),
            "attachmentsSupported": False,
            "readOnlyNotice": READ_ONLY_NOTICE,
            "toolAllowlist": tools.tool_names(),
            "safeRoots": [
                str(tools.project_root / "annotations"),
                str(tools.project_root / "audio"),
                str(tools.project_root / "config"),
            ],
        }

    return out


def tool_annotation_read(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker = tools._normalize_speaker(args.get("speaker"))
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

    path = tools._annotation_path_for_speaker(speaker)
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

    concept_intervals = _tier_intervals(annotation, "concept")

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
        intervals = _tier_intervals(annotation, tier_name)
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


def tool_speakers_list(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """List all annotated speakers under annotations/."""
    del args
    speakers: set[str] = set()
    if tools.annotations_dir.is_dir():
        for entry in tools.annotations_dir.iterdir():
            if not entry.is_file():
                continue
            name = entry.name
            if name.endswith(".parse.json"):
                speakers.add(name[: -len(".parse.json")])
            elif name.endswith(".json") and not name.endswith(".parse.json"):
                speakers.add(name[: -len(".json")])

    ordered = sorted(speakers)
    return {
        "readOnly": True,
        "speakers": ordered,
        "count": len(ordered),
    }


PROJECT_READ_TOOL_HANDLERS = {
    "project_context_read": tool_project_context_read,
    "annotation_read": tool_annotation_read,
    "speakers_list": tool_speakers_list,
}
