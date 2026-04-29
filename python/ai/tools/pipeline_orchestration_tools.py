from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from ..chat_tools import (
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
    _project_loaded_condition,
    _tool_condition,
)
from .project_read_tools import tool_speakers_list

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


PIPELINE_ORCHESTRATION_TOOL_NAMES = (
    "pipeline_state_read",
    "pipeline_state_batch",
    "pipeline_run",
)


PIPELINE_ORCHESTRATION_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "pipeline_state_read": ChatToolSpec(
        name="pipeline_state_read",
        description=(
            "Preflight one speaker. Read-only. Returns per-step "
            "``{done, intervals|segments, can_run, reason, "
            "coverage_start_sec, coverage_end_sec, "
            "coverage_fraction, full_coverage}`` plus top-level "
            "``duration_sec``. "
            "IMPORTANT: ``done`` only means 'the tier has ≥1 "
            "non-empty interval'. That is NOT the same as 'the "
            "entire WAV was processed' — a tier whose 128 "
            "intervals only cover the first 30 seconds of a "
            "6-minute recording is still ``done: true`` but "
            "``full_coverage: false``. Gate re-run decisions on "
            "``full_coverage``, not ``done``."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
            },
        },
    ),
    "pipeline_state_batch": ChatToolSpec(
        name="pipeline_state_batch",
        description=(
            "Preflight multiple speakers at once. Read-only. "
            "With no arguments, probes every speaker from "
            "``speakers_list``. Supply ``speakers`` to "
            "restrict. Each row carries the same per-step "
            "fields as ``pipeline_state_read``, including "
            "``full_coverage`` — the actual 'was the entire "
            "WAV processed?' signal (as distinct from "
            "``done``, which only checks for ≥1 non-empty "
            "interval). Top-level summary counts "
            "``blockedSpeakers`` (any step can_run=false) and "
            "``partialCoverageSpeakers`` (any STT/ORTH/IPA "
            "step has full_coverage=false). Ideal for "
            "answering 'can I kick off a full batch and walk "
            "away?' without surprises."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "speakers": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 200},
                    "maxItems": 200,
                    "description": "Optional speaker-id subset. Omit for every annotated speaker.",
                },
            },
        },
    ),
    "pipeline_run": ChatToolSpec(
        name="pipeline_run",
        description=(
            "Kick off a transcription pipeline for ONE speaker — the same "
            "``full_pipeline`` compute the UI uses. Supports any subset of "
            "``normalize / stt / ortho / ipa`` in canonical order. Setting "
            "``steps: ['ortho']`` with ``overwrites: {ortho: true}`` runs the "
            "razhan model full-file against this speaker's working WAV and "
            "overwrites the ortho tier. Returns a jobId; poll via "
            "``compute_status`` (compute_type=\"full_pipeline\") until "
            "``status=complete``. Steps run step-resilient: a failing STT will "
            "not abort ORTH/IPA for the same speaker."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker", "steps"],
            "properties": {
                "speaker": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    "description": "Speaker ID whose pipeline should run.",
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["normalize", "stt", "ortho", "ipa"],
                    },
                    "minItems": 1,
                    "maxItems": 4,
                    "description": "Ordered pipeline subset to execute for this speaker.",
                },
                "overwrites": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "normalize": {"type": "boolean"},
                        "stt": {"type": "boolean"},
                        "ortho": {"type": "boolean"},
                        "ipa": {"type": "boolean"},
                    },
                    "description": (
                        "Per-step overwrite flags. Steps flagged false will "
                        "skip when their tier / cache is already populated; "
                        "flagged true will replace the existing data."
                    ),
                },
                "language": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 32,
                    "description": (
                        "Optional language override forwarded to STT + ORTH "
                        "(razhan). Empty / omitted = auto-detect for STT, "
                        "``sd`` for ORTH (razhan's fine-tuning target)."
                    ),
                },
                "run_mode": {
                    "type": "string",
                    "enum": ["full", "concept-windows", "edited-only"],
                    "default": "full",
                    "description": "Pipeline scope: full-file behavior, all concept windows, or manually adjusted concept windows only.",
                },
                "concept_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 64},
                    "maxItems": 500,
                    "description": "Optional exact concept-id filter used when run_mode is concept-windows or edited-only.",
                },
                "dryRun": {
                    "type": "boolean",
                    "description": "If true, preview the planned compute payload without starting a background job.",
                },
            },
        },
        mutability="mutating",
        supports_dry_run=True,
        dry_run_parameter="dryRun",
        preconditions=(
            _project_loaded_condition(),
            _tool_condition(
                "speaker_ready_for_pipeline",
                "The target speaker must exist in the current project and have the files needed for the requested steps.",
                kind="project_state",
            ),
        ),
        postconditions=(
            _tool_condition(
                "pipeline_job_started",
                "When dryRun=false, a full_pipeline background job is created and can be polled via compute_status.",
                kind="job_state",
            ),
        ),
    ),
}


