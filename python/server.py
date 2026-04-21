"""PARSE HTTP server with static range serving and API endpoints."""

import cgi
import copy
import http.server
import io
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

from ai.chat_orchestrator import ChatOrchestrator, ChatOrchestratorError, READ_ONLY_NOTICE
from ai.chat_tools import ParseChatTools
from ai.provider import get_chat_config, get_ipa_provider, get_llm_provider, get_stt_provider, load_ai_config, resolve_context_window
from audio_pipeline_paths import build_normalized_output_path

try:
    from compare import cognate_compute as cognate_compute_module
except Exception:
    cognate_compute_module = None


HOST = "0.0.0.0"
PORT = 8766
JOB_RETENTION_SECONDS = 60 * 60

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Range, Content-Type",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS, POST, PUT",
    "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
    "Accept-Ranges": "bytes",
}

ANNOTATION_FILENAME_SUFFIX = ".parse.json"
ANNOTATION_LEGACY_FILENAME_SUFFIX = ".json"
ANNOTATION_TIER_ORDER = {
    "ipa": 1,
    "ortho": 2,
    "concept": 3,
    "speaker": 4,
}
ANNOTATION_MATCH_EPSILON = 0.0005

ONBOARD_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB hard cap
ONBOARD_AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}
NORMALIZE_LUFS_TARGET = -16.0
NORMALIZE_SAMPLE_RATE = "44100"
NORMALIZE_CHANNELS = "1"
NORMALIZE_SAMPLE_FORMAT = "s16"
NORMALIZE_AUDIO_CODEC = "pcm_s16le"

CHAT_SESSION_RETENTION_SECONDS = 8 * 60 * 60
CHAT_DEFAULT_MAX_MESSAGES_PER_SESSION = 200
CHAT_DEFAULT_MAX_MESSAGE_CHARS = 8000
CHAT_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

_chat_sessions: Dict[str, Dict[str, Any]] = {}
_chat_sessions_lock = threading.Lock()

_chat_runtime_lock = threading.Lock()
_chat_tools_runtime: Optional[ParseChatTools] = None
_chat_orchestrator_runtime: Optional[ChatOrchestrator] = None


def _reset_chat_runtime_after_auth_key_save() -> None:
    """Clear cached chat runtimes so a newly saved API key applies immediately."""
    global _chat_tools_runtime
    global _chat_orchestrator_runtime

    with _chat_runtime_lock:
        _chat_tools_runtime = None
        _chat_orchestrator_runtime = None


