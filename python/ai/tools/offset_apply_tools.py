from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from annotation_offset import interval_concept_identity, shift_annotation_intervals

from ..chat_tools import (
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
    SPEAKER_PATTERN,
    _project_loaded_condition,
    _tool_condition,
    _utc_now_iso,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


OFFSET_APPLY_TOOL_NAMES = ("apply_timestamp_offset",)


OFFSET_APPLY_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "apply_timestamp_offset": ChatToolSpec(
        name="apply_timestamp_offset",
        description=(
            "Shift every annotation interval (start and end) by offsetSec for the "
            "given speaker. Mutates annotations/<speaker>.parse.json. Use dryRun=true "
            "first to preview the shift, then dryRun=false to write."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker", "offsetSec", "dryRun"],
            "properties": {
                "speaker": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    "description": "Speaker ID whose annotation intervals will be shifted.",
                },
                "offsetSec": {
                    "type": "number",
                    "description": "Seconds to add to every interval start/end; negative values pull timestamps earlier.",
                },
                "dryRun": {
                    "type": "boolean",
                    "description": "If true, preview the timestamp shift without writing annotations/<speaker>.parse.json.",
                },
            },
        },
        mutability="mutating",
        supports_dry_run=True,
        dry_run_parameter="dryRun",
        preconditions=(
            _project_loaded_condition(),
            _tool_condition(
                "speaker_annotation_exists",
                "The target speaker must already have an annotation file under annotations/.",
                kind="file_presence",
            ),
        ),
        postconditions=(
            _tool_condition(
                "annotation_timestamps_shifted",
                "When dryRun=false, the speaker's annotation intervals are rewritten with the requested offset.",
                kind="filesystem_write",
            ),
        ),
    ),
}


_interval_concept_identity = interval_concept_identity


def _shift_annotation_intervals(record: Any, offset_sec: float) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Shift annotation intervals by ``offset_sec`` via the shared helper."""
    result = shift_annotation_intervals(
        record,
        offset_sec,
        collect_preview=True,
        preview_limit=5,
    )
    preview = [
        {"tier": item["tier"], "from": item["from"], "to": item["to"]}
        for item in result.preview
    ]
    return result.shifted_intervals, len(result.shifted_concepts), preview


def tool_apply_timestamp_offset(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker_raw = str(args.get("speaker") or "").strip()
    if not speaker_raw or not SPEAKER_PATTERN.match(speaker_raw):
        raise ChatToolValidationError("speaker is required and must match {0}".format(SPEAKER_PATTERN.pattern))
    speaker = speaker_raw

    if "offsetSec" not in args:
        raise ChatToolValidationError("offsetSec is required")
    try:
        offset_sec = float(args.get("offsetSec"))
    except (TypeError, ValueError):
        raise ChatToolValidationError("offsetSec must be a number")
    import math as _math
    if not _math.isfinite(offset_sec):
        raise ChatToolValidationError("offsetSec must be a finite number")
    if abs(offset_sec) < 1e-6:
        raise ChatToolValidationError("offsetSec is effectively zero — nothing to apply")

    if "dryRun" not in args:
        raise ChatToolValidationError("dryRun is required (use true to preview)")
    dry_run = bool(args.get("dryRun"))

    annotation_path = tools._annotation_path_for_speaker(speaker)
    if annotation_path is None or not annotation_path.is_file():
        raise ChatToolValidationError(
            "No annotation file found for speaker '{0}'".format(speaker)
        )

    try:
        record = json.loads(annotation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChatToolExecutionError("Failed to read annotation: {0}".format(exc)) from exc

    shifted_count, shifted_concepts, preview = _shift_annotation_intervals(record, offset_sec)
    if shifted_count == 0:
        raise ChatToolValidationError("No intervals were shifted")

    if dry_run:
        return {
            "readOnly": True,
            "dryRun": True,
            "speaker": speaker,
            "offsetSec": offset_sec,
            "wouldShiftIntervals": shifted_count,
            "wouldShiftConcepts": shifted_concepts,
            "preview": preview,
        }

    if isinstance(record, dict):
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        metadata["modified"] = _utc_now_iso()
        record["metadata"] = metadata

    try:
        annotation_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        raise ChatToolExecutionError("Failed to write annotation: {0}".format(exc)) from exc

    return {
        "readOnly": False,
        "dryRun": False,
        "speaker": speaker,
        "appliedOffsetSec": offset_sec,
        "shiftedIntervals": shifted_count,
        "shiftedConcepts": shifted_concepts,
        "annotationPath": str(annotation_path.relative_to(tools.project_root)),
    }


OFFSET_APPLY_TOOL_HANDLERS = {
    "apply_timestamp_offset": tool_apply_timestamp_offset,
}