def tool_pipeline_state_read(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._pipeline_state is None:
        raise ChatToolExecutionError("pipeline state callback is unavailable")
    speaker = tools._normalize_speaker(args.get("speaker"))
    try:
        state = tools._pipeline_state(speaker)
    except Exception as exc:
        raise ChatToolExecutionError("pipeline state lookup failed: {0}".format(exc)) from exc
    if not isinstance(state, dict):
        raise ChatToolExecutionError("pipeline state callback returned non-object")
    payload = {"readOnly": True, "speaker": speaker}
    payload.update(state)
    return payload


def tool_pipeline_state_batch(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._pipeline_state is None:
        raise ChatToolExecutionError("pipeline state callback is unavailable")

    requested = args.get("speakers")
    if requested is None:
        inventory = tool_speakers_list(tools, {})
        speakers = list(inventory.get("speakers") or [])
    elif isinstance(requested, list):
        speakers = []
        for raw in requested:
            normalized = tools._normalize_speaker(raw)
            if normalized and normalized not in speakers:
                speakers.append(normalized)
    else:
        raise ChatToolValidationError("speakers must be a list")

    results: List[Dict[str, Any]] = []
    blocked = 0
    partial_coverage = 0
    for speaker in speakers:
        try:
            state = tools._pipeline_state(speaker)
            if not isinstance(state, dict):
                state = {}
        except Exception as exc:
            state = {"error": str(exc)}
        row: Dict[str, Any] = {"speaker": speaker}
        row.update(state)
        results.append(row)
        step_any_blocked = False
        step_any_partial = False
        for step_name in ("normalize", "stt", "ortho", "ipa"):
            step = state.get(step_name) if isinstance(state, dict) else None
            if not isinstance(step, dict):
                continue
            if step.get("can_run") is False:
                step_any_blocked = True
            if step_name in ("stt", "ortho", "ipa"):
                if step.get("done") and step.get("full_coverage") is False:
                    step_any_partial = True
        if step_any_blocked:
            blocked += 1
        if step_any_partial:
            partial_coverage += 1

    return {
        "readOnly": True,
        "count": len(results),
        "blockedSpeakers": blocked,
        "partialCoverageSpeakers": partial_coverage,
        "rows": results,
    }


def tool_pipeline_run(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._start_compute_job is None:
        raise ChatToolExecutionError("start_compute_job callback is unavailable")

    speaker = tools._normalize_speaker(args.get("speaker"))
    raw_steps = args.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ChatToolValidationError("steps must be a non-empty list")
    valid = {"normalize", "stt", "ortho", "ipa"}
    steps: List[str] = []
    for raw in raw_steps:
        step = str(raw or "").strip().lower()
        if step not in valid:
            raise ChatToolValidationError("invalid step: {0!r}".format(raw))
        if step not in steps:
            steps.append(step)

    overwrites_raw = args.get("overwrites") or {}
    if not isinstance(overwrites_raw, dict):
        raise ChatToolValidationError("overwrites must be an object")
    overwrites: Dict[str, bool] = {}
    for key, value in overwrites_raw.items():
        normalized_key = str(key or "").strip().lower()
        if normalized_key not in valid:
            raise ChatToolValidationError("invalid overwrite key: {0!r}".format(key))
        overwrites[normalized_key] = bool(value)

    language_raw = args.get("language")
    language = str(language_raw).strip() if isinstance(language_raw, str) else ""

    run_mode = str(args.get("run_mode") or "full").strip().lower().replace("_", "-")
    if run_mode not in {"full", "concept-windows", "edited-only"}:
        raise ChatToolValidationError("run_mode must be one of 'full', 'concept-windows', or 'edited-only'")
    concept_ids_raw = args.get("concept_ids")
    concept_ids: List[str] = []
    if concept_ids_raw is not None:
        if not isinstance(concept_ids_raw, list):
            raise ChatToolValidationError("concept_ids must be a list")
        for raw in concept_ids_raw:
            concept_id = str(raw or "").strip()
            if concept_id and concept_id not in concept_ids:
                concept_ids.append(concept_id)

    payload: Dict[str, Any] = {"speaker": speaker, "steps": steps, "overwrites": overwrites}
    if language:
        payload["language"] = language
    if run_mode != "full":
        payload["run_mode"] = run_mode
    if concept_ids:
        payload["concept_ids"] = concept_ids

    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "pipeline_run",
            "plan": payload,
            "message": "Dry run. Would start a full_pipeline compute job for this speaker.",
        }

    try:
        job_id = tools._start_compute_job("full_pipeline", payload)
    except Exception as exc:
        raise ChatToolExecutionError("pipeline start failed: {0}".format(exc)) from exc

    result = {
        "jobId": str(job_id),
        "status": "running",
        "speaker": speaker,
        "steps": steps,
        "overwrites": overwrites,
        "computeType": "full_pipeline",
        "message": "Pipeline job started. Poll with compute_status.",
    }
    if run_mode != "full":
        result["run_mode"] = run_mode
    if concept_ids:
        result["concept_ids"] = concept_ids
    return result


PIPELINE_ORCHESTRATION_TOOL_HANDLERS = {
    "pipeline_state_read": tool_pipeline_state_read,
    "pipeline_state_batch": tool_pipeline_state_batch,
    "pipeline_run": tool_pipeline_run,
}