class ApiError(Exception):
    """API error with explicit HTTP status."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _project_root() -> pathlib.Path:
    return pathlib.Path.cwd().resolve()


def _config_path() -> pathlib.Path:
    return _project_root() / "config" / "ai_config.json"


def _enrichments_path() -> pathlib.Path:
    return _project_root() / "parse-enrichments.json"


def _sil_config_path() -> pathlib.Path:
    return _project_root() / "config" / "sil_contact_languages.json"


def _default_enrichments_payload() -> Dict[str, Any]:
    return {
        "computed_at": None,
        "config": {
            "contact_languages": [],
            "speakers_included": [],
            "concepts_included": [],
            "lexstat_threshold": 0.6,
        },
        "cognate_sets": {},
        "similarity": {},
        "borrowing_flags": {},
        "manual_overrides": {},
    }


def _clamp_progress(value: Any) -> float:
    try:
        progress = float(value)
    except (TypeError, ValueError):
        return 0.0

    if progress < 0.0:
        return 0.0
    if progress > 100.0:
        return 100.0
    return progress


def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)

    return merged


def _normalize_concept_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if text.startswith("#"):
        text = text[1:].strip()

    if ":" in text:
        text = text.split(":", 1)[0].strip()

    return text


def _concept_sort_key(concept_id: str) -> Tuple[int, float, str]:
    normalized = _normalize_concept_id(concept_id)
    try:
        return (0, float(normalized), normalized)
    except ValueError:
        return (1, float("inf"), normalized)


def _concept_out_value(concept_id: str) -> Any:
    normalized = _normalize_concept_id(concept_id)
    try:
        numeric = float(normalized)
    except ValueError:
        return normalized

    if numeric.is_integer():
        return int(numeric)
    return normalized


def _coerce_string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        tokens = [token.strip() for token in value.split(",")]
        return [token for token in tokens if token]

    if isinstance(value, list):
        output = []
        for item in value:
            text = str(item or "").strip()
            if text:
                output.append(text)
        return output

    return []


def _coerce_concept_id_list(value: Any) -> List[str]:
    concept_ids: List[str] = []
    for raw in _coerce_string_list(value):
        normalized = _normalize_concept_id(raw)
        if normalized and normalized not in concept_ids:
            concept_ids.append(normalized)
    return concept_ids


def _resolve_project_path(raw_path: str) -> pathlib.Path:
    path_value = str(raw_path or "").strip()
    if not path_value:
        raise ValueError("Path value is required")

    path_obj = pathlib.Path(path_value).expanduser()
    if not path_obj.is_absolute():
        path_obj = _project_root() / path_obj

    resolved = path_obj.resolve()

    # Guard against path traversal — resolved path must be under project root.
    root = _project_root()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            "Path escapes project root: {0}".format(resolved)
        )

    return resolved


def _read_json_file(path: pathlib.Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(default)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(default)

    if not isinstance(payload, dict):
        return copy.deepcopy(default)

    return payload


def _write_json_file(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _dist_dir(project_root: Optional[pathlib.Path] = None) -> pathlib.Path:
    root = (project_root or _project_root()).resolve()
    return root / "dist"


def _dist_index_path(project_root: Optional[pathlib.Path] = None) -> pathlib.Path:
    return _dist_dir(project_root) / "index.html"


def _has_built_frontend(project_root: Optional[pathlib.Path] = None) -> bool:
    return _dist_index_path(project_root).is_file()


def _static_request_parts(raw_path: str) -> List[str]:
    request_path = urlparse(raw_path).path or "/"
    pure_path = pathlib.PurePosixPath(unquote(request_path))
    return [part for part in pure_path.parts if part not in {"/", "", ".", ".."}]


def _resolve_static_request_path(
    raw_path: str,
    project_root: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    root = (project_root or _project_root()).resolve()
    parts = _static_request_parts(raw_path)
    root_candidate = root.joinpath(*parts) if parts else root

    if not _has_built_frontend(root):
        return root_candidate

    dist_candidate = _dist_dir(root).joinpath(*parts) if parts else _dist_index_path(root)
    if parts and dist_candidate.exists():
        return dist_candidate
    if parts and root_candidate.exists():
        return root_candidate

    request_suffix = pathlib.PurePosixPath("/".join(parts)).suffix if parts else ""
    if not parts or request_suffix == "":
        return _dist_index_path(root)

    return root_candidate


def _project_json_path() -> pathlib.Path:
    return _project_root() / "project.json"


def _source_index_path() -> pathlib.Path:
    return _project_root() / "source_index.json"


def _annotations_dir_path() -> pathlib.Path:
    return _resolve_project_path("annotations")


def _read_json_any_file(path: pathlib.Path) -> Any:
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _coerce_finite_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None
    if number in {float("inf"), float("-inf")}:
        return None

    return number


def _coerce_bool_like(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled"}:
            return False

    return bool(default)


def _coerce_int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)

    if number < minimum:
        number = minimum
    if number > maximum:
        number = maximum

    return number


def _coerce_float_range(value: Any, default: float, minimum: float, maximum: float) -> float:
    number = _coerce_finite_float(value)
    if number is None:
        number = float(default)

    if number < minimum:
        number = minimum
    if number > maximum:
        number = maximum

    return float(number)


def _has_nonempty_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0

    return True


def _chat_runtime_policy(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source_config = config if isinstance(config, dict) else load_ai_config(_config_path())
    chat_config = get_chat_config(source_config)

    return {
        "enabled": _coerce_bool_like(chat_config.get("enabled"), True),
        "mode": "read-only",
        "readOnly": True,
        "attachmentsSupported": False,
        "readOnlyNotice": READ_ONLY_NOTICE,
        "provider": str(chat_config.get("provider") or "openai").strip() or "openai",
        "model": str(chat_config.get("model") or "gpt-5.4").strip() or "gpt-5.4",
        "apiKeyEnv": str(chat_config.get("api_key_env") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY",
        "reasoningEffort": str(chat_config.get("reasoning_effort") or "").strip(),
        "temperature": _coerce_float_range(chat_config.get("temperature"), 0.1, 0.0, 2.0),
        "maxToolRounds": _coerce_int_range(chat_config.get("max_tool_rounds"), 4, 1, 8),
        "maxHistoryMessages": _coerce_int_range(chat_config.get("max_history_messages"), 24, 1, 64),
        "maxOutputTokens": _coerce_int_range(chat_config.get("max_output_tokens"), 1400, 128, 8192),
        "maxToolResultChars": _coerce_int_range(chat_config.get("max_tool_result_chars"), 24000, 2000, 200000),
        "maxUserMessageChars": _coerce_int_range(
            chat_config.get("max_user_message_chars"),
            CHAT_DEFAULT_MAX_MESSAGE_CHARS,
            500,
            50000,
        ),
        "maxSessionMessages": _coerce_int_range(
            chat_config.get("max_session_messages"),
            CHAT_DEFAULT_MAX_MESSAGES_PER_SESSION,
            10,
            1000,
        ),
    }


def _chat_public_policy_payload(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    policy = _chat_runtime_policy(config)
    return {
        "mode": policy["mode"],
        "readOnly": policy["readOnly"],
        "attachmentsSupported": policy["attachmentsSupported"],
        "readOnlyNotice": policy["readOnlyNotice"],
        "provider": policy["provider"],
        "model": policy["model"],
        "reasoningEffort": policy["reasoningEffort"],
        "limits": {
            "maxUserMessageChars": policy["maxUserMessageChars"],
            "maxSessionMessages": policy["maxSessionMessages"],
            "maxHistoryMessages": policy["maxHistoryMessages"],
            "maxToolRounds": policy["maxToolRounds"],
            "maxToolResultChars": policy["maxToolResultChars"],
            "maxOutputTokens": policy["maxOutputTokens"],
        },
    }


def _find_nonempty_key_path(value: Any, forbidden_keys: Sequence[str], path: str = "$") -> Optional[str]:
    normalized_keys = {str(item).strip().lower() for item in forbidden_keys if str(item).strip()}

    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            next_path = "{0}.{1}".format(path, key_text)
            if key_text.strip().lower() in normalized_keys and _has_nonempty_value(item):
                return next_path

            nested = _find_nonempty_key_path(item, tuple(normalized_keys), path=next_path)
            if nested:
                return nested
        return None

    if isinstance(value, list):
        for index, item in enumerate(value):
            nested = _find_nonempty_key_path(item, tuple(normalized_keys), path="{0}[{1}]".format(path, index))
            if nested:
                return nested

    return None


def _chat_validate_run_request(body: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    policy = _chat_runtime_policy()

    if not policy.get("enabled", True):
        raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE, "Chat assistant is disabled in config")

    if "readOnly" in body and not _coerce_bool_like(body.get("readOnly"), True):
        raise ApiError(HTTPStatus.BAD_REQUEST, "Chat assistant only supports readOnly=true in this MVP")

    requested_mode = str(body.get("mode") or "").strip().lower()
    if requested_mode and requested_mode != "read-only":
        raise ApiError(HTTPStatus.BAD_REQUEST, "Chat assistant only supports mode='read-only'")

    if "attachmentsSupported" in body and _coerce_bool_like(body.get("attachmentsSupported"), False):
        raise ApiError(HTTPStatus.BAD_REQUEST, "attachmentsSupported=true is not supported in chat MVP")

    forbidden_path = _find_nonempty_key_path(
        body,
        forbidden_keys=(
            "attachments",
            "attachmentIds",
            "files",
            "fileIds",
            "file_ids",
            "contextFiles",
            "context_files",
            "context_paths",
        ),
    )
    if forbidden_path:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "{0} is not supported in chat MVP; file/context attachments are disabled".format(forbidden_path),
        )

    message_text = str(body.get("message") or body.get("text") or "").strip()
    if not message_text:
        raise ApiError(HTTPStatus.BAD_REQUEST, "message is required")

    max_chars = int(policy.get("maxUserMessageChars") or CHAT_DEFAULT_MAX_MESSAGE_CHARS)
    if len(message_text) > max_chars:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "message exceeds maxUserMessageChars={0}".format(max_chars),
        )

    return policy, message_text


def _annotation_project_payload() -> Dict[str, Any]:
    return _read_json_file(_project_json_path(), {})


def _annotation_source_index_payload() -> Dict[str, Any]:
    return _read_json_file(_source_index_path(), {})


def _annotation_project_id() -> str:
    project_id = str(_annotation_project_payload().get("project_id") or "").strip()
    if project_id:
        return project_id
    return "parse-project"


def _annotation_language_code(fallback_record: Optional[Dict[str, Any]] = None) -> str:
    project = _annotation_project_payload()
    language_block = project.get("language") if isinstance(project, dict) else {}

    if isinstance(language_block, dict):
        language_code = str(language_block.get("code") or "").strip()
        if language_code:
            return language_code

    metadata_block = {}
    if isinstance(fallback_record, dict):
        metadata_raw = fallback_record.get("metadata")
        if isinstance(metadata_raw, dict):
            metadata_block = metadata_raw

    metadata_language = str(metadata_block.get("language_code") or "").strip()
    if metadata_language:
        return metadata_language

    return "und"


def _annotation_source_entries_for_speaker(speaker: str) -> List[Dict[str, Any]]:
    source_index = _annotation_source_index_payload()
    speakers_block = source_index.get("speakers") if isinstance(source_index, dict) else {}
    if not isinstance(speakers_block, dict):
        return []

    speaker_entry = speakers_block.get(speaker)
    if not isinstance(speaker_entry, dict):
        return []

    for key in ("source_wavs", "source_files"):
        entries = speaker_entry.get(key)
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]

    return []


def _annotation_primary_source_wav(speaker: str) -> str:
    source_entries = _annotation_source_entries_for_speaker(speaker)
    if not source_entries:
        return ""

    selected = None
    for entry in source_entries:
        if entry.get("is_primary"):
            selected = entry
            break

    if selected is None:
        selected = source_entries[0]

    filename = str(selected.get("filename") or "").strip()
    if filename:
        return filename

    return str(selected.get("file") or "").strip()


def _annotation_source_duration(speaker: str, source_wav: str) -> Optional[float]:
    source_entries = _annotation_source_entries_for_speaker(speaker)
    if not source_entries:
        return None

    requested = str(source_wav or "").strip()
    selected = None

    if requested:
        for entry in source_entries:
            filename = str(entry.get("filename") or "").strip()
            if filename and filename == requested:
                selected = entry
                break

    if selected is None:
        for entry in source_entries:
            if entry.get("is_primary"):
                selected = entry
                break

    if selected is None:
        selected = source_entries[0]

    duration = _coerce_finite_float(selected.get("duration_sec"))
    if duration is None or duration < 0:
        return None

    return duration


def _annotation_empty_tier(display_order: int) -> Dict[str, Any]:
    return {
        "type": "interval",
        "display_order": int(display_order),
        "intervals": [],
    }


def _annotation_sort_intervals(intervals: List[Dict[str, Any]]) -> None:
    intervals.sort(key=lambda interval: (float(interval.get("start", 0.0)), float(interval.get("end", 0.0))))


def _annotation_normalize_interval(raw_interval: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_interval, dict):
        return None

    start = _coerce_finite_float(
        raw_interval.get("start", raw_interval.get("xmin"))
    )
    end = _coerce_finite_float(
        raw_interval.get("end", raw_interval.get("xmax"))
    )

    if start is None or end is None:
        return None

    if end < start:
        return None

    return {
        "start": float(start),
        "end": float(end),
        "text": "" if raw_interval.get("text") is None else str(raw_interval.get("text")),
    }


def _annotation_tier_key(raw_name: Any) -> str:
    tier_name = str(raw_name or "").strip()
    if not tier_name:
        return ""

    lowered = tier_name.lower()
    if lowered in ANNOTATION_TIER_ORDER:
        return lowered

    return tier_name


def _annotation_normalize_tier(raw_tier: Any, default_display_order: int) -> Dict[str, Any]:
    tier_payload = raw_tier if isinstance(raw_tier, dict) else {}

    display_order_raw = _coerce_finite_float(tier_payload.get("display_order"))
    if display_order_raw is None or display_order_raw <= 0:
        display_order = int(default_display_order)
    else:
        display_order = int(display_order_raw)

    intervals_raw = tier_payload.get("intervals")
    intervals_out: List[Dict[str, Any]] = []

    if isinstance(intervals_raw, list):
        for raw_interval in intervals_raw:
            interval = _annotation_normalize_interval(raw_interval)
            if interval is not None:
                intervals_out.append(interval)

    _annotation_sort_intervals(intervals_out)

    return {
        "type": "interval",
        "display_order": display_order,
        "intervals": intervals_out,
    }


def _annotation_max_end(record: Dict[str, Any]) -> float:
    tiers = record.get("tiers") if isinstance(record, dict) else {}
    if not isinstance(tiers, dict):
        return 0.0

    max_end = 0.0
    for tier in tiers.values():
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals")
        if not isinstance(intervals, list):
            continue

        for raw_interval in intervals:
            interval = _annotation_normalize_interval(raw_interval)
            if interval is None:
                continue
            if interval["end"] > max_end:
                max_end = interval["end"]

    return max_end


def _annotation_sort_all_intervals(record: Dict[str, Any]) -> None:
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return

    for tier in tiers.values():
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals")
        if isinstance(intervals, list):
            _annotation_sort_intervals(intervals)


def _annotation_collect_speaker_intervals(record: Dict[str, Any]) -> List[Dict[str, float]]:
    tiers = record.get("tiers") if isinstance(record, dict) else {}
    if not isinstance(tiers, dict):
        return []

    for tier_key in ("concept", "ipa", "ortho"):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue

        intervals = tier.get("intervals")
        if not isinstance(intervals, list):
            continue

        dedupe: Dict[str, bool] = {}
        aligned: List[Dict[str, float]] = []

        for raw_interval in intervals:
            interval = _annotation_normalize_interval(raw_interval)
            if interval is None:
                continue

            if not str(interval.get("text") or "").strip():
                continue

            dedupe_key = "{0:.6f}|{1:.6f}".format(interval["start"], interval["end"])
            if dedupe_key in dedupe:
                continue

            dedupe[dedupe_key] = True
            aligned.append({"start": interval["start"], "end": interval["end"]})

        if aligned:
            return aligned

    speaker_tier = tiers.get("speaker")
    if not isinstance(speaker_tier, dict):
        return []

    fallback_intervals = speaker_tier.get("intervals")
    if not isinstance(fallback_intervals, list):
        return []

    fallback: List[Dict[str, float]] = []
    for raw_interval in fallback_intervals:
        interval = _annotation_normalize_interval(raw_interval)
        if interval is None:
            continue

        fallback.append({"start": interval["start"], "end": interval["end"]})

    return fallback


def _annotation_sync_speaker_tier(record: Dict[str, Any]) -> None:
    if not isinstance(record, dict):
        return

    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        tiers = {}
        record["tiers"] = tiers

    speaker_tier = tiers.get("speaker")
    if not isinstance(speaker_tier, dict):
        speaker_tier = _annotation_empty_tier(ANNOTATION_TIER_ORDER["speaker"])
        tiers["speaker"] = speaker_tier

    speaker_tier["type"] = "interval"
    speaker_tier["display_order"] = ANNOTATION_TIER_ORDER["speaker"]

    duration = _coerce_finite_float(record.get("source_audio_duration_sec"))
    if duration is None or duration < 0:
        duration = 0.0

    record["source_audio_duration_sec"] = float(duration)

    speaker_text = str(record.get("speaker") or "").strip()
    aligned_intervals = _annotation_collect_speaker_intervals(record)

    speaker_tier["intervals"] = [
        {
            "start": interval["start"],
            "end": interval["end"],
            "text": speaker_text,
        }
        for interval in aligned_intervals
    ]


def _annotation_touch_metadata(record: Dict[str, Any], preserve_created: bool) -> None:
    metadata = record.get("metadata") if isinstance(record, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
        record["metadata"] = metadata

    if (not preserve_created) or not str(metadata.get("created") or "").strip():
        metadata["created"] = _utc_now_iso()

    metadata["modified"] = _utc_now_iso()

    language_code = str(metadata.get("language_code") or "").strip()
    if not language_code:
        metadata["language_code"] = _annotation_language_code(record)


def _annotation_empty_record(
    speaker: str,
    source_audio: Optional[str],
    duration_sec: Optional[float],
    existing_record: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    now_iso = _utc_now_iso()
    speaker_text = str(speaker or "").strip()

    duration = _coerce_finite_float(duration_sec)
    if duration is None or duration < 0:
        duration = 0.0

    source_audio_text = str(source_audio or "").strip()
    if not source_audio_text:
        source_audio_text = _annotation_primary_source_wav(speaker_text)

    return {
        "version": 1,
        "project_id": _annotation_project_id(),
        "speaker": speaker_text,
        "source_audio": source_audio_text,
        "source_audio_duration_sec": float(duration),
        "tiers": {
            "ipa": _annotation_empty_tier(ANNOTATION_TIER_ORDER["ipa"]),
            "ortho": _annotation_empty_tier(ANNOTATION_TIER_ORDER["ortho"]),
            "concept": _annotation_empty_tier(ANNOTATION_TIER_ORDER["concept"]),
            "speaker": _annotation_empty_tier(ANNOTATION_TIER_ORDER["speaker"]),
        },
        "metadata": {
            "language_code": _annotation_language_code(existing_record),
            "created": now_iso,
            "modified": now_iso,
        },
    }


def _annotation_upsert_interval(intervals: List[Dict[str, Any]], start: float, end: float, text: str) -> None:
    for interval in intervals:
        if abs(float(interval.get("start", 0.0)) - start) <= ANNOTATION_MATCH_EPSILON and abs(
            float(interval.get("end", 0.0)) - end
        ) <= ANNOTATION_MATCH_EPSILON:
            interval["text"] = text
            return

    intervals.append({"start": start, "end": end, "text": text})
    _annotation_sort_intervals(intervals)


def _normalize_flat_annotation_entry(raw_entry: Any, defaults: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_entry, dict):
        return None

    start = _coerce_finite_float(
        raw_entry.get(
            "startSec",
            raw_entry.get("start_sec", raw_entry.get("start", raw_entry.get("xmin"))),
        )
    )
    end = _coerce_finite_float(
        raw_entry.get(
            "endSec",
            raw_entry.get("end_sec", raw_entry.get("end", raw_entry.get("xmax"))),
        )
    )

    if start is None or end is None or end < start:
        return None

    concept_text = ""
    for key in ("concept", "concept_text", "conceptLabel", "concept_id", "conceptId"):
        value = raw_entry.get(key)
        if value is not None:
            concept_text = str(value)
            break

    concept_id_raw = raw_entry.get("conceptId")
    if concept_id_raw is None:
        concept_id_raw = raw_entry.get("concept_id")

    concept_id = str(concept_id_raw) if concept_id_raw is not None else _normalize_concept_id(concept_text)

    source_wav = raw_entry.get("sourceWav")
    if source_wav is None:
        source_wav = raw_entry.get("source_wav")

    return {
        "speaker": str(raw_entry.get("speaker") or defaults.get("speaker") or "").strip(),
        "conceptId": str(concept_id or "").strip(),
        "concept": concept_text,
        "startSec": float(start),
        "endSec": float(end),
        "ipa": "" if raw_entry.get("ipa") is None else str(raw_entry.get("ipa")),
        "ortho": "" if raw_entry.get("ortho") is None else str(raw_entry.get("ortho")),
        "sourceWav": str(source_wav or defaults.get("sourceWav") or "").strip(),
    }


def _annotation_record_from_flat_entries(
    raw_entries: Any,
    speaker_hint: str,
    source_wav_hint: str,
) -> Dict[str, Any]:
    speaker = str(speaker_hint or "").strip()
    source_wav = str(source_wav_hint or "").strip() or _annotation_primary_source_wav(speaker)
    record = _annotation_empty_record(speaker, source_wav, 0.0, None)

    entries = raw_entries if isinstance(raw_entries, list) else []
    for raw_entry in entries:
        normalized = _normalize_flat_annotation_entry(
            raw_entry,
            {
                "speaker": speaker,
                "sourceWav": source_wav,
            },
        )
        if normalized is None:
            continue

        if normalized["sourceWav"] and not str(record.get("source_audio") or "").strip():
            record["source_audio"] = normalized["sourceWav"]

        if normalized["endSec"] > float(record.get("source_audio_duration_sec") or 0.0):
            record["source_audio_duration_sec"] = float(normalized["endSec"])

        concept_text = str(normalized.get("concept") or "").strip() or str(normalized.get("conceptId") or "").strip()

        _annotation_upsert_interval(
            record["tiers"]["ipa"]["intervals"],
            normalized["startSec"],
            normalized["endSec"],
            str(normalized.get("ipa") or ""),
        )
        _annotation_upsert_interval(
            record["tiers"]["ortho"]["intervals"],
            normalized["startSec"],
            normalized["endSec"],
            str(normalized.get("ortho") or ""),
        )
        _annotation_upsert_interval(
            record["tiers"]["concept"]["intervals"],
            normalized["startSec"],
            normalized["endSec"],
            concept_text,
        )

    _annotation_sync_speaker_tier(record)
    _annotation_touch_metadata(record, preserve_created=True)
    return record


def _normalize_annotation_record(raw_record: Any, speaker_hint: str) -> Dict[str, Any]:
    speaker_from_hint = str(speaker_hint or "").strip()

    if isinstance(raw_record, list):
        return _annotation_record_from_flat_entries(raw_record, speaker_from_hint, "")

    if not isinstance(raw_record, dict):
        source_audio = _annotation_primary_source_wav(speaker_from_hint)
        source_duration = _annotation_source_duration(speaker_from_hint, source_audio)
        return _annotation_empty_record(speaker_from_hint, source_audio, source_duration or 0.0, None)

    annotations_block = raw_record.get("annotations")
    if isinstance(annotations_block, list):
        speaker_from_record = str(raw_record.get("speaker") or speaker_from_hint).strip()
        source_from_record = str(
            raw_record.get("source_audio")
            or raw_record.get("sourceWav")
            or raw_record.get("source_wav")
            or ""
        ).strip()
        return _annotation_record_from_flat_entries(annotations_block, speaker_from_record, source_from_record)

    speaker = str(raw_record.get("speaker") or speaker_from_hint).strip()
    source_audio = str(
        raw_record.get("source_audio")
        or raw_record.get("sourceWav")
        or raw_record.get("source_wav")
        or ""
    ).strip()

    source_duration = _coerce_finite_float(raw_record.get("source_audio_duration_sec"))
    if source_duration is None or source_duration < 0:
        source_duration = _annotation_source_duration(speaker, source_audio) or 0.0

    normalized = _annotation_empty_record(speaker, source_audio, source_duration, raw_record)
    normalized["version"] = 1

    project_id = str(raw_record.get("project_id") or "").strip()
    normalized["project_id"] = project_id or _annotation_project_id()

    tiers_in = raw_record.get("tiers")
    if not isinstance(tiers_in, dict):
        tiers_in = {}

    next_custom_display_order = 5

    for original_key, raw_tier in tiers_in.items():
        tier_key = _annotation_tier_key(original_key)
        if not tier_key:
            continue

        default_order = ANNOTATION_TIER_ORDER.get(tier_key, next_custom_display_order)
        tier = _annotation_normalize_tier(raw_tier, default_order)
        normalized["tiers"][tier_key] = tier

        if tier_key not in ANNOTATION_TIER_ORDER:
            next_custom_display_order = max(next_custom_display_order, int(tier.get("display_order", default_order)) + 1)

    for tier_key, display_order in ANNOTATION_TIER_ORDER.items():
        if tier_key not in normalized["tiers"]:
            normalized["tiers"][tier_key] = _annotation_empty_tier(display_order)

    metadata_in = raw_record.get("metadata")
    if not isinstance(metadata_in, dict):
        metadata_in = {}

    now_iso = _utc_now_iso()
    language_code = str(metadata_in.get("language_code") or _annotation_language_code(raw_record) or "und").strip()
    if not language_code:
        language_code = "und"

    normalized["metadata"] = {
        "language_code": language_code,
        "created": str(metadata_in.get("created") or now_iso),
        "modified": str(metadata_in.get("modified") or now_iso),
    }

    max_end = _annotation_max_end(normalized)
    if max_end > float(normalized.get("source_audio_duration_sec") or 0.0):
        normalized["source_audio_duration_sec"] = float(max_end)

    source_index_duration = _annotation_source_duration(speaker, str(normalized.get("source_audio") or ""))
    if source_index_duration is not None and source_index_duration > float(normalized.get("source_audio_duration_sec") or 0.0):
        normalized["source_audio_duration_sec"] = float(source_index_duration)

    if not str(normalized.get("source_audio") or "").strip():
        normalized["source_audio"] = _annotation_primary_source_wav(speaker)

    _annotation_sync_speaker_tier(normalized)
    _annotation_sort_all_intervals(normalized)

    return normalized


def _normalize_speaker_id(raw_speaker: Any) -> str:
    speaker = str(raw_speaker or "").strip()
    if not speaker:
        raise ValueError("speaker is required")

    if speaker in {".", ".."}:
        raise ValueError("Invalid speaker id")

    if "\x00" in speaker:
        raise ValueError("speaker contains an invalid null byte")

    if "/" in speaker or "\\" in speaker:
        raise ValueError("speaker must not contain path separators")

    if len(speaker) > 200:
        raise ValueError("speaker is too long")

    return speaker


def _annotation_record_relative_path(speaker: str) -> pathlib.Path:
    return pathlib.Path("annotations") / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)


def _annotation_legacy_record_relative_path(speaker: str) -> pathlib.Path:
    return pathlib.Path("annotations") / "{0}{1}".format(speaker, ANNOTATION_LEGACY_FILENAME_SUFFIX)


def _annotation_resolve_relative_path(relative_path: pathlib.Path) -> pathlib.Path:
    annotations_dir = _annotations_dir_path()
    candidate = _resolve_project_path(str(relative_path))

    try:
        candidate.relative_to(annotations_dir)
    except ValueError as exc:
        raise ValueError("Annotation path escapes annotations directory") from exc

    return candidate


def _annotation_record_path_for_speaker(speaker: str) -> pathlib.Path:
    return _annotation_resolve_relative_path(_annotation_record_relative_path(speaker))


def _annotation_legacy_record_path_for_speaker(speaker: str) -> pathlib.Path:
    return _annotation_resolve_relative_path(_annotation_legacy_record_relative_path(speaker))


def _annotation_read_path_for_speaker(speaker: str) -> pathlib.Path:
    canonical_path = _annotation_record_path_for_speaker(speaker)
    if canonical_path.is_file():
        return canonical_path

    legacy_path = _annotation_legacy_record_path_for_speaker(speaker)
    if legacy_path.is_file():
        return legacy_path

    return canonical_path


def _annotation_payload_from_request_body(raw_payload: Any) -> Any:
    if isinstance(raw_payload, list):
        return raw_payload

    if isinstance(raw_payload, dict):
        annotation_candidate = raw_payload.get("annotation")
        if isinstance(annotation_candidate, (dict, list)):
            return annotation_candidate

        record_candidate = raw_payload.get("record")
        if isinstance(record_candidate, (dict, list)):
            return record_candidate

        return raw_payload

    raise ValueError("Annotation payload must be a JSON object or array")


def _normalize_chat_session_id(raw_session_id: Any) -> str:
    session_id = str(raw_session_id or "").strip()
    if not session_id:
        raise ValueError("sessionId is required")

    if not CHAT_SESSION_ID_PATTERN.match(session_id):
        raise ValueError("sessionId must match [A-Za-z0-9_-]{1,128}")

    return session_id


def _cleanup_old_chat_sessions() -> None:
    now_ts = time.time()
    stale_session_ids: List[str] = []

    with _chat_sessions_lock:
        for session_id, session in _chat_sessions.items():
            updated_ts = session.get("updated_ts")
            if not isinstance(updated_ts, (int, float)):
                continue

            if now_ts - float(updated_ts) > CHAT_SESSION_RETENTION_SECONDS:
                stale_session_ids.append(session_id)

        for session_id in stale_session_ids:
            _chat_sessions.pop(session_id, None)


def _chat_session_public_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    policy_payload = _chat_public_policy_payload()

    messages_raw = session.get("messages")
    messages_out: List[Dict[str, Any]] = []
    tokens_used: Optional[int] = None

    if isinstance(messages_raw, list):
        for message in messages_raw:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            if role not in {"user", "assistant", "system"}:
                continue

            content = str(message.get("content") or "")
            created_at = message.get("created_at")
            messages_out.append(
                {
                    "role": role,
                    "content": content,
                    "created_at": created_at,
                }
            )

            # Last assistant turn's total_tokens approximates the current
            # conversation size (prompt_tokens of the next turn ≈ this).
            if role == "assistant":
                meta = message.get("meta")
                if isinstance(meta, dict):
                    candidate = meta.get("tokensUsed")
                    if isinstance(candidate, int) and candidate >= 0:
                        tokens_used = candidate

    model_name = str(policy_payload.get("model") or "")
    tokens_limit = resolve_context_window(model_name)

    return {
        "sessionId": str(session.get("sessionId") or ""),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "ephemeral": True,
        "sharedAcrossPages": True,
        **policy_payload,
        "messages": messages_out,
        "tokensUsed": tokens_used,
        "tokensLimit": tokens_limit,
    }


def _chat_create_or_get_session(session_id: Optional[str] = None) -> Dict[str, Any]:
    _cleanup_old_chat_sessions()

    resolved_session_id = str(session_id or "").strip()
    if resolved_session_id:
        resolved_session_id = _normalize_chat_session_id(resolved_session_id)
    else:
        resolved_session_id = "chat_{0}".format(uuid.uuid4().hex)

    now_iso = _utc_now_iso()
    now_ts = time.time()

    with _chat_sessions_lock:
        existing = _chat_sessions.get(resolved_session_id)
        if existing is not None:
            existing["updated_at"] = now_iso
            existing["updated_ts"] = now_ts
            return copy.deepcopy(existing)

        created = {
            "sessionId": resolved_session_id,
            "created_at": now_iso,
            "updated_at": now_iso,
            "created_ts": now_ts,
            "updated_ts": now_ts,
            "messages": [],
        }
        _chat_sessions[resolved_session_id] = created
        return copy.deepcopy(created)


def _chat_get_session_snapshot(session_id: str) -> Optional[Dict[str, Any]]:
    with _chat_sessions_lock:
        session = _chat_sessions.get(session_id)
        if session is None:
            return None
        return copy.deepcopy(session)


def _chat_append_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in {"user", "assistant", "system"}:
        raise ValueError("Unsupported chat role: {0}".format(role))

    policy = _chat_runtime_policy()
    max_message_chars = int(policy.get("maxUserMessageChars") or CHAT_DEFAULT_MAX_MESSAGE_CHARS)
    max_session_messages = int(policy.get("maxSessionMessages") or CHAT_DEFAULT_MAX_MESSAGES_PER_SESSION)

    text = str(content or "")
    if len(text) > max_message_chars:
        text = text[:max_message_chars]

    with _chat_sessions_lock:
        session = _chat_sessions.get(session_id)
        if session is None:
            raise ValueError("Unknown chat session: {0}".format(session_id))

        messages = session.get("messages")
        if not isinstance(messages, list):
            messages = []
            session["messages"] = messages

        message_payload: Dict[str, Any] = {
            "id": "msg_{0}".format(uuid.uuid4().hex),
            "role": normalized_role,
            "content": text,
            "created_at": _utc_now_iso(),
        }

        if isinstance(metadata, dict) and metadata:
            message_payload["meta"] = copy.deepcopy(metadata)

        messages.append(message_payload)

        if len(messages) > max_session_messages:
            session["messages"] = messages[-max_session_messages:]

        session["updated_at"] = _utc_now_iso()
        session["updated_ts"] = time.time()

        return copy.deepcopy(message_payload)


def _chat_start_stt_job(speaker: str, source_wav: str, language: Optional[str]) -> str:
    job_id = _create_job(
        "stt",
        {
            "speaker": speaker,
            "sourceWav": source_wav,
            "language": language,
            "origin": "chat_tool",
        },
    )

    thread = threading.Thread(
        target=_run_stt_job,
        args=(job_id, speaker, source_wav, language),
        daemon=True,
    )
    thread.start()

    return job_id


def _chat_get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    return _get_job_snapshot(job_id)


def _chat_docs_root() -> Optional[pathlib.Path]:
    raw = str(os.environ.get("PARSE_CHAT_DOCS_ROOT") or "").strip()
    if not raw:
        return None

    root = pathlib.Path(raw).expanduser()
    if not root.is_absolute():
        root = _project_root() / root

    try:
        return root.resolve()
    except Exception:
        return root


def _chat_external_read_roots() -> List[pathlib.Path]:
    """Parse PARSE_EXTERNAL_READ_ROOTS as an OS-path-separated list.

    Use ``:`` on POSIX and ``;`` on Windows. Non-existent or unreadable entries
    are dropped silently so an over-eager config doesn't break chat startup.
    """
    raw = str(os.environ.get("PARSE_EXTERNAL_READ_ROOTS") or "").strip()
    if not raw:
        return []

    sep = ";" if os.name == "nt" or ";" in raw else os.pathsep
    roots: List[pathlib.Path] = []
    for piece in raw.split(sep):
        piece = piece.strip()
        if not piece:
            continue
        candidate = pathlib.Path(piece).expanduser()
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _chat_memory_path() -> pathlib.Path:
    raw = str(os.environ.get("PARSE_CHAT_MEMORY_PATH") or "").strip()
    if raw:
        candidate = pathlib.Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = _project_root() / candidate
        try:
            return candidate.resolve()
        except Exception:
            return candidate
    return (_project_root() / "parse-memory.md").resolve()


def _chat_onboard_speaker(
    speaker: str,
    source_wav_path: pathlib.Path,
    source_csv_path: Optional[pathlib.Path],
    is_primary: bool,
) -> Dict[str, Any]:
    """Synchronous onboarding callback used by the chat tool.

    Copies the source WAV (and optional CSV) into the project's audio/original/
    tree, then runs the existing onboard-speaker worker in-thread so the
    annotation scaffold and source_index registration follow the same path the
    HTTP /api/onboard/speaker endpoint uses.
    """
    project_root_path = _project_root()
    target_dir = project_root_path / "audio" / "original" / speaker
    target_dir.mkdir(parents=True, exist_ok=True)

    wav_dest = target_dir / source_wav_path.name
    wav_dest.write_bytes(source_wav_path.read_bytes())

    csv_dest: Optional[pathlib.Path] = None
    if source_csv_path is not None:
        csv_dest = target_dir / source_csv_path.name
        csv_dest.write_bytes(source_csv_path.read_bytes())

    job_id = _create_job(
        "onboard:speaker",
        {
            "speaker": speaker,
            "wavPath": str(wav_dest.relative_to(project_root_path)),
            "csvPath": str(csv_dest.relative_to(project_root_path)) if csv_dest else None,
            "initiatedBy": "chat",
        },
    )

    # Run synchronously — we're already inside the chat job's worker thread.
    _run_onboard_speaker_job(job_id, speaker, wav_dest, csv_dest)

    snapshot = _get_job_snapshot(job_id) or {}
    result = snapshot.get("result") if isinstance(snapshot, dict) else None

    if snapshot.get("status") != "complete":
        raise RuntimeError(
            "Onboarding job {0} failed: {1}".format(
                job_id, snapshot.get("error") or "unknown error"
            )
        )

    # If the caller marked this as non-primary, patch source_index.json accordingly.
    # _run_onboard_speaker_job already sets is_primary based on list length; respect
    # an explicit False override from the caller.
    if is_primary is False and isinstance(result, dict):
        source_index_path = _source_index_path()
        source_index = _read_json_file(source_index_path, {})
        speakers_block = source_index.get("speakers") if isinstance(source_index, dict) else None
        if isinstance(speakers_block, dict):
            entry = speakers_block.get(speaker)
            if isinstance(entry, dict):
                for source_entry in entry.get("source_wavs", []) or []:
                    if isinstance(source_entry, dict) and source_entry.get("filename") == wav_dest.name:
                        source_entry["is_primary"] = False
                _write_json_file(source_index_path, source_index)

    return {
        "jobId": job_id,
        "annotationPath": (result or {}).get("annotationPath") if isinstance(result, dict) else None,
        "wavPath": (result or {}).get("wavPath") if isinstance(result, dict) else None,
        "csvPath": (result or {}).get("csvPath") if isinstance(result, dict) else None,
    }


def _get_chat_runtime() -> Tuple[ParseChatTools, ChatOrchestrator]:
    global _chat_tools_runtime
    global _chat_orchestrator_runtime

    with _chat_runtime_lock:
        if _chat_tools_runtime is None:
            _chat_tools_runtime = ParseChatTools(
                project_root=_project_root(),
                config_path=_config_path(),
                docs_root=_chat_docs_root(),
                start_stt_job=_chat_start_stt_job,
                get_job_snapshot=_chat_get_job_snapshot,
                external_read_roots=_chat_external_read_roots(),
                memory_path=_chat_memory_path(),
                onboard_speaker=_chat_onboard_speaker,
            )

        if _chat_orchestrator_runtime is None:
            _chat_orchestrator_runtime = ChatOrchestrator(
                project_root=_project_root(),
                tools=_chat_tools_runtime,
                config_path=_config_path(),
            )

        return _chat_tools_runtime, _chat_orchestrator_runtime


def _run_chat_job(job_id: str, session_id: str) -> None:
    try:
        _set_job_progress(job_id, 5.0, message="Preparing chat context")

        session_snapshot = _chat_get_session_snapshot(session_id)
        if session_snapshot is None:
            raise RuntimeError("Unknown chat session: {0}".format(session_id))

        _set_job_progress(job_id, 20.0, message="Running chat orchestration")
        _, orchestrator = _get_chat_runtime()
        result = orchestrator.run(
            session_id=session_id,
            session_messages=session_snapshot.get("messages", []),
        )

        assistant_payload = result.get("assistant") if isinstance(result, dict) else {}
        if not isinstance(assistant_payload, dict):
            assistant_payload = {}

        assistant_content = str(assistant_payload.get("content") or "").strip()
        if not assistant_content:
            assistant_content = "I could not produce a response for this request."

        reasoning_meta = result.get("reasoning") if isinstance(result, dict) else None
        total_tokens = None
        if isinstance(reasoning_meta, dict):
            total_tokens_raw = reasoning_meta.get("totalTokens")
            if isinstance(total_tokens_raw, int) and total_tokens_raw >= 0:
                total_tokens = total_tokens_raw

        _chat_append_message(
            session_id,
            role="assistant",
            content=assistant_content,
            metadata={
                "model": result.get("model") if isinstance(result, dict) else None,
                "toolTraceCount": len(result.get("toolTrace", [])) if isinstance(result, dict) else 0,
                "tokensUsed": total_tokens,
            },
        )

        _set_job_complete(
            job_id,
            assistant_content,
            message="Chat run complete",
        )
    except ChatOrchestratorError as exc:
        _set_job_error(job_id, str(exc))
    except Exception as exc:
        _set_job_error(job_id, str(exc))


def _cleanup_old_jobs() -> None:
    now_ts = time.time()
    stale_ids: List[str] = []

    with _jobs_lock:
        for job_id, job in _jobs.items():
            if job.get("status") not in {"complete", "error"}:
                continue

            completed_ts = job.get("completed_ts")
            if not isinstance(completed_ts, (int, float)):
                continue

            if now_ts - float(completed_ts) > JOB_RETENTION_SECONDS:
                stale_ids.append(job_id)

        for job_id in stale_ids:
            _jobs.pop(job_id, None)


def _create_job(job_type: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    _cleanup_old_jobs()

    job_id = str(uuid.uuid4())
    now_ts = time.time()

    with _jobs_lock:
        _jobs[job_id] = {
            "jobId": job_id,
            "type": str(job_type),
            "status": "running",
            "progress": 0.0,
            "result": None,
            "error": None,
            "message": None,
            "segmentsProcessed": 0,
            "totalSegments": 0,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "completed_at": None,
            "created_ts": now_ts,
            "updated_ts": now_ts,
            "completed_ts": None,
            "meta": copy.deepcopy(metadata or {}),
        }

    return job_id


def _set_job_progress(
    job_id: str,
    progress: float,
    message: Optional[str] = None,
    segments_processed: Optional[int] = None,
    total_segments: Optional[int] = None,
) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job.get("status") != "running":
            return

        now_ts = time.time()
        job["progress"] = _clamp_progress(progress)
        job["updated_at"] = _utc_now_iso()
        job["updated_ts"] = now_ts

        if message is not None:
            job["message"] = str(message)
        if segments_processed is not None:
            try:
                job["segmentsProcessed"] = max(0, int(segments_processed))
            except (TypeError, ValueError):
                job["segmentsProcessed"] = 0
        if total_segments is not None:
            try:
                job["totalSegments"] = max(0, int(total_segments))
            except (TypeError, ValueError):
                job["totalSegments"] = 0


def _set_job_complete(
    job_id: str,
    result: Any,
    message: Optional[str] = None,
    segments_processed: Optional[int] = None,
    total_segments: Optional[int] = None,
) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return

        now_ts = time.time()
        job["status"] = "complete"
        job["progress"] = 100.0
        job["result"] = copy.deepcopy(result)
        job["error"] = None
        job["updated_at"] = _utc_now_iso()
        job["updated_ts"] = now_ts
        job["completed_at"] = _utc_now_iso()
        job["completed_ts"] = now_ts
        if message is not None:
            job["message"] = str(message)
        if segments_processed is not None:
            try:
                job["segmentsProcessed"] = max(0, int(segments_processed))
            except (TypeError, ValueError):
                pass
        if total_segments is not None:
            try:
                job["totalSegments"] = max(0, int(total_segments))
            except (TypeError, ValueError):
                pass


def _set_job_error(job_id: str, error_message: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return

        now_ts = time.time()
        job["status"] = "error"
        job["error"] = str(error_message)
        job["updated_at"] = _utc_now_iso()
        job["updated_ts"] = now_ts
        job["completed_at"] = _utc_now_iso()
        job["completed_ts"] = now_ts


def _get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return copy.deepcopy(job)


def _job_response_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    status = str(job.get("status") or "error")
    job_id = str(job.get("jobId") or "")
    payload: Dict[str, Any] = {
        "jobId": job_id,
        "status": status,
        "progress": _clamp_progress(job.get("progress", 0.0)),
        "result": job.get("result"),
    }

    job_type = str(job.get("type") or "")
    if job_type:
        payload["type"] = job_type

    meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
    if isinstance(meta, dict):
        session_id = str(meta.get("sessionId") or "").strip()
        if session_id:
            payload["sessionId"] = session_id

    if job.get("message"):
        payload["message"] = job.get("message")
    if job.get("error"):
        payload["error"] = str(job.get("error"))

    payload["segmentsProcessed"] = int(job.get("segmentsProcessed", 0) or 0)
    payload["totalSegments"] = int(job.get("totalSegments", 0) or 0)

    if job_type == "chat:run":
        payload["runId"] = job_id
        payload.update(_chat_public_policy_payload())

    done = status in {"complete", "error"}
    payload["done"] = done
    payload["success"] = status == "complete"
    return payload


def _load_cached_suggestions(speaker: str, concept_ids: List[str]) -> List[Dict[str, Any]]:
    suggestions_path = _project_root() / "ai_suggestions.json"
    if not suggestions_path.exists():
        return []

    try:
        payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, dict):
        return []

    suggestions_block = payload.get("suggestions")
    if not isinstance(suggestions_block, dict):
        return []

    if concept_ids:
        concept_iter = concept_ids
    else:
        concept_iter = sorted(suggestions_block.keys(), key=_concept_sort_key)

    output: List[Dict[str, Any]] = []
    for concept_id in concept_iter:
        entry = suggestions_block.get(str(concept_id))
        if not isinstance(entry, dict):
            continue

        speakers_map = entry.get("speakers")
        if not isinstance(speakers_map, dict):
            continue

        speaker_suggestions = speakers_map.get(speaker)
        if not isinstance(speaker_suggestions, list):
            continue

        output.append(
            {
                "conceptId": _concept_out_value(concept_id),
                "conceptEn": str(entry.get("concept_en") or ""),
                "suggestions": speaker_suggestions,
            }
        )

    return output


def _run_stt_job(job_id: str, speaker: str, source_wav: str, language: Optional[str]) -> None:
    try:
        audio_path = _resolve_project_path(source_wav)
        if not audio_path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(audio_path))

        _set_job_progress(job_id, 1.0, message="Initializing STT provider")
        provider = get_stt_provider()

        def _progress_callback(progress: float, segments_processed: int) -> None:
            _set_job_progress(
                job_id,
                progress,
                message="Transcribing",
                segments_processed=segments_processed,
            )

        segments = provider.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=_progress_callback,
        )

        result = {
            "speaker": speaker,
            "sourceWav": str(audio_path),
            "language": language,
            "segments": segments,
        }
        _set_job_complete(
            job_id,
            result,
            message="STT complete",
            segments_processed=len(segments),
            total_segments=len(segments),
        )
    except Exception as exc:
        _set_job_error(job_id, str(exc))


def _run_onboard_speaker_job(
    job_id: str,
    speaker: str,
    wav_dest: pathlib.Path,
    csv_dest: Optional[pathlib.Path],
) -> None:
    """Background worker for onboard/speaker — scaffold annotation + register in source_index."""
    try:
        _set_job_progress(job_id, 30.0, message="Scaffolding annotation record")

        # Build empty annotation record with source audio reference
        wav_relative = str(wav_dest.relative_to(_project_root()))
        annotation = _annotation_empty_record(speaker, wav_relative, None, None)
        annotation["speaker"] = speaker
        _annotation_touch_metadata(annotation, preserve_created=False)

        annotation_path = _annotation_record_path_for_speaker(speaker)
        _write_json_file(annotation_path, annotation)

        _set_job_progress(job_id, 60.0, message="Updating source index")

        # Register in source_index.json
        source_index_path = _source_index_path()
        source_index = _read_json_file(source_index_path, {})
        speakers_block = source_index.get("speakers")
        if not isinstance(speakers_block, dict):
            speakers_block = {}
            source_index["speakers"] = speakers_block

        speaker_entry = speakers_block.get(speaker)
        if not isinstance(speaker_entry, dict):
            speaker_entry = {"source_wavs": []}
            speakers_block[speaker] = speaker_entry

        source_wavs = speaker_entry.get("source_wavs")
        if not isinstance(source_wavs, list):
            source_wavs = []
            speaker_entry["source_wavs"] = source_wavs

        wav_filename = wav_dest.name
        already_registered = any(
            isinstance(entry, dict) and str(entry.get("filename", "")) == wav_filename
            for entry in source_wavs
        )
        if not already_registered:
            source_wavs.append({
                "filename": wav_filename,
                "path": wav_relative,
                "is_primary": len(source_wavs) == 0,
                "added_at": _utc_now_iso(),
            })

        _write_json_file(source_index_path, source_index)

        _set_job_progress(job_id, 90.0, message="Finalizing")

        result: Dict[str, Any] = {
            "speaker": speaker,
            "wavPath": wav_relative,
            "csvPath": str(csv_dest.relative_to(_project_root())) if csv_dest else None,
            "annotationPath": str(annotation_path.relative_to(_project_root())),
        }
        _set_job_complete(job_id, result, message="Speaker onboarded")
    except Exception as exc:
        _set_job_error(job_id, str(exc))


def _run_normalize_job(job_id: str, speaker: str, source_wav: str) -> None:
    """Background worker — runs ffmpeg loudnorm to normalize audio to LUFS target."""
    try:
        audio_path = _resolve_project_path(source_wav)
        if not audio_path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(audio_path))

        working_root = _project_root() / "audio" / "working"

        _set_job_progress(job_id, 5.0, message="Checking ffmpeg availability")

        # Verify ffmpeg is available
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            raise RuntimeError("ffmpeg is not installed or not on PATH")

        _set_job_progress(job_id, 10.0, message="Scanning loudness (pass 1)")

        # Pass 1: measure current loudness
        measure_cmd = [
            "ffmpeg", "-i", str(audio_path),
            "-af", "loudnorm=print_format=json",
            "-f", "null", "-"
        ]
        measure_result = subprocess.run(
            measure_cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        # Parse measured loudness from stderr (ffmpeg outputs stats there)
        stderr_text = measure_result.stderr or ""
        measured_i = None
        measured_tp = None
        measured_lra = None
        measured_thresh = None

        # Look for the JSON block that loudnorm prints
        json_start = stderr_text.rfind("{")
        json_end = stderr_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                loudnorm_stats = json.loads(stderr_text[json_start:json_end])
                measured_i = str(loudnorm_stats.get("input_i", ""))
                measured_tp = str(loudnorm_stats.get("input_tp", ""))
                measured_lra = str(loudnorm_stats.get("input_lra", ""))
                measured_thresh = str(loudnorm_stats.get("input_thresh", ""))
            except (json.JSONDecodeError, ValueError):
                pass

        _set_job_progress(job_id, 40.0, message="Normalizing audio (pass 2)")

        # Working copies are always PCM WAV, even when the staged source is MP3/FLAC.
        working_dir = working_root / speaker
        working_dir.mkdir(parents=True, exist_ok=True)
        output_path = build_normalized_output_path(audio_path, working_dir)

        # Pass 2: apply loudnorm with measured stats for precise normalization
        normalize_filter = "loudnorm=I={target}".format(target=NORMALIZE_LUFS_TARGET)
        if measured_i and measured_tp and measured_lra and measured_thresh:
            normalize_filter = (
                "loudnorm=I={target}"
                ":measured_I={mi}"
                ":measured_TP={mtp}"
                ":measured_LRA={mlra}"
                ":measured_thresh={mt}"
                ":linear=true"
            ).format(
                target=NORMALIZE_LUFS_TARGET,
                mi=measured_i,
                mtp=measured_tp,
                mlra=measured_lra,
                mt=measured_thresh,
            )

        normalize_cmd = [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-af", normalize_filter,
            "-ar", NORMALIZE_SAMPLE_RATE,
            "-ac", NORMALIZE_CHANNELS,
            "-c:a", NORMALIZE_AUDIO_CODEC,
            "-sample_fmt", NORMALIZE_SAMPLE_FORMAT,
            str(output_path),
        ]
        proc = subprocess.run(
            normalize_cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if proc.returncode != 0:
            error_tail = (proc.stderr or "")[-500:]
            raise RuntimeError("ffmpeg normalize failed: {0}".format(error_tail))

        if not output_path.exists():
            raise RuntimeError("ffmpeg produced no output file")

        _set_job_progress(job_id, 95.0, message="Finalizing")

        output_relative = str(output_path.relative_to(_project_root()))
        result: Dict[str, Any] = {
            "speaker": speaker,
            "sourcePath": source_wav,
            "normalizedPath": output_relative,
        }
        _set_job_complete(job_id, result, message="Normalization complete")
    except Exception as exc:
        _set_job_error(job_id, str(exc))


def _compute_cognates(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if cognate_compute_module is None:
        raise RuntimeError("compare.cognate_compute is unavailable")

    threshold_raw = payload.get("threshold", 0.60)
    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError):
        raise RuntimeError("threshold must be a number")

    if threshold <= 0.0:
        raise RuntimeError("threshold must be greater than 0")

    speaker_filter_values = _coerce_string_list(payload.get("speakers"))
    speaker_filter = set(speaker_filter_values)

    concept_filter_values = _coerce_concept_id_list(payload.get("conceptIds"))
    concept_filter = set(concept_filter_values)

    contact_override = [code.lower() for code in _coerce_string_list(payload.get("contactLanguages"))]
    if not contact_override:
        contact_override = [code.lower() for code in _coerce_string_list(payload.get("contact_languages"))]

    annotations_dir_raw = payload.get("annotationsDir", payload.get("annotations_dir", "annotations"))
    annotations_dir = _resolve_project_path(str(annotations_dir_raw))

    _set_job_progress(job_id, 10.0, message="Loading contact language data")
    contact_languages_from_config, refs_by_concept = cognate_compute_module.load_contact_language_data(
        _sil_config_path()
    )
    contact_languages = contact_override or contact_languages_from_config

    _set_job_progress(job_id, 25.0, message="Loading annotation files")
    forms_by_concept, discovered_speakers = cognate_compute_module.load_annotations(annotations_dir)

    filtered_forms: Dict[str, List[Any]] = {}
    for concept_id, records in forms_by_concept.items():
        normalized_concept_id = _normalize_concept_id(concept_id)
        if concept_filter and normalized_concept_id not in concept_filter:
            continue

        kept_records: List[Any] = []
        for record in records:
            record_speaker = str(getattr(record, "speaker", "")).strip()
            if speaker_filter and record_speaker not in speaker_filter:
                continue
            kept_records.append(record)

        if kept_records:
            filtered_forms[normalized_concept_id] = kept_records

    if concept_filter_values:
        selected_concept_ids = concept_filter_values
    else:
        selected_concept_ids = sorted(filtered_forms.keys(), key=_concept_sort_key)

    concept_specs = [
        cognate_compute_module.ConceptSpec(concept_id=concept_id, label="")
        for concept_id in selected_concept_ids
    ]

    _set_job_progress(job_id, 45.0, message="Computing cognate sets")
    cognate_sets = cognate_compute_module._compute_cognate_sets_with_lingpy(
        filtered_forms,
        concept_specs,
        threshold,
    )

    _set_job_progress(job_id, 75.0, message="Computing similarity scores")
    similarity = cognate_compute_module.compute_similarity_scores(
        forms_by_concept=filtered_forms,
        concepts=concept_specs,
        contact_languages=contact_languages,
        refs_by_concept=refs_by_concept,
    )

    if speaker_filter_values:
        speakers_included = sorted([speaker for speaker in discovered_speakers if speaker in speaker_filter])
    else:
        speakers_included = sorted(discovered_speakers)

    enrichments_payload = {
        "computed_at": _utc_now_iso(),
        "config": {
            "contact_languages": list(contact_languages),
            "speakers_included": speakers_included,
            "concepts_included": [_concept_out_value(concept_id) for concept_id in selected_concept_ids],
            "lexstat_threshold": round(float(threshold), 3),
        },
        "cognate_sets": cognate_sets,
        "similarity": similarity,
        "borrowing_flags": {},
        "manual_overrides": {},
    }

    _set_job_progress(job_id, 92.0, message="Writing parse-enrichments.json")
    output_path = _enrichments_path()
    _write_json_file(output_path, enrichments_payload)

    return {
        "type": "cognates",
        "outputPath": str(output_path),
        "computedAt": enrichments_payload["computed_at"],
        "conceptCount": len(enrichments_payload["config"]["concepts_included"]),
        "speakerCount": len(enrichments_payload["config"]["speakers_included"]),
    }


def _compute_contact_lexemes(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and merge contact language lexeme forms into sil_contact_languages.json."""
    from compare.contact_lexeme_fetcher import fetch_and_merge

    concepts_path = _project_root() / "concepts.csv"
    config_path = _sil_config_path()

    providers = _coerce_string_list(payload.get("providers")) or None
    languages_raw = _coerce_string_list(payload.get("languages"))

    if not languages_raw:
        import json as _json
        with open(config_path) as f:
            sil_config = _json.load(f)
        languages_raw = [k for k, v in sil_config.items() if isinstance(v, dict) and "name" in v]

    overwrite = bool(payload.get("overwrite", False))

    def _progress(pct: float, msg: str) -> None:
        _set_job_progress(job_id, pct * 0.9, message=msg)

    try:
        ai_config_path = _project_root() / "config" / "ai_config.json"
        import json as _json2
        with open(ai_config_path) as f:
            ai_config = _json2.load(f)
    except Exception:
        ai_config = {}

    _set_job_progress(job_id, 5.0, message="Starting contact lexeme fetch")

    filled = fetch_and_merge(
        concepts_path=concepts_path,
        config_path=config_path,
        language_codes=languages_raw,
        providers=providers,
        overwrite=overwrite,
        ai_config=ai_config,
        progress_callback=_progress,
    )

    _set_job_progress(job_id, 100.0, message="Done")
    return {
        "filled": filled,
        "config_path": str(config_path),
    }


