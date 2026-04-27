from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Dict

from ..chat_tools import ChatToolExecutionError, ChatToolSpec, ChatToolValidationError

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


JOB_STATUS_TOOL_NAMES = (
    "stt_status",
    "stt_word_level_status",
    "forced_align_status",
    "ipa_transcribe_acoustic_status",
    "retranscribe_with_boundaries_status",
    "compute_status",
    "audio_normalize_status",
    "jobs_list",
    "job_status",
    "job_logs",
    "jobs_list_active",
)


JOB_STATUS_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "stt_status": ChatToolSpec(
        name="stt_status",
        description=(
            "Read status/progress of an existing STT job."
        ),
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
    "stt_word_level_status": ChatToolSpec(
        name="stt_word_level_status",
        description=(
            "Read status of a Tier 1 word-level STT job. When includeSegments=true the returned "
            "segments include the nested words[] payload produced by word_timestamps=True."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                "includeSegments": {"type": "boolean"},
                "includeWords": {"type": "boolean"},
                "maxSegments": {"type": "integer", "minimum": 1, "maximum": 300},
            },
        },
    ),
    "forced_align_status": ChatToolSpec(
        name="forced_align_status",
        description=(
            "Read status/progress of an existing Tier 2 forced-alignment job."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
        },
    ),
    "ipa_transcribe_acoustic_status": ChatToolSpec(
        name="ipa_transcribe_acoustic_status",
        description=(
            "Read status/progress of an existing Tier 3 acoustic IPA job."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
        },
    ),
    "retranscribe_with_boundaries_status": ChatToolSpec(
        name="retranscribe_with_boundaries_status",
        description=(
            "Read status/progress of a boundary-constrained STT job started by retranscribe_with_boundaries_start."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
        },
    ),
    "compute_status": ChatToolSpec(
        name="compute_status",
        description=(
            "Poll any compute job (full_pipeline, ortho, ipa, contact-lexemes, …) by jobId. "
            "Read-only. Returns the job snapshot with status, progress, message, and — for "
            "completed jobs — the full ``result`` payload. For pipeline jobs the result includes "
            "per-step status and summary counts so the agent can reason about success/skip/error cells."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                "computeType": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                    "description": "Optional expected compute type (e.g. \"full_pipeline\"). If provided, the tool validates the job's type matches before returning the snapshot.",
                },
            },
        },
    ),
    "audio_normalize_status": ChatToolSpec(
        name="audio_normalize_status",
        description=(
            "Poll status of a normalize job started with audio_normalize_start. Returns status, progress, error, and result when complete."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
        },
    ),
    "jobs_list": ChatToolSpec(
        name="jobs_list",
        description=(
            "List jobs from the PARSE job registry, including active and recent completed jobs. Supports filtering by status, type, and speaker, plus a bounded result limit."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "statuses": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {"type": "string", "minLength": 1, "maxLength": 32},
                },
                "types": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {"type": "string", "minLength": 1, "maxLength": 128},
                },
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        },
    ),
    "job_status": ChatToolSpec(
        name="job_status",
        description=(
            "Read the generic status of any PARSE background job by jobId. Returns type, status, progress, message, error, result, timestamps, and logCount."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
        },
    ),
    "job_logs": ChatToolSpec(
        name="job_logs",
        description=(
            "Read structured log lines for any PARSE background job. Returns timestamped entries for progress and terminal events."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["jobId"],
            "properties": {
                "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                "offset": {"type": "integer", "minimum": 0, "maximum": 10000},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    ),
    "jobs_list_active": ChatToolSpec(
        name="jobs_list_active",
        description=(
            "List all currently-running jobs in the PARSE job registry (STT, normalize, compute, onboard, etc.). Returns type, status, progress, speaker, and message for each active job. Useful for recovering jobIds after a session restart."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    ),
}


def _generic_compute_status(
    tools: "ParseChatTools",
    args: Dict[str, Any],
    *,
    expected_type: str,
    tier_label: str,
) -> Dict[str, Any]:
    if tools._get_job_snapshot is None:
        raise ChatToolExecutionError("Job snapshot callback is unavailable")

    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        raise ChatToolValidationError("jobId is required")

    snapshot = tools._get_job_snapshot(job_id)
    if snapshot is None:
        return {
            "readOnly": True,
            "jobId": job_id,
            "status": "not_found",
            "tier": tier_label,
            "message": "Unknown jobId",
        }

    actual_type = str(snapshot.get("type") or snapshot.get("computeType") or "").strip().lower()
    if actual_type and actual_type not in {
        expected_type,
        expected_type.replace("_", "-"),
        "compute:{0}".format(expected_type),
    }:
        return {
            "readOnly": True,
            "jobId": job_id,
            "status": "invalid_job_type",
            "tier": tier_label,
            "expected": expected_type,
            "actual": actual_type,
        }

    return {
        "readOnly": True,
        "jobId": job_id,
        "tier": tier_label,
        "status": snapshot.get("status"),
        "progress": snapshot.get("progress"),
        "message": snapshot.get("message"),
        "error": snapshot.get("error"),
        "result": snapshot.get("result"),
    }


def tool_stt_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._get_job_snapshot is None:
        raise ChatToolExecutionError("Job snapshot callback is unavailable")

    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        raise ChatToolValidationError("jobId is required")

    include_segments = bool(args.get("includeSegments", False))
    max_segments = int(args.get("maxSegments", 30) or 30)

    snapshot = tools._get_job_snapshot(job_id)
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


def tool_stt_word_level_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    include_words = bool(args.get("includeWords", True))
    delegated = tool_stt_status(tools, args)
    delegated["tier"] = "tier1_word_level"
    if not include_words and isinstance(delegated.get("segments"), list):
        for seg in delegated["segments"]:
            if isinstance(seg, dict) and "words" in seg:
                seg.pop("words", None)
        delegated["wordsOmitted"] = True
    return delegated


def tool_forced_align_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    return _generic_compute_status(
        tools,
        args,
        expected_type="forced_align",
        tier_label="tier2_forced_align",
    )


def tool_ipa_transcribe_acoustic_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    return _generic_compute_status(
        tools,
        args,
        expected_type="ipa_only",
        tier_label="tier3_acoustic_ipa",
    )


def tool_retranscribe_with_boundaries_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    return _generic_compute_status(
        tools,
        args,
        expected_type="retranscribe_with_boundaries",
        tier_label="boundary_constrained_stt",
    )


def tool_compute_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._get_job_snapshot is None:
        raise ChatToolExecutionError("Job snapshot callback is unavailable")

    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        raise ChatToolValidationError("jobId is required")
    expected = str(args.get("computeType") or "").strip().lower()

    snapshot = tools._get_job_snapshot(job_id)
    if snapshot is None:
        return {
            "readOnly": True,
            "jobId": job_id,
            "status": "not_found",
            "message": "Unknown jobId",
        }

    job_type = str(snapshot.get("type") or "")
    if expected and job_type != "compute:{0}".format(expected):
        return {
            "readOnly": True,
            "jobId": job_id,
            "status": "invalid_job_type",
            "expected": "compute:{0}".format(expected),
            "actual": job_type,
        }

    return {
        "readOnly": True,
        "jobId": job_id,
        "type": job_type,
        "status": snapshot.get("status"),
        "progress": snapshot.get("progress"),
        "message": snapshot.get("message"),
        "error": snapshot.get("error"),
        "result": snapshot.get("result"),
    }


def tool_audio_normalize_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._get_job_snapshot is None:
        raise ChatToolExecutionError("Job snapshot callback is unavailable")

    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        raise ChatToolValidationError("jobId is required")

    snapshot = tools._get_job_snapshot(job_id)
    if snapshot is None:
        return {
            "readOnly": True,
            "jobId": job_id,
            "status": "not_found",
            "message": "Unknown jobId",
        }

    if snapshot.get("type") != "normalize":
        return {
            "readOnly": True,
            "jobId": job_id,
            "status": "invalid_job_type",
            "expected": "normalize",
            "actual": snapshot.get("type"),
        }

    return {
        "readOnly": True,
        "jobId": job_id,
        "type": "normalize",
        "status": snapshot.get("status"),
        "progress": snapshot.get("progress"),
        "message": snapshot.get("message"),
        "error": snapshot.get("error"),
        "result": snapshot.get("result"),
    }


def tool_jobs_list(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._list_jobs is None:
        raise ChatToolExecutionError("list_jobs callback is unavailable")
    try:
        payload = tools._list_jobs(
            {
                "statuses": args.get("statuses") or [],
                "types": args.get("types") or [],
                "speaker": args.get("speaker"),
                "limit": args.get("limit"),
            }
        )
    except Exception as exc:
        raise ChatToolExecutionError("jobs_list failed: {0}".format(exc)) from exc
    if not isinstance(payload, dict):
        raise ChatToolExecutionError("jobs_list callback must return an object")
    result = {"readOnly": True}
    result.update(payload)
    return result


def tool_job_status(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._get_job_snapshot is None:
        raise ChatToolExecutionError("Job snapshot callback is unavailable")

    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        raise ChatToolValidationError("jobId is required")

    snapshot = tools._get_job_snapshot(job_id)
    if snapshot is None:
        return {
            "readOnly": True,
            "jobId": job_id,
            "status": "not_found",
            "message": "Unknown jobId",
        }

    return {
        "readOnly": True,
        "jobId": job_id,
        "type": snapshot.get("type"),
        "status": snapshot.get("status"),
        "progress": snapshot.get("progress"),
        "message": snapshot.get("message"),
        "error": snapshot.get("error"),
        "errorCode": snapshot.get("error_code") or snapshot.get("errorCode"),
        "result": snapshot.get("result"),
        "createdAt": snapshot.get("created_at") or snapshot.get("createdAt"),
        "updatedAt": snapshot.get("updated_at") or snapshot.get("updatedAt"),
        "completedAt": snapshot.get("completed_at") or snapshot.get("completedAt"),
        "meta": copy.deepcopy(snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else {}),
        "locks": copy.deepcopy(snapshot.get("locks") if isinstance(snapshot.get("locks"), dict) else {}),
        "logCount": len(snapshot.get("logs")) if isinstance(snapshot.get("logs"), list) else int(snapshot.get("logCount") or 0),
    }


def tool_job_logs(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._get_job_logs is None:
        raise ChatToolExecutionError("get_job_logs callback is unavailable")

    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        raise ChatToolValidationError("jobId is required")

    offset = int(args.get("offset") or 0)
    limit = int(args.get("limit") or 100)
    try:
        payload = tools._get_job_logs(job_id, offset, limit)
    except Exception as exc:
        raise ChatToolExecutionError("job_logs failed: {0}".format(exc)) from exc
    if not isinstance(payload, dict):
        raise ChatToolExecutionError("get_job_logs callback must return an object")
    result = {"readOnly": True}
    result.update(payload)
    if "logs" in result and isinstance(result["logs"], list):
        result["logCount"] = len(result["logs"])
    return result


def tool_jobs_list_active(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    del args
    if tools._list_active_jobs is None:
        raise ChatToolExecutionError("list_active_jobs callback is unavailable")
    try:
        jobs = tools._list_active_jobs()
    except Exception as exc:
        raise ChatToolExecutionError("jobs_list_active failed: {0}".format(exc)) from exc
    return {"readOnly": True, "jobs": jobs, "count": len(jobs)}


JOB_STATUS_TOOL_HANDLERS = {
    "stt_status": tool_stt_status,
    "stt_word_level_status": tool_stt_word_level_status,
    "forced_align_status": tool_forced_align_status,
    "ipa_transcribe_acoustic_status": tool_ipa_transcribe_acoustic_status,
    "retranscribe_with_boundaries_status": tool_retranscribe_with_boundaries_status,
    "compute_status": tool_compute_status,
    "audio_normalize_status": tool_audio_normalize_status,
    "jobs_list": tool_jobs_list,
    "job_status": tool_job_status,
    "job_logs": tool_job_logs,
    "jobs_list_active": tool_jobs_list_active,
}