def _run_compute_job(job_id: str, compute_type: str, payload: Dict[str, Any]) -> None:
    try:
        normalized_type = str(compute_type or "").strip().lower()
        _set_job_progress(job_id, 5.0, message="Starting compute job")

        if normalized_type in {"cognates", "similarity"}:
            result = _compute_cognates(job_id, payload)
        elif normalized_type == "contact-lexemes":
            result = _compute_contact_lexemes(job_id, payload)
        else:
            raise RuntimeError("Unsupported compute type: {0}".format(normalized_type))

        _set_job_complete(job_id, result, message="Compute complete")
    except Exception as exc:
        _set_job_error(job_id, str(exc))


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with static range support and API routes."""

    def translate_path(self, path: str) -> str:
        return str(_resolve_static_request_path(path))

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:
        if self._handle_api("GET"):
            return

        range_header = self.headers.get("Range")
        if range_header:
            self._serve_range(range_header)
        else:
            super().do_GET()

    def do_HEAD(self) -> None:
        if self._is_api_path(self.path):
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "GET, POST, PUT, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        range_header = self.headers.get("Range")
        if range_header:
            self._serve_range(range_header, head_only=True)
        else:
            super().do_HEAD()

    def do_POST(self) -> None:
        if self._handle_api("POST"):
            return
        self._send_json_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_PUT(self) -> None:
        if self._handle_api("PUT"):
            return
        self._send_json_error(HTTPStatus.NOT_FOUND, "Not found")

    def end_headers(self) -> None:
        self._add_cors_headers()
        super().end_headers()

    def _add_cors_headers(self) -> None:
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)

    def _request_path(self) -> str:
        return urlparse(self.path).path or "/"

    def _is_api_path(self, raw_path: str) -> bool:
        return (urlparse(raw_path).path or "").startswith("/api/")

    def _path_parts(self, request_path: str) -> List[str]:
        return [unquote(part) for part in request_path.strip("/").split("/") if part]

    def _read_json_body(self, required: bool = True) -> Any:
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length:
            if required:
                raise ApiError(HTTPStatus.BAD_REQUEST, "JSON request body is required")
            return {}

        try:
            content_length = int(raw_length)
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header")

        if content_length < 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header")

        if content_length == 0:
            if required:
                raise ApiError(HTTPStatus.BAD_REQUEST, "JSON request body is required")
            return {}

        raw_body = self.rfile.read(content_length)
        if not raw_body:
            if required:
                raise ApiError(HTTPStatus.BAD_REQUEST, "JSON request body is required")
            return {}

        try:
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid JSON body")

    def _expect_object(self, payload: Any, label: str) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "{0} must be a JSON object".format(label))
        return payload

    def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except BrokenPipeError:
            pass

    def _send_json_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": str(message)})

    def _handle_api(self, method: str) -> bool:
        request_path = self._request_path()
        if not request_path.startswith("/api/"):
            return False

        _cleanup_old_jobs()
        _cleanup_old_chat_sessions()

        try:
            if method == "GET":
                self._dispatch_api_get(request_path)
            elif method == "POST":
                self._dispatch_api_post(request_path)
            elif method == "PUT":
                self._dispatch_api_put(request_path)
            else:
                raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")
        except ApiError as exc:
            self._send_json_error(exc.status, exc.message)
        except Exception as exc:
            self._send_json_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        return True

    def _dispatch_api_get(self, request_path: str) -> None:
        parts = self._path_parts(request_path)
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "annotations":
            self._api_get_annotation(parts[2])
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "chat" and parts[2] == "session":
            self._api_get_chat_session(parts[3])
            return

        if request_path == "/api/enrichments":
            self._api_get_enrichments()
            return

        if request_path == "/api/config":
            self._api_get_config()
            return

        if request_path == "/api/auth/status":
            self._api_auth_status()
            return

        if request_path == "/api/export/lingpy":
            self._api_get_export_lingpy()
            return

        if request_path == "/api/export/nexus":
            self._api_get_export_nexus()
            return

        if request_path == "/api/contact-lexemes/coverage":
            self._api_get_contact_lexeme_coverage()
            return

        if request_path == "/api/tags":
            self._api_get_tags()
            return

        raise ApiError(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def _dispatch_api_post(self, request_path: str) -> None:
        if request_path == "/api/onboard/speaker":
            self._api_post_onboard_speaker()
            return

        if request_path == "/api/onboard/speaker/status":
            self._api_post_onboard_speaker_status()
            return

        if request_path == "/api/normalize":
            self._api_post_normalize()
            return

        if request_path == "/api/normalize/status":
            self._api_post_normalize_status()
            return

        if request_path == "/api/stt":
            self._api_post_stt_start()
            return

        if request_path == "/api/stt/status":
            self._api_post_stt_status()
            return

        if request_path == "/api/ipa":
            self._api_post_ipa()
            return

        if request_path == "/api/suggest":
            self._api_post_suggest()
            return

        if request_path == "/api/chat/session":
            self._api_post_chat_session()
            return

        if request_path == "/api/chat/run":
            self._api_post_chat_run_start()
            return

        if request_path == "/api/chat/run/status":
            self._api_post_chat_run_status()
            return

        if request_path == "/api/enrichments":
            self._api_post_enrichments()
            return

        if request_path == "/api/config":
            self._api_update_config()
            return

        if request_path == "/api/auth/key":
            self._api_auth_key()
            return

        if request_path == "/api/auth/start":
            self._api_auth_start()
            return

        if request_path == "/api/auth/poll":
            self._api_auth_poll()
            return

        if request_path == "/api/auth/logout":
            self._api_auth_logout()
            return

        if request_path == "/api/tags/merge":
            self._api_post_tags_merge()
            return

        parts = self._path_parts(request_path)

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "annotations":
            self._api_post_annotation(parts[2])
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "compute" and parts[2] == "status":
            self._api_post_compute_status(None)
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "compute" and parts[3] == "status":
            self._api_post_compute_status(parts[2])
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "compute":
            self._api_post_compute_start(parts[2])
            return

        if len(parts) == 3 and parts[0] == "api" and parts[2] == "status" and parts[1] not in {
            "stt",
            "compute",
        }:
            self._api_post_compute_status(parts[1])
            return

        raise ApiError(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def _dispatch_api_put(self, request_path: str) -> None:
        if request_path == "/api/config":
            self._api_update_config()
            return

        raise ApiError(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def _api_get_annotation(self, speaker_part: str) -> None:
        try:
            speaker = _normalize_speaker_id(speaker_part)
            annotation_path = _annotation_read_path_for_speaker(speaker)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        raw_payload = _read_json_any_file(annotation_path)
        normalized = _normalize_annotation_record(raw_payload, speaker)
        normalized["speaker"] = speaker
        _annotation_sync_speaker_tier(normalized)

        self._send_json(HTTPStatus.OK, normalized)

    def _api_post_annotation(self, speaker_part: str) -> None:
        try:
            speaker = _normalize_speaker_id(speaker_part)
            annotation_path = _annotation_record_path_for_speaker(speaker)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        body = self._read_json_body(required=True)
        try:
            payload = _annotation_payload_from_request_body(body)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        normalized = _normalize_annotation_record(payload, speaker)
        normalized["speaker"] = speaker
        _annotation_sync_speaker_tier(normalized)
        _annotation_touch_metadata(normalized, preserve_created=True)

        _write_json_file(annotation_path, normalized)

        self._send_json(
            HTTPStatus.OK,
            {
                "success": True,
                "speaker": speaker,
                "annotation": normalized,
            },
        )

    def _api_post_onboard_speaker(self) -> None:
        """Handle multipart POST /api/onboard/speaker — upload WAV + optional CSV."""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Type must be multipart/form-data")

        raw_length = self.headers.get("Content-Length", "")
        try:
            content_length = int(raw_length)
        except (ValueError, TypeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Length header is required")

        if content_length > ONBOARD_MAX_UPLOAD_BYTES:
            raise ApiError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "Upload exceeds {0} byte limit".format(ONBOARD_MAX_UPLOAD_BYTES),
            )

        # Parse multipart using cgi.FieldStorage
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(content_length),
        }
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ=environ,
            keep_blank_values=True,
        )

        # Extract speaker_id
        speaker_id_field = form.getfirst("speaker_id", "")
        if isinstance(speaker_id_field, bytes):
            speaker_id_field = speaker_id_field.decode("utf-8", errors="replace")
        speaker_id_raw = str(speaker_id_field or "").strip()

        try:
            speaker = _normalize_speaker_id(speaker_id_raw)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        # Extract audio file
        audio_item = form["audio"] if "audio" in form else None
        if audio_item is None or not getattr(audio_item, "filename", None):
            raise ApiError(HTTPStatus.BAD_REQUEST, "audio file is required")

        audio_filename = os.path.basename(audio_item.filename or "upload.wav")
        audio_ext = pathlib.Path(audio_filename).suffix.lower()
        if audio_ext not in ONBOARD_AUDIO_EXTENSIONS:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "Unsupported audio format: {0} (allowed: {1})".format(
                    audio_ext, ", ".join(sorted(ONBOARD_AUDIO_EXTENSIONS))
                ),
            )

        # Write audio to audio/original/<speaker>/
        speaker_audio_dir = _project_root() / "audio" / "original" / speaker
        speaker_audio_dir.mkdir(parents=True, exist_ok=True)
        wav_dest = speaker_audio_dir / audio_filename

        audio_data = audio_item.file.read()
        wav_dest.write_bytes(audio_data)

        # Extract optional CSV
        csv_dest: Optional[pathlib.Path] = None
        csv_item = form["csv"] if "csv" in form else None
        if csv_item is not None and getattr(csv_item, "filename", None):
            csv_filename = os.path.basename(csv_item.filename or "elicitation.csv")
            csv_dest = speaker_audio_dir / csv_filename
            csv_data = csv_item.file.read()
            csv_dest.write_bytes(csv_data)

        # Create background job
        job_id = _create_job(
            "onboard:speaker",
            {
                "speaker": speaker,
                "wavPath": str(wav_dest.relative_to(_project_root())),
                "csvPath": str(csv_dest.relative_to(_project_root())) if csv_dest else None,
            },
        )

        thread = threading.Thread(
            target=_run_onboard_speaker_job,
            args=(job_id, speaker, wav_dest, csv_dest),
            daemon=True,
        )
        thread.start()

        self._send_json(
            HTTPStatus.OK,
            {
                "job_id": job_id,
                "jobId": job_id,
                "status": "running",
                "speaker": speaker,
            },
        )

    def _api_post_normalize(self) -> None:
        """Handle POST /api/normalize — start audio normalization job."""
        body = self._expect_object(self._read_json_body(), "Request body")
        speaker = str(body.get("speaker") or "").strip()

        if not speaker:
            raise ApiError(HTTPStatus.BAD_REQUEST, "speaker is required")

        try:
            speaker = _normalize_speaker_id(speaker)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        # Resolve source WAV — use explicit path if provided, else look up primary source
        source_wav = str(body.get("sourceWav") or body.get("source_wav") or "").strip()
        if not source_wav:
            source_wav = _annotation_primary_source_wav(speaker)

        if not source_wav:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "No source audio found for speaker '{0}'. Provide sourceWav explicitly.".format(speaker),
            )

        job_id = _create_job(
            "normalize",
            {
                "speaker": speaker,
                "sourceWav": source_wav,
            },
        )

        thread = threading.Thread(
            target=_run_normalize_job,
            args=(job_id, speaker, source_wav),
            daemon=True,
        )
        thread.start()

        self._send_json(
            HTTPStatus.OK,
            {
                "job_id": job_id,
                "jobId": job_id,
                "status": "running",
            },
        )

    def _api_post_onboard_speaker_status(self) -> None:
        """Poll status for an onboard:speaker job."""
        body = self._expect_object(self._read_json_body(), "Request body")
        job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
        if not job_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "job_id is required")

        job = _get_job_snapshot(job_id)
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown job_id")

        if str(job.get("type") or "") != "onboard:speaker":
            raise ApiError(HTTPStatus.BAD_REQUEST, "job_id is not an onboard:speaker job")

        self._send_json(HTTPStatus.OK, _job_response_payload(job))

    def _api_post_normalize_status(self) -> None:
        """Poll status for a normalize job."""
        body = self._expect_object(self._read_json_body(), "Request body")
        job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
        if not job_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "job_id is required")

        job = _get_job_snapshot(job_id)
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown job_id")

        if str(job.get("type") or "") != "normalize":
            raise ApiError(HTTPStatus.BAD_REQUEST, "job_id is not a normalize job")

        self._send_json(HTTPStatus.OK, _job_response_payload(job))

    def _api_post_stt_start(self) -> None:
        body = self._expect_object(self._read_json_body(), "Request body")
        speaker = str(body.get("speaker") or "").strip()
        source_wav = str(body.get("sourceWav") or body.get("source_wav") or "").strip()

        language_raw = body.get("language")
        language = str(language_raw).strip() if language_raw is not None else None
        if language == "":
            language = None

        if not speaker:
            raise ApiError(HTTPStatus.BAD_REQUEST, "speaker is required")
        if not source_wav:
            raise ApiError(HTTPStatus.BAD_REQUEST, "sourceWav is required")

        job_id = _create_job(
            "stt",
            {
                "speaker": speaker,
                "sourceWav": source_wav,
                "language": language,
            },
        )

        thread = threading.Thread(
            target=_run_stt_job,
            args=(job_id, speaker, source_wav, language),
            daemon=True,
        )
        thread.start()

        self._send_json(
            HTTPStatus.OK,
            {
                "jobId": job_id,
                "status": "running",
            },
        )

    def _api_post_stt_status(self) -> None:
        body = self._expect_object(self._read_json_body(), "Request body")
        job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
        if not job_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId is required")

        job = _get_job_snapshot(job_id)
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown jobId")

        if job.get("type") != "stt":
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId is not an STT job")

        self._send_json(HTTPStatus.OK, _job_response_payload(job))

    def _api_post_ipa(self) -> None:
        body = self._expect_object(self._read_json_body(), "Request body")
        text = str(body.get("text") or "")
        language = str(body.get("language") or "").strip() or "sdh"

        provider = get_ipa_provider()
        ipa = provider.to_ipa(text=text, language=language)
        self._send_json(HTTPStatus.OK, {"ipa": ipa})

    def _api_post_suggest(self) -> None:
        body = self._expect_object(self._read_json_body(), "Request body")
        speaker = str(body.get("speaker") or "").strip()
        if not speaker:
            raise ApiError(HTTPStatus.BAD_REQUEST, "speaker is required")

        concept_ids = _coerce_concept_id_list(body.get("conceptIds") or body.get("concept_ids") or [])

        suggestions: Any = []
        try:
            llm_provider = get_llm_provider()
            suggest_fn = getattr(llm_provider, "suggest_concepts", None)
            if callable(suggest_fn):
                transcript_windows = body.get("transcriptWindows", body.get("transcript_windows", []))
                reference_forms = body.get("referenceForms", body.get("reference_forms", []))
                try:
                    suggestions = suggest_fn(transcript_windows, reference_forms)
                except Exception:
                    suggestions = []
        except Exception:
            suggestions = []

        if not suggestions:
            suggestions = _load_cached_suggestions(speaker, concept_ids)

        self._send_json(HTTPStatus.OK, {"suggestions": suggestions})

    def _api_get_chat_session(self, session_part: str) -> None:
        try:
            session_id = _normalize_chat_session_id(session_part)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        session = _chat_get_session_snapshot(session_id)
        if session is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown sessionId")

        self._send_json(HTTPStatus.OK, _chat_session_public_payload(session))

    def _api_post_chat_session(self) -> None:
        body = self._read_json_body(required=False)
        body_obj = self._expect_object(body or {}, "Request body")

        raw_session_id = body_obj.get("sessionId", body_obj.get("session_id"))
        session_id = str(raw_session_id).strip() if raw_session_id is not None else ""

        try:
            session = _chat_create_or_get_session(session_id if session_id else None)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        self._send_json(HTTPStatus.OK, _chat_session_public_payload(session))

    def _api_post_chat_run_start(self) -> None:
        body = self._expect_object(self._read_json_body(required=True), "Request body")
        policy = None

        try:
            policy, message_text = _chat_validate_run_request(body)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        raw_session_id = body.get("sessionId", body.get("session_id"))
        session_id = str(raw_session_id).strip() if raw_session_id is not None else ""

        try:
            session = _chat_create_or_get_session(session_id if session_id else None)
            resolved_session_id = str(session.get("sessionId") or "")
            _chat_append_message(resolved_session_id, role="user", content=message_text)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        job_id = _create_job(
            "chat:run",
            {
                "sessionId": resolved_session_id,
            },
        )

        thread = threading.Thread(
            target=_run_chat_job,
            args=(job_id, resolved_session_id),
            daemon=True,
        )
        thread.start()

        response_payload = {
            "jobId": job_id,
            "runId": job_id,
            "sessionId": resolved_session_id,
            "status": "running",
        }
        response_payload.update(_chat_public_policy_payload())
        if policy is not None:
            response_payload["provider"] = str(policy.get("provider") or response_payload.get("provider") or "")
            response_payload["model"] = str(policy.get("model") or response_payload.get("model") or "")

        self._send_json(HTTPStatus.OK, response_payload)

    def _api_post_chat_run_status(self) -> None:
        body = self._expect_object(self._read_json_body(required=True), "Request body")
        job_id = str(
            body.get("jobId")
            or body.get("job_id")
            or body.get("runId")
            or body.get("run_id")
            or ""
        ).strip()
        if not job_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId or runId is required")

        job = _get_job_snapshot(job_id)
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown jobId")

        if str(job.get("type") or "") != "chat:run":
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId is not a chat run")

        self._send_json(HTTPStatus.OK, _job_response_payload(job))

    def _api_post_compute_start(self, compute_type: str) -> None:
        normalized_type = str(compute_type or "").strip().lower()
        if not normalized_type or normalized_type == "status":
            raise ApiError(HTTPStatus.BAD_REQUEST, "Compute type is required")

        body = self._read_json_body(required=False)
        body_obj = self._expect_object(body or {}, "Request body")

        job_id = _create_job(
            "compute:{0}".format(normalized_type),
            {
                "computeType": normalized_type,
                "payload": body_obj,
            },
        )

        thread = threading.Thread(
            target=_run_compute_job,
            args=(job_id, normalized_type, body_obj),
            daemon=True,
        )
        thread.start()

        self._send_json(
            HTTPStatus.OK,
            {
                "jobId": job_id,
                "status": "running",
            },
        )

    def _api_post_compute_status(self, compute_type: Optional[str]) -> None:
        body = self._expect_object(self._read_json_body(), "Request body")
        job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
        if not job_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId is required")

        job = _get_job_snapshot(job_id)
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown jobId")

        job_type = str(job.get("type") or "")
        if not job_type.startswith("compute:"):
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId is not a compute job")

        if compute_type:
            expected_type = str(compute_type).strip().lower()
            if job_type != "compute:{0}".format(expected_type):
                raise ApiError(HTTPStatus.BAD_REQUEST, "jobId does not match compute type")

        self._send_json(HTTPStatus.OK, _job_response_payload(job))

    def _api_get_annotation(self, speaker: str) -> None:
        """Return annotation JSON for a single speaker.

        Lookup order: ``<speaker>.parse.json`` then ``<speaker>.json``.
        Returns 404 if neither exists.
        """
        safe_speaker = pathlib.Path(speaker).name  # prevent path traversal
        if not safe_speaker:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid speaker id")

        annotations_dir = _project_root() / "annotations"
        canonical = annotations_dir / (safe_speaker + ".parse.json")
        legacy = annotations_dir / (safe_speaker + ".json")

        target: Optional[pathlib.Path] = None
        if canonical.is_file():
            target = canonical
        elif legacy.is_file():
            target = legacy

        if target is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "No annotation file for speaker: {0}".format(safe_speaker))

        payload = _read_json_file(target, {})
        self._send_json(HTTPStatus.OK, payload)

    def _api_get_enrichments(self) -> None:
        payload = _read_json_file(_enrichments_path(), _default_enrichments_payload())
        self._send_json(HTTPStatus.OK, {"enrichments": payload})

    def _api_post_enrichments(self) -> None:
        body = self._read_json_body(required=True)
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Enrichments payload must be a JSON object")

        enrichments_payload = body.get("enrichments") if isinstance(body.get("enrichments"), dict) else body
        _write_json_file(_enrichments_path(), enrichments_payload)
        self._send_json(HTTPStatus.OK, {"success": True})

    # ── Auth endpoints ──────────────────────────────────────────────

    def _api_auth_key(self) -> None:
        """POST /api/auth/key — store a direct API key."""
        try:
            data = self._read_json_body()
            key = str(data.get("key") or "").strip()
            provider = str(data.get("provider") or "xai").strip()
            if not key:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "key is required"})
                return
            from ai.openai_auth import save_api_key, get_auth_status
            save_api_key(key, provider)
            _reset_chat_runtime_after_auth_key_save()
            status = get_auth_status()
            self._send_json(HTTPStatus.OK, status)
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _api_auth_status(self) -> None:
        from ai.openai_auth import get_auth_status
        self._send_json(HTTPStatus.OK, get_auth_status())

    def _api_auth_start(self) -> None:
        from ai.openai_auth import start_device_auth
        try:
            result = start_device_auth()
            self._send_json(HTTPStatus.OK, result)
        except RuntimeError as e:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

    def _api_auth_poll(self) -> None:
        from ai.openai_auth import poll_device_auth
        result = poll_device_auth()
        self._send_json(HTTPStatus.OK, result)

    def _api_auth_logout(self) -> None:
        from ai.openai_auth import clear_tokens
        clear_tokens()
        self._send_json(HTTPStatus.OK, {"success": True})

    # ── Tag endpoints ────────────────────────────────────────────

    def _api_get_tags(self) -> None:
        """GET /api/tags — return parse-tags.json as tag array."""
        tags_path = _project_root() / "parse-tags.json"
        if not tags_path.exists():
            self._send_json(HTTPStatus.OK, {"tags": []})
            return
        try:
            with open(tags_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._send_json(HTTPStatus.OK, {"tags": data})
            else:
                self._send_json(HTTPStatus.OK, {"tags": []})
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _api_post_tags_merge(self) -> None:
        """POST /api/tags/merge — additive merge of incoming tags into parse-tags.json."""
        try:
            data = self._expect_object(self._read_json_body(required=True), "Request body")
            incoming = data.get("tags")
            if not isinstance(incoming, list):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "tags must be an array"})
                return

            tags_path = _project_root() / "parse-tags.json"
            existing: list = []
            if tags_path.exists():
                try:
                    with open(tags_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, list):
                        existing = raw
                except Exception:
                    existing = []

            existing_by_id = {t["id"]: t for t in existing if isinstance(t, dict) and "id" in t}
            for tag in incoming:
                if not isinstance(tag, dict) or "id" not in tag:
                    continue
                tid = str(tag["id"])
                if tid in existing_by_id:
                    prev = existing_by_id[tid]
                    merged = set(prev.get("concepts") or [])
                    merged.update(tag.get("concepts") or [])
                    prev["concepts"] = sorted(merged)
                    prev["label"] = tag.get("label", prev.get("label", ""))
                    prev["color"] = tag.get("color", prev.get("color", "#6b7280"))
                else:
                    existing_by_id[tid] = {
                        "id": tid,
                        "label": str(tag.get("label") or ""),
                        "color": str(tag.get("color") or "#6b7280"),
                        "concepts": sorted(set(tag.get("concepts") or [])),
                    }

            merged_list = list(existing_by_id.values())
            with open(tags_path, "w", encoding="utf-8") as f:
                json.dump(merged_list, f, indent=2, ensure_ascii=False)

            self._send_json(HTTPStatus.OK, {"ok": True, "tagCount": len(merged_list)})
        except ApiError:
            raise
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    # ── Config endpoints ─────────────────────────────────────────

    def _api_get_config(self) -> None:
        config = load_ai_config(_config_path())

        # Inject concepts from concepts.csv
        concepts_path = _project_root() / "concepts.csv"
        concepts: list = []
        if concepts_path.exists():
            import csv as _csv
            with open(concepts_path, newline="", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    cid = str(row.get("id") or "").strip()
                    label = str(row.get("concept_en") or "").strip()
                    if cid and label:
                        concepts.append({"id": cid, "label": label})
        config["concepts"] = concepts

        self._send_json(HTTPStatus.OK, {"config": config})

    def _api_get_export_lingpy(self) -> None:
        """Stream LingPy-compatible wordlist TSV as a file download."""
        import tempfile
        tmp_fd, tmp_str = tempfile.mkstemp(suffix=".tsv")
        import os as _os
        _os.close(tmp_fd)
        tmp_path = pathlib.Path(tmp_str)
        try:
            cognate_compute_module.export_wordlist_tsv(
                _enrichments_path(),
                _project_root() / "annotations",
                tmp_path,
            )
            content = tmp_path.read_bytes()
        finally:
            try:
                _os.unlink(tmp_str)
            except OSError:
                pass
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="parse-wordlist.tsv"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _api_get_export_nexus(self) -> None:
        """NEXUS export placeholder — not yet implemented."""
        self._send_json_error(HTTPStatus.NOT_IMPLEMENTED, "NEXUS export not yet implemented")

    def _api_get_contact_lexeme_coverage(self) -> None:
        """Return coverage stats for contact language lexeme data."""
        import json as _json
        config_path = _sil_config_path()
        try:
            with open(config_path) as f:
                config = _json.load(f)
        except (OSError, ValueError):
            config = {}

        concepts_path = _project_root() / "concepts.csv"
        try:
            import csv as _csv
            with open(concepts_path, newline="") as f:
                reader = _csv.DictReader(f)
                all_concepts = [row.get("concept_en", "").strip() for row in reader if row.get("concept_en")]
        except (OSError, KeyError):
            all_concepts = []

        languages = {}
        for lang_code, lang_data in config.items():
            if not isinstance(lang_data, dict) or "name" not in lang_data:
                continue
            concepts_dict = lang_data.get("concepts", {})
            filled = {c: v for c, v in concepts_dict.items() if v}
            empty = [c for c in all_concepts if not filled.get(c)]
            languages[lang_code] = {
                "name": lang_data.get("name", lang_code),
                "total": len(all_concepts),
                "filled": len(filled),
                "empty": len(empty),
                "concepts": filled,
            }

        self._send_json(HTTPStatus.OK, {"languages": languages})

    def _api_update_config(self) -> None:
        body = self._expect_object(self._read_json_body(), "Request body")
        current = load_ai_config(_config_path())
        merged = _deep_merge_dicts(current, body)
        _write_json_file(_config_path(), merged)
        self._send_json(HTTPStatus.OK, {"success": True, "config": merged})

    def _parse_single_range(self, range_header: str, file_size: int) -> Tuple[int, int]:
        unit, _, ranges_spec = range_header.partition("=")
        if unit.strip().lower() != "bytes":
            raise ValueError("Unsupported range unit: {0!r}".format(unit))

        ranges_spec = ranges_spec.strip()
        if not ranges_spec:
            raise ValueError("Empty range spec")

        if "," in ranges_spec:
            raise ValueError("Multiple byte ranges are not supported")

        start_str, _, end_str = ranges_spec.partition("-")
        start_str = start_str.strip()
        end_str = end_str.strip()

        if start_str == "" and end_str == "":
            raise ValueError("Empty range spec")

        if start_str == "":
            suffix_length = int(end_str)
            if suffix_length <= 0:
                raise ValueError("Non-positive suffix length")
            start = max(0, file_size - suffix_length)
            end = file_size - 1
            return start, end

        start = int(start_str)
        if start < 0:
            raise ValueError("Negative range start")
        if start >= file_size:
            raise ValueError("Range start beyond EOF")

        if end_str == "":
            end = file_size - 1
        else:
            end = int(end_str)
            if end < start:
                raise ValueError("Range start exceeds range end")
            end = min(end, file_size - 1)

        return start, end

    def _serve_range(self, range_header: str, head_only: bool = False) -> None:
        path = self.translate_path(self.path)

        if os.path.isdir(path):
            if head_only:
                super().do_HEAD()
            else:
                super().do_GET()
            return

        try:
            file_size = os.path.getsize(path)
        except (OSError, FileNotFoundError):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        try:
            start, end = self._parse_single_range(range_header, file_size)
        except (ValueError, TypeError) as exc:
            self._send_416(file_size, reason=str(exc))
            return

        chunk_size = end - start + 1
        ctype = self.guess_type(path)

        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(chunk_size))
        self.send_header("Content-Range", "bytes {0}-{1}/{2}".format(start, end, file_size))
        self.end_headers()

        if head_only:
            return

        try:
            with open(path, "rb") as handle:
                handle.seek(start)
                remaining = chunk_size
                buffer_size = 64 * 1024
                while remaining > 0:
                    to_read = min(buffer_size, remaining)
                    data = handle.read(to_read)
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
        except (OSError, BrokenPipeError):
            pass

    def _send_416(self, file_size: int, reason: str = "") -> None:
        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        self.send_header("Content-Range", "bytes */{0}".format(file_size))
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "0")
        self.end_headers()


def _get_local_ips() -> List[str]:
    ips: List[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ips.append(sock.getsockname()[0])
    except OSError:
        pass
    return ips


def _startup_banner_lines(
    serve_dir: pathlib.Path,
    local_ips: Sequence[str],
) -> List[str]:
    lines = [
        "",
        "=" * 60,
        "  PARSE - HTTP Server",
        "=" * 60,
        "  Serving: {0}".format(serve_dir),
        "  Port   : {0}".format(PORT),
        "",
        "  React dev UI (current workflow; requires `npm run dev`):",
        "    Annotate: http://localhost:5173/",
        "    Compare : http://localhost:5173/compare",
    ]
    if _has_built_frontend(serve_dir):
        lines.extend([
            "",
            "  Built UI (served by this Python server after `npm run build`):",
            "    PARSE   : http://localhost:{0}/".format(PORT),
            "    Compare : http://localhost:{0}/compare".format(PORT),
        ])
        for ip in local_ips:
            lines.append("    PARSE   : http://{0}:{1}/".format(ip, PORT))
            lines.append("    Compare : http://{0}:{1}/compare".format(ip, PORT))
    else:
        lines.extend([
            "",
            "  Built UI (served by this Python server after `npm run build`):",
            "    dist/index.html not found — run `npm run build` to serve the frontend here.",
        ])
    lines.extend([
        "",
        "  Features: Range requests [x]  CORS [x]  Threaded [x]  API [x]",
        "  Press Ctrl+C to stop.",
        "=" * 60,
    ])
    return lines


def main() -> None:
    serve_dir = _project_root()

    # Guard: refuse to run if workspace is on a Windows mount (WSL /mnt/ path).
    # PARSE workspaces must live on WSL-native ext4 for performance with large WAVs.
    resolved = str(serve_dir.resolve())
    if resolved.startswith("/mnt/"):
        print("=" * 60, file=sys.stderr)
        print("FATAL: workspace is on a Windows mount:", file=sys.stderr)
        print("  " + resolved, file=sys.stderr)
        print("", file=sys.stderr)
        print("PARSE requires a WSL-native workspace (e.g. /home/lucas/parse-workspace/).", file=sys.stderr)
        print("Run the server with:  cd /home/lucas/parse-workspace && python server.py", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    os.chdir(serve_dir)

    server_address = (HOST, PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, RangeRequestHandler)
    local_ips = _get_local_ips()

    for line in _startup_banner_lines(serve_dir, local_ips):
        print(line)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
