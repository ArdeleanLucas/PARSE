"""PARSE HTTP server with static range serving and API endpoints."""

import cgi
import copy
import http.server
import io
import json
import math
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
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from ai.chat_orchestrator import ChatOrchestrator, ChatOrchestratorError, READ_ONLY_NOTICE
from ai.chat_tools import ChatToolExecutionError, ChatToolValidationError, ParseChatTools
from ai.workflow_tools import WorkflowTools
from ai.provider import get_chat_config, get_llm_provider, get_ortho_provider, get_stt_provider, load_ai_config, resolve_context_window
from ai.ipa_transcribe import transcribe_slice as _acoustic_transcribe_slice
from audio_pipeline_paths import build_normalized_output_path
from external_api.catalog import build_mcp_http_catalog, get_mcp_tool_entry, mcp_exposure_payload, resolve_catalog_mode
from external_api.openapi import build_openapi_document, render_redoc_html, render_swagger_ui_html

try:
    from compare import cognate_compute as cognate_compute_module
except Exception:
    cognate_compute_module = None


HOST = "0.0.0.0"
PORT = 8766
JOB_RETENTION_SECONDS = 60 * 60
JOB_LOG_MAX_ENTRIES = 200
JOB_LOCK_TTL_SECONDS = 10 * 60
CONFIG_SCHEMA_VERSION = 1

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


class JobResourceConflictError(Exception):
    """Raised when a background job tries to mutate a speaker already locked by another active job."""

    def __init__(
        self,
        *,
        resource_kind: str,
        resource_id: str,
        holder_job_id: str,
        holder_job_type: str,
        holder_status: str,
    ) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        self.holder_job_id = holder_job_id
        self.holder_job_type = holder_job_type
        self.holder_status = holder_status
        super().__init__(
            "{0}:{1} is locked by job {2} ({3}, {4})".format(
                resource_kind,
                resource_id,
                holder_job_id,
                holder_job_type,
                holder_status,
            )
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def _utc_iso_from_ts(timestamp: float) -> str:
    return datetime.fromtimestamp(float(timestamp), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _workspace_frontend_config(base_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = copy.deepcopy(base_config) if isinstance(base_config, dict) else {}

    project_payload = _read_json_file(_project_json_path(), {})
    if not isinstance(project_payload, dict):
        project_payload = {}
    source_index_payload = _read_json_file(_source_index_path(), {})
    if not isinstance(source_index_payload, dict):
        source_index_payload = {}

    speakers: List[str] = []
    speakers_value = project_payload.get("speakers")
    if isinstance(speakers_value, dict):
        speakers.extend(str(key).strip() for key in speakers_value.keys() if str(key).strip())
    elif isinstance(speakers_value, list):
        speakers.extend(str(item).strip() for item in speakers_value if str(item).strip())

    source_speakers = source_index_payload.get("speakers")
    if isinstance(source_speakers, dict):
        speakers.extend(str(key).strip() for key in source_speakers.keys() if str(key).strip())
    speakers = sorted(dict.fromkeys(speakers))

    concepts_path = _project_root() / "concepts.csv"
    concepts: list = []
    if concepts_path.exists():
        import csv as _csv
        with open(concepts_path, newline="", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                cid = str(row.get("id") or "").strip()
                label = str(row.get("concept_en") or "").strip()
                if not (cid and label):
                    continue
                entry: Dict[str, Any] = {"id": cid, "label": label}
                survey_item = str(row.get("survey_item") or "").strip()
                if survey_item:
                    entry["survey_item"] = survey_item
                custom_order_raw = str(row.get("custom_order") or "").strip()
                if custom_order_raw:
                    try:
                        entry["custom_order"] = int(custom_order_raw)
                    except ValueError:
                        try:
                            entry["custom_order"] = float(custom_order_raw)
                        except ValueError:
                            pass
                concepts.append(entry)

    language_block = project_payload.get("language") if isinstance(project_payload.get("language"), dict) else {}
    language_code = str(
        project_payload.get("language_code")
        or language_block.get("code")
        or config.get("language_code")
        or "und"
    ).strip() or "und"
    project_name = str(
        project_payload.get("project_name")
        or project_payload.get("name")
        or config.get("project_name")
        or "PARSE"
    ).strip() or "PARSE"

    config["project_name"] = project_name
    config["language_code"] = language_code
    config["speakers"] = speakers
    config["concepts"] = concepts
    config["audio_dir"] = str(project_payload.get("audio_dir") or config.get("audio_dir") or "audio")
    config["annotations_dir"] = str(project_payload.get("annotations_dir") or config.get("annotations_dir") or "annotations")
    config["schema_version"] = CONFIG_SCHEMA_VERSION
    return config


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

    # Always emit ``manuallyAdjusted`` — true or false — so every interval
    # has the same shape on disk. Consumers (UI, agents, Praat export) can
    # branch on a stable boolean without having to treat "absent" and
    # "false" as a third case. Legacy records without the key are read
    # back as false, which matches pre-PR-197 behaviour.
    return {
        "start": float(start),
        "end": float(end),
        "text": "" if raw_interval.get("text") is None else str(raw_interval.get("text")),
        "manuallyAdjusted": bool(raw_interval.get("manuallyAdjusted")),
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


def _offset_detect_payload(
    *,
    speaker: str,
    offset_sec: float,
    confidence: float,
    n_matched: int,
    total_anchors: int,
    total_segments: int,
    method: str,
    spread_sec: float,
    matches: List[Dict[str, Any]],
    anchor_distribution: str,
) -> Dict[str, Any]:
    """Shape the response body for /api/offset/detect{,-from-pair}.

    Direction is reported in plain language so MCP / chat clients can read
    it back to the user without sign confusion. The numeric ``offsetSec``
    is the value to pass to /api/offset/apply unchanged.
    """
    if abs(offset_sec) < 1e-3:
        direction = "none"
        direction_label = "no shift needed"
    elif offset_sec > 0:
        direction = "later"
        direction_label = "{0:.3f} s later (toward the end)".format(offset_sec)
    else:
        direction = "earlier"
        direction_label = "{0:.3f} s earlier (toward the start)".format(abs(offset_sec))

    reliable = bool(
        n_matched >= 3 and confidence >= 0.5 and (spread_sec <= 2.0 or n_matched == 1)
    )
    warnings: List[str] = []
    if n_matched < 3 and method != "manual_pair":
        warnings.append(
            "Only {0} anchor match{1} were found — apply with caution.".format(
                n_matched, "" if n_matched == 1 else "es"
            )
        )
    if spread_sec > 2.0:
        warnings.append(
            "Match offsets disagree by ±{0:.2f}s — the detected value may be noisy.".format(spread_sec)
        )
    if confidence < 0.5 and method != "manual_pair":
        warnings.append("Low confidence; consider re-running STT or using a manual single-anchor pair.")
    if method == "bucket_vote":
        warnings.append(
            "Monotonic alignment failed; fell back to bucket vote which is more vulnerable to false matches."
        )

    return {
        "speaker": speaker,
        "offsetSec": float(offset_sec),
        "confidence": float(confidence),
        "nAnchors": int(n_matched),
        "totalAnchors": int(total_anchors),
        "totalSegments": int(total_segments),
        "method": method,
        "spreadSec": float(spread_sec),
        "direction": direction,
        "directionLabel": direction_label,
        "anchorDistribution": anchor_distribution,
        "reliable": reliable,
        "warnings": warnings,
        "matches": matches,
    }


def _annotation_find_concept_interval(
    record: Dict[str, Any], concept_id: str
) -> Optional[Dict[str, Any]]:
    """Return the first interval whose ``concept_id`` (or text) matches.

    Searches concept tier first (where the id naturally lives), then ortho
    and ipa tiers as fallback for legacy records that stored the concept id
    in the text field.
    """
    if not isinstance(record, dict) or not concept_id:
        return None
    needle = str(concept_id).strip()
    if not needle:
        return None
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return None
    for tier_key in ("concept", "ortho", "ipa"):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals")
        if not isinstance(intervals, list):
            continue
        for raw in intervals:
            normalized = _annotation_normalize_interval(raw)
            if normalized is None:
                continue
            cid = str(raw.get("concept_id") or raw.get("conceptId") or "").strip()
            text = str(normalized.get("text") or "").strip()
            if cid == needle or text == needle:
                return normalized
    return None


def _annotation_offset_anchor_intervals(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return interval dicts (start/end/text) suitable as offset-detection anchors.

    Prefers ``ortho`` and ``ipa`` tiers (transcribed forms that should match
    STT output); falls back to ``concept`` only if neither is populated.
    """
    if not isinstance(record, dict):
        return []
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return []

    for tier_key in ("ortho", "ipa", "concept"):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue
        intervals_raw = tier.get("intervals")
        if not isinstance(intervals_raw, list):
            continue

        collected: List[Dict[str, Any]] = []
        for raw in intervals_raw:
            normalized = _annotation_normalize_interval(raw)
            if normalized is None:
                continue
            text = str(normalized.get("text") or "").strip()
            if not text:
                continue
            collected.append({"start": normalized["start"], "end": normalized["end"], "text": text})
        if collected:
            return collected

    return []


def _annotation_shift_intervals(
    record: Dict[str, Any], offset_sec: float
) -> Tuple[int, int]:
    """Add ``offset_sec`` to every interval's start/end. Negative values clamp to 0.

    Mutates the record in place. Intervals flagged ``manuallyAdjusted`` are
    skipped — once the annotator has locked a lexeme's timing (direct edit or
    a captured anchor pair) a later global shift must not move it again.

    Returns a tuple of ``(shifted, skipped_protected)``.
    """
    if not isinstance(record, dict):
        return 0, 0
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return 0, 0

    shifted = 0
    skipped_protected = 0
    for tier in tiers.values():
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals")
        if not isinstance(intervals, list):
            continue
        for raw in intervals:
            if not isinstance(raw, dict):
                continue
            start = _coerce_finite_float(raw.get("start", raw.get("xmin")))
            end = _coerce_finite_float(raw.get("end", raw.get("xmax")))
            if start is None or end is None:
                continue
            if bool(raw.get("manuallyAdjusted")):
                skipped_protected += 1
                continue
            new_start = max(0.0, float(start) + float(offset_sec))
            new_end = max(new_start, float(end) + float(offset_sec))
            raw["start"] = new_start
            raw["end"] = new_end
            if "xmin" in raw:
                raw["xmin"] = new_start
            if "xmax" in raw:
                raw["xmax"] = new_end
            shifted += 1
    _annotation_sort_all_intervals(record)
    return shifted, skipped_protected


def _stt_cache_path(speaker: str) -> pathlib.Path:
    return _project_root() / "coarse_transcripts" / "{0}.json".format(speaker)


def _write_stt_cache(speaker: str, source_wav: str, language: Optional[str], segments: List[Dict[str, Any]]) -> None:
    speaker_norm = str(speaker or "").strip()
    if not speaker_norm or not isinstance(segments, list) or not segments:
        return
    cache_path = _stt_cache_path(speaker_norm)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "speaker": speaker_norm,
            "source_wav": source_wav,
            "language": language,
            "segments": segments,
        }
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
    except OSError as exc:
        print("[stt] failed to cache segments for {0!r}: {1}".format(speaker_norm, exc), file=sys.stderr, flush=True)


def _read_stt_cache(speaker: str) -> Optional[List[Dict[str, Any]]]:
    cache_path = _stt_cache_path(speaker)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list) or not segments:
        return None
    return segments


def _latest_stt_segments_for_speaker(speaker: str) -> Optional[List[Dict[str, Any]]]:
    """Find the most recent completed STT job for ``speaker`` and return its segments.

    Prefers the current session's in-memory job. Falls back to the on-disk
    ``coarse_transcripts/<speaker>.json`` cache so actions like offset-detect
    still work after a server restart.
    """
    speaker_norm = str(speaker or "").strip()
    if not speaker_norm:
        return None
    candidates: List[Tuple[float, List[Dict[str, Any]]]] = []
    with _jobs_lock:
        for job in _jobs.values():
            if str(job.get("type") or "") != "stt":
                continue
            if str(job.get("status") or "") != "complete":
                continue
            meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
            if str(meta.get("speaker") or "") != speaker_norm:
                continue
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
            segments = result.get("segments")
            if not isinstance(segments, list) or not segments:
                continue
            ts = float(job.get("completed_ts") or job.get("updated_ts") or 0.0)
            candidates.append((ts, copy.deepcopy(segments)))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    return _read_stt_cache(speaker_norm)


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
        # Sidecar for the Lexical Anchor Alignment System — keyed by
        # concept_id. Kept outside the tiers block so it round-trips
        # through Praat/TextGrid cleanly (that format has no slot for
        # confidence or user-confirmation metadata).
        "confirmed_anchors": {},
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

    # Pass confirmed_anchors through verbatim when it's a well-formed dict.
    # Each entry is {start, end, source, confirmed_at, ...} keyed by concept id.
    raw_anchors = raw_record.get("confirmed_anchors")
    if isinstance(raw_anchors, dict):
        clean_anchors: Dict[str, Any] = {}
        for key, val in raw_anchors.items():
            if not isinstance(val, dict):
                continue
            start = _coerce_finite_float(val.get("start"))
            end = _coerce_finite_float(val.get("end"))
            if start is None or end is None or end < start:
                continue
            entry: Dict[str, Any] = {"start": float(start), "end": float(end)}
            for field in ("source", "confirmed_at", "matched_text", "matched_variant"):
                if field in val and val[field] is not None:
                    entry[field] = val[field]
            variants_used = val.get("variants_used")
            if isinstance(variants_used, list):
                entry["variants_used"] = [str(x) for x in variants_used]
            clean_anchors[str(key)] = entry
        normalized["confirmed_anchors"] = clean_anchors

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

    _launch_compute_runner(
        job_id, "stt",
        {"speaker": speaker, "sourceWav": source_wav, "language": language},
    )

    return job_id


def _chat_get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    return _get_job_snapshot(job_id)



def _chat_list_jobs(filters: Dict[str, Any]) -> Dict[str, Any]:
    filters_obj = dict(filters or {})
    rows = _list_jobs_snapshots(
        statuses=filters_obj.get("statuses") or [],
        job_types=filters_obj.get("types") or [],
        speaker=filters_obj.get("speaker"),
        limit=int(filters_obj.get("limit") or 100),
    )
    return {"jobs": rows, "count": len(rows)}



def _chat_get_job_logs(job_id: str, offset: int, limit: int) -> Dict[str, Any]:
    job = _get_job_snapshot(job_id)
    if job is None:
        return {"jobId": job_id, "count": 0, "offset": offset, "limit": limit, "logs": []}
    return _job_logs_payload(job, offset=offset, limit=limit)



def _job_callback_url_from_mapping(payload: Dict[str, Any]) -> Optional[str]:
    body_obj = payload if isinstance(payload, dict) else {}
    raw = body_obj.get("callbackUrl", body_obj.get("callback_url"))
    try:
        return _normalize_job_callback_url(raw)
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc



def _chat_pipeline_state(speaker: str) -> Dict[str, Any]:
    """Thin wrapper so ParseChatTools can reach the preflight probe."""
    return _pipeline_state_for_speaker(speaker)


# Set by the ``--compute-mode`` CLI flag in ``main()``. CLI beats env var
# because Windows python.exe launched via WSL interop does NOT inherit
# WSL-side env vars (confirmed 2026-04-23: ``PARSE_COMPUTE_MODE=subprocess
# python.exe server.py`` — inside the process, os.environ.get returns
# None for anything outside a small whitelist like HOME/PATH/USER).
# argv DOES propagate across the interop boundary, so the flag is the
# reliable way to pin the mode on that deployment.
_COMPUTE_MODE_OVERRIDE: Optional[str] = None


def _resolve_compute_mode() -> str:
    """Return the active compute mode — 'thread' (default), 'subprocess',
    or 'persistent'.

    Precedence:
      1. ``--compute-mode`` CLI flag (most explicit, survives WSL interop).
      2. ``PARSE_USE_PERSISTENT_WORKER=true`` (shortcut for the 2026-04
         persistent-worker rollout flag).
      3. ``PARSE_COMPUTE_MODE`` env var.
      4. Default ``'thread'`` (legacy behaviour).
    """
    if _COMPUTE_MODE_OVERRIDE:
        return _COMPUTE_MODE_OVERRIDE.strip().lower() or "thread"
    if str(os.environ.get("PARSE_USE_PERSISTENT_WORKER", "")).strip().lower() in {
        "1", "true", "yes", "on",
    }:
        return "persistent"
    env = os.environ.get("PARSE_COMPUTE_MODE", "").strip().lower()
    return env or "thread"


def _launch_compute_runner(job_id: str, compute_type: str, payload: Dict[str, Any]) -> None:
    """Start the backing worker for a compute job.

    Two modes, selected by ``--compute-mode`` CLI flag or
    ``PARSE_COMPUTE_MODE`` env var (CLI wins — env vars don't cross the
    WSL↔Windows python.exe boundary):

    - ``"thread"`` (default) — legacy behaviour. Spawns a
      ``threading.Thread`` that runs ``_run_compute_job`` in the same
      Python process as the HTTP server. Simple, works on Linux
      native, but wedges on Windows python.exe + WSL interop when the
      compute thread touches CUDA (observed 2026-04-23, see
      fix/compute-subprocess-runner).

    - ``"subprocess"`` — spawns a fresh Python process via
      ``multiprocessing.get_context("spawn")``. The child imports
      ``server``, runs the same ``_run_compute_job`` function, and
      writes its result to a temp JSON file. A monitor thread reads
      that file and updates the in-memory ``_jobs`` dict so status
      polls work unchanged. CUDA initialisation happens in the child,
      isolated from the HTTP server's address space — whatever
      threading quirk is causing the wedge can't reach us here. The
      trade-off is startup overhead (~1-3s per job to import + reload
      torch) which is negligible for multi-minute compute jobs.

    Env vars:
        PARSE_COMPUTE_MODE=subprocess — opt in to subprocess mode.
        PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC — hard kill deadline
            (default 4 hours; covers a razhan+wav2vec2 run on a
            multi-hour recording on CPU).
    """
    mode = _resolve_compute_mode()
    if mode == "persistent":
        _compute_checkpoint(
            "LAUNCH.persistent", job_id=job_id, compute_type=compute_type
        )
        _launch_compute_persistent(job_id, compute_type, payload)
        return
    if mode == "subprocess":
        _compute_checkpoint(
            "LAUNCH.subprocess", job_id=job_id, compute_type=compute_type
        )
        _launch_compute_subprocess(job_id, compute_type, payload)
        return
    _compute_checkpoint("LAUNCH.thread", job_id=job_id, compute_type=compute_type, mode=mode)
    thread = threading.Thread(
        target=_run_compute_job,
        args=(job_id, compute_type, payload),
        daemon=True,
    )
    thread.start()


def _launch_compute_subprocess(
    job_id: str, compute_type: str, payload: Dict[str, Any]
) -> None:
    """Spawn a child Python process to run the compute job.

    The child writes its outcome to ``/tmp/parse-compute-<job_id>.json``.
    A local monitor thread reads that file when the child exits and
    promotes the outcome to ``_set_job_complete`` / ``_set_job_error``
    so the existing HTTP status polling keeps working.

    Uses ``get_context("spawn")`` explicitly — on Windows python.exe
    this is the default but we name it so Linux native servers get
    the same isolation guarantees (fork would share torch state
    between parent and child, which is exactly the hazard we're
    trying to escape).
    """
    import multiprocessing
    import tempfile
    import json as _json

    result_path = os.path.join(
        tempfile.gettempdir(), "parse-compute-{0}.json".format(job_id)
    )
    try:
        if os.path.exists(result_path):
            os.remove(result_path)
    except OSError:
        pass

    checkpoint_path = _compute_checkpoint_path()

    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(
        target=_compute_subprocess_entry,
        name="parse-compute-{0}".format(compute_type),
        args=(job_id, compute_type, payload, result_path, checkpoint_path),
        daemon=True,
    )
    child.start()
    _compute_checkpoint(
        "SUBPROCESS.started", job_id=job_id, child_pid=child.pid, result_path=result_path
    )

    try:
        timeout_raw = os.environ.get("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "14400")
        timeout_sec = max(60.0, float(timeout_raw))
    except ValueError:
        timeout_sec = 14400.0

    def _monitor() -> None:
        child.join(timeout=timeout_sec)
        if child.is_alive():
            _compute_checkpoint(
                "SUBPROCESS.timeout", job_id=job_id, pid=child.pid, timeout=timeout_sec
            )
            try:
                child.terminate()
                child.join(timeout=10.0)
            except Exception:
                pass
            _set_job_error(
                job_id,
                "Compute subprocess exceeded PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC ({0}s) and was terminated.".format(
                    int(timeout_sec)
                ),
            )
            return

        exit_code = child.exitcode
        _compute_checkpoint(
            "SUBPROCESS.exited", job_id=job_id, exit_code=exit_code
        )

        if not os.path.exists(result_path):
            _set_job_error(
                job_id,
                "Compute subprocess exited code={0} without writing result file {1}".format(
                    exit_code, result_path
                ),
            )
            return

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                payload_out = _json.load(f)
        except Exception as exc:
            _set_job_error(
                job_id,
                "Compute subprocess result file unreadable: {0}".format(exc),
            )
            return
        finally:
            try:
                os.remove(result_path)
            except OSError:
                pass

        ok = bool(payload_out.get("ok"))
        if ok:
            _set_job_complete(
                job_id,
                payload_out.get("result"),
                message="Compute subprocess complete",
            )
        else:
            err = str(payload_out.get("error") or "Compute subprocess reported failure")
            tb = str(payload_out.get("traceback") or "") or None
            _set_job_error(job_id, err, traceback_str=tb)

    monitor = threading.Thread(
        target=_monitor,
        name="parse-compute-monitor-{0}".format(job_id),
        daemon=True,
    )
    monitor.start()


def _compute_subprocess_entry(
    job_id: str,
    compute_type: str,
    payload: Dict[str, Any],
    result_path: str,
    checkpoint_path: str,
) -> None:
    """Runs in a fresh Python process.

    Imports the server module to reuse every compute function and
    its dependency graph, then writes a JSON outcome to ``result_path``.
    Any import-time / compute-time failure is captured as
    ``{ok: False, error, traceback}``.

    The child writes to the shared ``checkpoint_path`` (same buffer-
    free file the parent uses) so we get a continuous per-stage log
    across process boundaries. Pipe buffering can't hide it — the
    file is append-only + fsync'd per write on both sides.
    """
    import json as _json
    import traceback as _tb

    # Redirect child stderr into a dedicated file so torch/CUDA init
    # noise doesn't pollute the parent's log, and so the child's own
    # crashes can be post-mortemed independently.
    try:
        child_stderr = open(
            "/tmp/parse-compute-{0}.stderr.log".format(job_id),
            "w",
            encoding="utf-8",
        )
        sys.stderr = child_stderr
    except Exception:
        pass

    # Re-use the parent's checkpoint file path so MAIN and CHILD
    # entries interleave in one timeline. The parent's
    # ``_compute_checkpoint`` writes via module-level fd caching; the
    # child's module is a fresh import so its own fd cache is
    # independent — which is actually what we want (two writers, one
    # file, both with O_APPEND).
    os.environ["PARSE_COMPUTE_CHECKPOINT_LOG"] = checkpoint_path

    outcome: Dict[str, Any] = {"ok": False}
    try:
        # Imports happen here, AFTER spawn, so the CUDA init is
        # guaranteed to be in THIS process's context, not inherited.
        import server as _server  # noqa: F401

        _compute_checkpoint("CHILD.entry", job_id=job_id, compute_type=compute_type)

        # Run the compute synchronously on the main thread of this
        # child process. ``_run_compute_job`` writes to the parent's
        # ``_jobs`` dict via in-module functions, but in the child those
        # calls target the child's own (separate) ``_jobs`` dict — a
        # harmless no-op. We don't read from that dict in the child;
        # we only care about the return value of the compute function,
        # which we reconstruct by calling the function directly rather
        # than via ``_run_compute_job``.
        normalized_type = str(compute_type or "").strip().lower()
        if normalized_type in {"cognates", "similarity"}:
            result = _server._compute_cognates("child-{0}".format(job_id), payload)
        elif normalized_type == "contact-lexemes":
            result = _server._compute_contact_lexemes("child-{0}".format(job_id), payload)
        elif normalized_type in {"ipa_only", "ipa-only", "ipa"}:
            result = _server._compute_speaker_ipa("child-{0}".format(job_id), payload)
        elif normalized_type in {"ortho", "ortho_only", "ortho-only"}:
            result = _server._compute_speaker_ortho("child-{0}".format(job_id), payload)
        elif normalized_type in {"forced_align", "forced-align", "align"}:
            result = _server._compute_speaker_forced_align(
                "child-{0}".format(job_id), payload
            )
        elif normalized_type in {"full_pipeline", "full-pipeline", "pipeline"}:
            result = _server._compute_full_pipeline("child-{0}".format(job_id), payload)
        elif normalized_type in {"train_ipa_model", "train-ipa-model", "train_ipa"}:
            result = _server._compute_training_job("child-{0}".format(job_id), payload)
        elif normalized_type == "stt":
            result = _server._compute_stt("child-{0}".format(job_id), payload)
        elif normalized_type in {"offset_detect", "offset-detect"}:
            result = _server._compute_offset_detect("child-{0}".format(job_id), payload)
        elif normalized_type in {"offset_detect_from_pair", "offset-detect-from-pair"}:
            result = _server._compute_offset_detect_from_pair("child-{0}".format(job_id), payload)
        else:
            raise RuntimeError("Unsupported compute type: {0}".format(normalized_type))

        _compute_checkpoint("CHILD.ok", job_id=job_id)
        outcome = {"ok": True, "result": result}
    except Exception as exc:
        _compute_checkpoint(
            "CHILD.exc", job_id=job_id, exc_type=type(exc).__name__, exc=str(exc)[:200]
        )
        outcome = {
            "ok": False,
            "error": str(exc),
            "traceback": _tb.format_exc(),
        }

    try:
        with open(result_path, "w", encoding="utf-8") as f:
            _json.dump(outcome, f, ensure_ascii=False, default=str)
    except Exception as exc:
        _compute_checkpoint(
            "CHILD.result_write_failed",
            job_id=job_id,
            exc=str(exc)[:200],
        )


# ---------------------------------------------------------------------------
# Persistent compute worker (one long-lived process for all compute jobs)
# ---------------------------------------------------------------------------
#
# Eliminates the per-job Aligner.load() that repeated ``subprocess`` mode
# pays and the CUDA-context-in-HTTP-thread hazard that ``thread`` mode
# pays. See ``python/workers/compute_worker.py`` for the worker body.
#
# Feature flag: --compute-mode=persistent  or  PARSE_USE_PERSISTENT_WORKER=true.
# Default is ``thread`` — rollout plan is to validate on a small speaker,
# then Fail02, then flip the PM2 default.

_PERSISTENT_WORKER_HANDLE: Optional[Any] = None
_PERSISTENT_WORKER_LOCK = threading.Lock()


def _start_persistent_worker() -> bool:
    """Start the single long-lived compute worker process.

    Returns True on success. Called exactly once from ``main()`` when
    the resolved compute mode is ``persistent``. On failure the caller
    should refuse to boot rather than silently drop back to threads —
    the operator explicitly asked for persistent.
    """
    global _PERSISTENT_WORKER_HANDLE
    # Late import so non-persistent modes don't pay the package cost.
    from workers.compute_worker import WorkerHandle

    with _PERSISTENT_WORKER_LOCK:
        if (
            _PERSISTENT_WORKER_HANDLE is not None
            and _PERSISTENT_WORKER_HANDLE.is_alive()
        ):
            return True
        handle = WorkerHandle(
            on_progress=_set_job_progress,
            on_complete=_set_job_complete,
            on_error=_set_job_error,
        )
        started = handle.start(ready_timeout=180.0)
        if not started:
            return False
        _PERSISTENT_WORKER_HANDLE = handle

    import atexit
    atexit.register(_shutdown_persistent_worker)
    return True


def _shutdown_persistent_worker() -> None:
    global _PERSISTENT_WORKER_HANDLE
    with _PERSISTENT_WORKER_LOCK:
        handle = _PERSISTENT_WORKER_HANDLE
        _PERSISTENT_WORKER_HANDLE = None
    if handle is not None:
        try:
            handle.shutdown(timeout=10.0)
        except Exception:
            pass


def _launch_compute_persistent(
    job_id: str, compute_type: str, payload: Dict[str, Any]
) -> None:
    handle = _PERSISTENT_WORKER_HANDLE
    if handle is None or not handle.is_alive():
        _set_job_error(
            job_id,
            "Persistent compute worker is not running. Restart the server.",
        )
        return
    handle.submit(job_id, compute_type, payload)


def _chat_start_compute_job(compute_type: str, payload: Dict[str, Any]) -> str:
    """Start a compute job and return its jobId.

    Backs both the Tier 2/3 acoustic-alignment tools
    (``forced_align`` / ``ipa_only``) and the pipeline-run tool
    (``full_pipeline``). Mirrors ``_api_post_compute_start`` without the
    HTTP layer so chat-tool / MCP callers get the same behaviour as the
    REST client: ``full_pipeline`` runs step-resilient, records per-step
    tracebacks, and the returned jobId is pollable via
    ``_get_job_snapshot``. The job type is recorded as
    ``compute:<type>`` so ``compute_status`` and
    ``_generic_compute_status`` can filter by compute-type suffix.
    """
    normalized_type = str(compute_type or "").strip().lower()
    if not normalized_type:
        raise ValueError("compute_type is required")

    body_obj = dict(payload or {})
    speaker = str(body_obj.get("speaker") or "").strip() or None
    job_metadata = {
        "computeType": normalized_type,
        "payload": body_obj,
        "origin": "chat_tool",
    }
    if speaker:
        job_metadata["speaker"] = speaker
    job_id = _create_job(
        "compute:{0}".format(normalized_type),
        job_metadata,
    )
    # Delegates to thread / subprocess depending on PARSE_COMPUTE_MODE.
    _launch_compute_runner(job_id, normalized_type, body_obj)
    return job_id


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
        # Preserve wildcard tokens as-is so ParseChatTools.__init__ can detect them.
        if piece in {"*", "**", "/"}:
            roots.append(pathlib.Path(piece))
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
                list_jobs=_chat_list_jobs,
                get_job_logs=_chat_get_job_logs,
                external_read_roots=_chat_external_read_roots(),
                memory_path=_chat_memory_path(),
                onboard_speaker=_chat_onboard_speaker,
                start_compute_job=_chat_start_compute_job,
                pipeline_state=_chat_pipeline_state,
            )

        if _chat_orchestrator_runtime is None:
            _chat_orchestrator_runtime = ChatOrchestrator(
                project_root=_project_root(),
                tools=_chat_tools_runtime,
                config_path=_config_path(),
            )

        return _chat_tools_runtime, _chat_orchestrator_runtime


def _build_workflow_runtime() -> WorkflowTools:
    return WorkflowTools(
        project_root=_project_root(),
        config_path=_config_path(),
        docs_root=_chat_docs_root(),
        start_stt_job=_chat_start_stt_job,
        get_job_snapshot=_chat_get_job_snapshot,
        external_read_roots=_chat_external_read_roots(),
        memory_path=_chat_memory_path(),
        onboard_speaker=_chat_onboard_speaker,
        start_compute_job=_chat_start_compute_job,
        pipeline_state=_chat_pipeline_state,
    )


def _execute_mcp_http_tool(tool_name: str, raw_args: Dict[str, Any], mode: str = "active") -> Dict[str, Any]:
    if not isinstance(raw_args, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "Tool arguments must be a JSON object")

    parse_tools, _ = _get_chat_runtime()
    workflow_tools = _build_workflow_runtime()
    tool_entry = get_mcp_tool_entry(
        tool_name,
        project_root=_project_root(),
        mode=mode,
        parse_tools=parse_tools,
        workflow_tools=workflow_tools,
    )
    if tool_entry is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "Unknown MCP tool: {0}".format(tool_name))

    family = str(tool_entry.get("family") or "chat")
    try:
        if family == "adapter" and tool_name == "mcp_get_exposure_mode":
            catalog = build_mcp_http_catalog(
                project_root=_project_root(),
                mode=mode,
                parse_tools=parse_tools,
                workflow_tools=workflow_tools,
            )
            return mcp_exposure_payload(
                expose_all_tools=bool(catalog["exposure"].get("exposeAllTools", False)),
                config_source=catalog["exposure"].get("configSource"),
                parse_chat_tool_count=int(catalog["exposure"].get("parseChatToolCount", len(parse_tools.tool_names()))),
                workflow_tool_count=int(catalog["exposure"].get("workflowToolCount", 0)),
                mcp_tool_count=int(catalog["exposure"].get("mcpToolCount", catalog.get("count", 0))),
            )
        if family == "workflow":
            return workflow_tools.execute(tool_name, raw_args)
        return parse_tools.execute(tool_name, raw_args)
    except (ChatToolValidationError, ChatToolExecutionError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc


def _run_chat_job(job_id: str, session_id: str) -> None:
    try:
        _set_job_progress(job_id, 5.0, message="Preparing chat context")

        session_snapshot = _chat_get_session_snapshot(session_id)
        if session_snapshot is None:
            raise RuntimeError("Unknown chat session: {0}".format(session_id))

        _set_job_progress(job_id, 20.0, message="Running chat orchestration")
        _, orchestrator = _get_chat_runtime()

        def _tool_progress(tool_name: str) -> None:
            _set_job_progress(job_id, 20.0, message="Running: {0}".format(tool_name))

        result = orchestrator.run(
            session_id=session_id,
            session_messages=session_snapshot.get("messages", []),
            on_tool_call=_tool_progress,
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


def _job_log_limit() -> int:
    raw = str(os.environ.get("PARSE_JOB_LOG_MAX_ENTRIES") or "").strip()
    if raw:
        try:
            parsed = int(raw)
        except ValueError:
            parsed = JOB_LOG_MAX_ENTRIES
        return max(10, min(parsed, 1000))
    return JOB_LOG_MAX_ENTRIES



def _infer_job_error_code(error_message: Any) -> str:
    text = str(error_message or "").strip().lower()
    if not text:
        return "job_failed"
    if "unknown jobid" in text or "unknown job_id" in text:
        return "job_not_found"
    if "not a" in text and "job" in text:
        return "invalid_job_type"
    if "timeout" in text:
        return "timeout"
    if "ffmpeg" in text:
        return "ffmpeg_failed"
    if "provider init failed" in text or "loading model" in text:
        return "model_init_failed"
    if "cuda" in text or "cublas" in text:
        return "cuda_runtime_error"
    if "validation" in text or "required" in text:
        return "validation_error"
    return "job_failed"



def _job_log_entry(
    *,
    level: str,
    event: str,
    message: str,
    source: str = "job_registry",
    progress: Optional[float] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "ts": _utc_now_iso(),
        "level": str(level or "info"),
        "event": str(event or "job.event"),
        "message": str(message or ""),
        "source": str(source or "job_registry"),
    }
    if progress is not None:
        entry["progress"] = _clamp_progress(progress)
    if isinstance(data, dict) and data:
        entry["data"] = copy.deepcopy(data)
    return entry



def _append_job_log_locked(
    job: Dict[str, Any],
    *,
    level: str,
    event: str,
    message: str,
    source: str = "server",
    progress: Optional[float] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    logs = job.get("logs")
    if not isinstance(logs, list):
        logs = []
        job["logs"] = logs
    logs.append(
        _job_log_entry(
            level=level,
            event=event,
            message=message,
            source=source,
            progress=progress,
            data=data,
        )
    )
    log_limit = _job_log_limit()
    if len(logs) > log_limit:
        del logs[:-log_limit]


_MUTATING_SPEAKER_JOB_TYPES = frozenset({"normalize", "stt", "onboard:speaker"})
_MUTATING_SPEAKER_COMPUTE_TYPES = frozenset(
    {"stt", "ortho", "ortho_only", "ipa", "ipa_only", "forced_align", "full_pipeline"}
)



def _job_lock_resources(job_type: str, metadata: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    meta = metadata if isinstance(metadata, dict) else {}
    speaker = str(meta.get("speaker") or "").strip()
    if not speaker:
        return []

    normalized_job_type = str(job_type or "").strip().lower()
    if normalized_job_type in _MUTATING_SPEAKER_JOB_TYPES:
        return [{"kind": "speaker", "id": speaker}]

    if normalized_job_type.startswith("compute:"):
        compute_type = str(meta.get("computeType") or normalized_job_type.split(":", 1)[1] or "").strip().lower()
        if compute_type in _MUTATING_SPEAKER_COMPUTE_TYPES:
            return [{"kind": "speaker", "id": speaker}]

    return []



def _expire_job_locks_locked(job: Dict[str, Any], now_ts: float, *, reason: str = "ttl_expired") -> None:
    locks = job.get("locks")
    if not isinstance(locks, dict) or not locks.get("active"):
        return
    locks["active"] = False
    locks["expires_at"] = None
    locks["expires_ts"] = None
    locks["released_at"] = _utc_iso_from_ts(now_ts)
    locks["released_ts"] = now_ts
    locks["released_reason"] = reason



def _find_job_resource_conflict_locked(
    resources: Sequence[Dict[str, str]],
    *,
    now_ts: float,
) -> Optional[Tuple[Dict[str, Any], Dict[str, str]]]:
    wanted = {
        (str(resource.get("kind") or "").strip(), str(resource.get("id") or "").strip())
        for resource in resources
        if str(resource.get("kind") or "").strip() and str(resource.get("id") or "").strip()
    }
    if not wanted:
        return None

    for job in _jobs.values():
        if str(job.get("status") or "").strip().lower() not in {"queued", "running"}:
            continue
        locks = job.get("locks")
        if not isinstance(locks, dict) or not locks.get("active"):
            continue
        try:
            expires_ts = float(locks.get("expires_ts") or 0.0)
        except (TypeError, ValueError):
            expires_ts = 0.0
        if expires_ts and expires_ts <= now_ts:
            _expire_job_locks_locked(job, now_ts)
            continue
        for resource in locks.get("resources") or []:
            resource_kind = str(resource.get("kind") or "").strip()
            resource_id = str(resource.get("id") or "").strip()
            if (resource_kind, resource_id) in wanted:
                return job, {"kind": resource_kind, "id": resource_id}
    return None



def _refresh_job_locks_locked(job: Dict[str, Any], now_ts: float) -> None:
    locks = job.get("locks")
    if not isinstance(locks, dict) or not locks.get("active"):
        return
    ttl_seconds = max(1, int(locks.get("ttl_seconds") or JOB_LOCK_TTL_SECONDS))
    locks["heartbeat_at"] = _utc_iso_from_ts(now_ts)
    locks["heartbeat_ts"] = now_ts
    locks["expires_at"] = _utc_iso_from_ts(now_ts + ttl_seconds)
    locks["expires_ts"] = now_ts + ttl_seconds



def _release_job_locks_locked(job: Dict[str, Any], now_ts: float) -> None:
    locks = job.get("locks")
    if not isinstance(locks, dict) or not locks.get("active"):
        return
    resources = copy.deepcopy(locks.get("resources") or [])
    locks["active"] = False
    locks["expires_at"] = None
    locks["expires_ts"] = None
    locks["released_at"] = _utc_iso_from_ts(now_ts)
    locks["released_ts"] = now_ts
    locks["released_reason"] = "job_finished"
    if resources:
        _append_job_log_locked(
            job,
            level="info",
            event="job.lock_released",
            message="Released job resource lock",
            progress=_clamp_progress(job.get("progress", 0.0)),
            data={"resources": resources},
        )



def _job_locks_payload(locks: Any) -> Dict[str, Any]:
    locks_dict = locks if isinstance(locks, dict) else {}
    resources = locks_dict.get("resources") if isinstance(locks_dict.get("resources"), list) else []
    return {
        "active": bool(locks_dict.get("active")),
        "resources": copy.deepcopy(resources),
        "heartbeat_at": locks_dict.get("heartbeat_at"),
        "expires_at": locks_dict.get("expires_at"),
        "released_at": locks_dict.get("released_at"),
        "released_reason": locks_dict.get("released_reason"),
        "ttl_seconds": int(locks_dict.get("ttl_seconds") or JOB_LOCK_TTL_SECONDS),
    }



def _normalize_job_callback_url(raw_value: Any) -> Optional[str]:
    value = str(raw_value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("callbackUrl must be an absolute http(s) URL")
    return value



def _job_callback_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = _job_detail_payload(job, include_logs=False)
    payload["event"] = "job.{0}".format(str(job.get("status") or "unknown"))
    return payload



def _post_job_callback(callback_url: str, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        callback_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "PARSE-Job-Callback/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=10.0) as response:
        response.read()



def _dispatch_job_callback(job_snapshot: Dict[str, Any]) -> None:
    meta = job_snapshot.get("meta") if isinstance(job_snapshot.get("meta"), dict) else {}
    callback_url = str(meta.get("callbackUrl") or "").strip()
    if not callback_url:
        return
    try:
        _post_job_callback(callback_url, _job_callback_payload(job_snapshot))
    except Exception as exc:
        job_id = str(job_snapshot.get("jobId") or "")
        with _jobs_lock:
            live_job = _jobs.get(job_id)
            if live_job is not None:
                _append_job_log_locked(
                    live_job,
                    level="error",
                    event="job.callback_failed",
                    message="Callback delivery failed: {0}".format(exc),
                    progress=_clamp_progress(live_job.get("progress", 0.0)),
                    data={"callbackUrl": callback_url},
                )



def _dispatch_job_callback_async(job_snapshot: Dict[str, Any]) -> None:
    meta = job_snapshot.get("meta") if isinstance(job_snapshot.get("meta"), dict) else {}
    callback_url = str(meta.get("callbackUrl") or "").strip()
    if not callback_url:
        return
    thread = threading.Thread(target=_dispatch_job_callback, args=(copy.deepcopy(job_snapshot),), daemon=True)
    thread.start()



def _create_job(
    job_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    initial_status: str = "running",
) -> str:
    _cleanup_old_jobs()

    job_id = str(uuid.uuid4())
    now_ts = time.time()
    now_iso = _utc_now_iso()
    normalized_status = str(initial_status or "running").strip().lower() or "running"
    if normalized_status not in {"queued", "running"}:
        normalized_status = "running"
    resources = _job_lock_resources(job_type, metadata)

    with _jobs_lock:
        conflict = _find_job_resource_conflict_locked(resources, now_ts=now_ts)
        if conflict is not None:
            holder_job, resource = conflict
            raise JobResourceConflictError(
                resource_kind=str(resource.get("kind") or "resource"),
                resource_id=str(resource.get("id") or ""),
                holder_job_id=str(holder_job.get("jobId") or ""),
                holder_job_type=str(holder_job.get("type") or "unknown"),
                holder_status=str(holder_job.get("status") or "running"),
            )

        locks_payload = {
            "active": bool(resources),
            "resources": copy.deepcopy(resources),
            "heartbeat_at": None,
            "heartbeat_ts": None,
            "expires_at": None,
            "expires_ts": None,
            "released_at": None,
            "released_ts": None,
            "released_reason": None,
            "ttl_seconds": JOB_LOCK_TTL_SECONDS,
        }
        if resources:
            locks_payload["heartbeat_at"] = now_iso
            locks_payload["heartbeat_ts"] = now_ts
            locks_payload["expires_at"] = _utc_iso_from_ts(now_ts + JOB_LOCK_TTL_SECONDS)
            locks_payload["expires_ts"] = now_ts + JOB_LOCK_TTL_SECONDS

        job: Dict[str, Any] = {
            "jobId": job_id,
            "type": str(job_type),
            "status": normalized_status,
            "progress": 0.0,
            "result": None,
            "error": None,
            "error_code": None,
            "message": None,
            "segmentsProcessed": 0,
            "totalSegments": 0,
            "created_at": now_iso,
            "updated_at": now_iso,
            "completed_at": None,
            "created_ts": now_ts,
            "updated_ts": now_ts,
            "completed_ts": None,
            "meta": copy.deepcopy(metadata or {}),
            "locks": locks_payload,
            "logs": [],
        }
        _append_job_log_locked(
            job,
            level="info",
            event="job.queued" if normalized_status == "queued" else "job.created",
            message="Job queued" if normalized_status == "queued" else "Job created",
            progress=0.0,
            data={
                "jobId": job_id,
                "type": str(job_type),
                "meta": copy.deepcopy(metadata or {}),
            },
        )
        if resources:
            _append_job_log_locked(
                job,
                level="info",
                event="job.lock_acquired",
                message="Acquired job resource lock",
                progress=0.0,
                data={"resources": copy.deepcopy(resources)},
            )
        _jobs[job_id] = job

    return job_id


# ---------------------------------------------------------------------------
# Compute-checkpoint log (buffer-free, for Windows-python.exe hang diagnosis)
# ---------------------------------------------------------------------------
#
# Symptom: when ``_compute_speaker_ipa`` runs in a threaded job under
# Windows python.exe via WSL, the process wedges mid-function. stderr
# shows only the first print; subsequent prints never land in the log
# even with ``flush=True``. Hypothesis: the redirection pipe
# ``python.exe 2> /tmp/parse_api_stderr.log`` goes through Windows's
# stream buffer, and ``sys.stderr.flush()`` only flushes Python's
# internal buffer — the OS pipe buffer can still hold kilobytes that
# never reach disk if the process stops writing.
#
# This checkpoint logger bypasses stderr/pipe entirely: it opens a
# dedicated log file with O_APPEND|O_CREAT, writes each line with
# ``os.write`` (no Python-level buffering), and calls ``os.fsync`` to
# force the kernel to flush to disk. If the process hangs after
# checkpoint N but before N+1, we know exactly which call line is at
# fault — regardless of pipe buffering.
#
# Log file: PARSE_COMPUTE_CHECKPOINT_LOG (env) or /tmp/parse_compute_checkpoint.log
# Format: ISO8601 UTC \t thread_name \t pid \t label \t key=value ...
#
# Cheap enough to call every few lines: one syscall pair per checkpoint.
# Log is append-only; caller can ``> file`` to truncate between runs.

_COMPUTE_CHECKPOINT_LOG_PATH: Optional[str] = None
_COMPUTE_CHECKPOINT_FD: Optional[int] = None
_COMPUTE_CHECKPOINT_LOCK = threading.Lock()


def _tail_log_file(path: str, max_lines: int = 200, max_bytes: int = 256 * 1024) -> Optional[str]:
    """Return the last ``max_lines`` lines of ``path``, capped at ``max_bytes``.

    Best-effort: returns None if the file is missing, unreadable, or empty.
    Used by ``_api_get_job_logs`` to surface worker stderr tails without
    pulling the whole file. Bytes cap protects against a multi-MB log
    ending up in a JSON response body.
    """
    try:
        with open(path, "rb") as fh:
            try:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
            except OSError:
                size = 0
            if size <= 0:
                return None
            start = max(0, size - max_bytes)
            fh.seek(start)
            chunk = fh.read()
    except (OSError, FileNotFoundError):
        return None
    if not chunk:
        return None
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines) if lines else None


def _compute_checkpoint_path() -> str:
    global _COMPUTE_CHECKPOINT_LOG_PATH
    if _COMPUTE_CHECKPOINT_LOG_PATH is None:
        raw = os.environ.get("PARSE_COMPUTE_CHECKPOINT_LOG", "").strip()
        _COMPUTE_CHECKPOINT_LOG_PATH = raw or "/tmp/parse_compute_checkpoint.log"
    return _COMPUTE_CHECKPOINT_LOG_PATH


def _compute_checkpoint(label: str, **kv: Any) -> None:
    """Append one buffer-free checkpoint line.

    Safe to call from any thread. Each call:
      1. Serialises under ``_COMPUTE_CHECKPOINT_LOCK`` so interleaved
         writes from the HTTP thread + compute thread don't tear lines.
      2. Opens the fd on first use (one-shot per process), reuses it
         after. The fd is never closed — OS cleans up on exit.
      3. Writes the formatted line via ``os.write`` then ``os.fsync``.
         fsync is the point — if the process wedges 100ms after
         returning from here, the line is already durable on disk.
    """
    try:
        global _COMPUTE_CHECKPOINT_FD
        path = _compute_checkpoint_path()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        thread_name = threading.current_thread().name
        pid = os.getpid()
        parts = [now, thread_name, str(pid), label]
        for key, value in kv.items():
            try:
                parts.append("{0}={1}".format(key, value))
            except Exception:
                parts.append("{0}=?".format(key))
        line = ("\t".join(parts) + "\n").encode("utf-8", errors="replace")

        with _COMPUTE_CHECKPOINT_LOCK:
            if _COMPUTE_CHECKPOINT_FD is None:
                _COMPUTE_CHECKPOINT_FD = os.open(
                    path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644
                )
            os.write(_COMPUTE_CHECKPOINT_FD, line)
            try:
                os.fsync(_COMPUTE_CHECKPOINT_FD)
            except OSError:
                # On some platforms fsync on an appended pipe-like FD
                # raises; the write itself already went through.
                pass
    except Exception:
        # Checkpointing MUST NOT ever raise back into the compute path.
        # If the log file is unreachable the compute continues.
        pass

def _set_job_running(job_id: str, message: Optional[str] = None) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        if str(job.get("status") or "") == "running":
            return
        now_ts = time.time()
        job["status"] = "running"
        job["updated_at"] = _utc_iso_from_ts(now_ts)
        job["updated_ts"] = now_ts
        _refresh_job_locks_locked(job, now_ts)
        if message is not None:
            job["message"] = str(message)
        _append_job_log_locked(
            job,
            level="info",
            event="job.started",
            message=str(job.get("message") or message or "Job started"),
            progress=_clamp_progress(job.get("progress", 0.0)),
        )



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
        previous_message = str(job.get("message") or "")
        previous_progress = _clamp_progress(job.get("progress", 0.0))
        current_progress = _clamp_progress(progress)
        job["progress"] = current_progress
        job["updated_at"] = _utc_iso_from_ts(now_ts)
        job["updated_ts"] = now_ts
        _refresh_job_locks_locked(job, now_ts)

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

        current_message = str(job.get("message") or "")
        if current_message and current_message != previous_message:
            _append_job_log_locked(
                job,
                level="info",
                event="job.progress",
                message=current_message,
                progress=current_progress,
                data={
                    "segmentsProcessed": int(job.get("segmentsProcessed", 0) or 0),
                    "totalSegments": int(job.get("totalSegments", 0) or 0),
                },
            )
        elif current_progress != previous_progress and abs(current_progress - previous_progress) >= 25.0:
            _append_job_log_locked(
                job,
                level="info",
                event="job.progress",
                message="Progress updated",
                progress=current_progress,
            )



def _set_job_complete(
    job_id: str,
    result: Any,
    message: Optional[str] = None,
    segments_processed: Optional[int] = None,
    total_segments: Optional[int] = None,
) -> None:
    callback_snapshot: Optional[Dict[str, Any]] = None
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return

        now_ts = time.time()
        now_iso = _utc_iso_from_ts(now_ts)
        job["status"] = "complete"
        job["progress"] = 100.0
        job["result"] = copy.deepcopy(result)
        job["error"] = None
        job["error_code"] = None
        job["updated_at"] = now_iso
        job["updated_ts"] = now_ts
        job["completed_at"] = now_iso
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
        _release_job_locks_locked(job, now_ts)
        _append_job_log_locked(
            job,
            level="info",
            event="job.completed",
            message=str(job.get("message") or "Job complete"),
            progress=100.0,
        )
        callback_snapshot = copy.deepcopy(job)

    if callback_snapshot is not None:
        _dispatch_job_callback_async(callback_snapshot)



def _set_job_error(
    job_id: str,
    error_message: str,
    traceback_str: Optional[str] = None,
) -> None:
    """Mark a job as errored. ``traceback_str`` is stored separately from
    the short error message so the UI's crash-log modal can render the
    one-line reason on top and the full Python traceback below without
    having to split-on-newline."""
    callback_snapshot: Optional[Dict[str, Any]] = None
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return

        now_ts = time.time()
        now_iso = _utc_iso_from_ts(now_ts)
        job["status"] = "error"
        job["error"] = str(error_message)
        if traceback_str:
            job["traceback"] = str(traceback_str)
        job["error_code"] = _infer_job_error_code(error_message)
        job["updated_at"] = now_iso
        job["updated_ts"] = now_ts
        job["completed_at"] = now_iso
        job["completed_ts"] = now_ts
        _release_job_locks_locked(job, now_ts)
        _append_job_log_locked(
            job,
            level="error",
            event="job.failed",
            message=str(error_message),
            progress=_clamp_progress(job.get("progress", 0.0)),
        )
        callback_snapshot = copy.deepcopy(job)

    if callback_snapshot is not None:
        _dispatch_job_callback_async(callback_snapshot)

def _get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return copy.deepcopy(job)



def _job_logs_payload(job: Dict[str, Any], *, offset: int = 0, limit: int = JOB_LOG_MAX_ENTRIES) -> Dict[str, Any]:
    logs = job.get("logs") if isinstance(job.get("logs"), list) else []
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(int(limit or _job_log_limit()), _job_log_limit()))
    sliced = copy.deepcopy(logs[safe_offset:safe_offset + safe_limit])
    return {
        "jobId": str(job.get("jobId") or ""),
        "count": len(logs),
        "offset": safe_offset,
        "limit": safe_limit,
        "logs": sliced,
    }



def _job_detail_payload(job: Dict[str, Any], *, include_logs: bool = False) -> Dict[str, Any]:
    payload = _job_response_payload(job)
    payload["createdAt"] = job.get("created_at")
    payload["updatedAt"] = job.get("updated_at")
    payload["completedAt"] = job.get("completed_at")
    payload["meta"] = copy.deepcopy(job.get("meta") if isinstance(job.get("meta"), dict) else {})
    payload["locks"] = _job_locks_payload(job.get("locks"))
    logs = job.get("logs") if isinstance(job.get("logs"), list) else []
    payload["logCount"] = len(logs)
    if include_logs:
        payload["logs"] = copy.deepcopy(logs)
    return payload



def _list_jobs_snapshots(
    *,
    statuses: Optional[Sequence[str]] = None,
    job_types: Optional[Sequence[str]] = None,
    speaker: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    normalized_statuses = {
        str(value or "").strip().lower()
        for value in (statuses or [])
        if str(value or "").strip()
    }
    normalized_types = {
        str(value or "").strip()
        for value in (job_types or [])
        if str(value or "").strip()
    }
    speaker_filter = str(speaker or "").strip()
    safe_limit = max(1, min(int(limit or 100), 500))

    rows: List[Dict[str, Any]] = []
    with _jobs_lock:
        jobs_sorted = sorted(
            _jobs.values(),
            key=lambda item: float(item.get("created_ts") or 0.0),
            reverse=True,
        )
        for job in jobs_sorted:
            job_status = str(job.get("status") or "").strip().lower()
            if normalized_statuses and job_status not in normalized_statuses:
                continue
            job_type = str(job.get("type") or "").strip()
            if normalized_types and job_type not in normalized_types:
                continue
            meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
            if speaker_filter and str(meta.get("speaker") or "").strip() != speaker_filter:
                continue
            rows.append(_job_detail_payload(job))
            if len(rows) >= safe_limit:
                break
    return rows



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
    if job.get("traceback"):
        payload["traceback"] = str(job.get("traceback"))

    payload["segmentsProcessed"] = int(job.get("segmentsProcessed", 0) or 0)
    payload["totalSegments"] = int(job.get("totalSegments", 0) or 0)
    payload["locks"] = _job_locks_payload(job.get("locks"))
    if job.get("error_code"):
        payload["errorCode"] = str(job.get("error_code"))

    if job_type == "chat:run":
        payload["runId"] = job_id
        payload.update(_chat_public_policy_payload())

    done = status in {"complete", "error"}
    payload["done"] = done
    payload["success"] = status == "complete"
    return payload


def _list_active_jobs_snapshots() -> List[Dict[str, Any]]:
    """Return public snapshots for all currently-running jobs.

    Used by the frontend on page load to rehydrate in-flight progress bars
    (STT, normalize, IPA, etc.) after a reload — backend threads outlive the
    browser, so the job is still running; the UI just lost its ``job_id``.
    """
    results: List[Dict[str, Any]] = []
    with _jobs_lock:
        for job in _jobs.values():
            if job.get("status") != "running":
                continue
            payload = _job_response_payload(job)
            meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
            if isinstance(meta, dict) and meta:
                # Only surface safe metadata the UI already has access to:
                # speaker identifies which hook should adopt this job.
                speaker = meta.get("speaker")
                if isinstance(speaker, str) and speaker.strip():
                    payload["speaker"] = speaker.strip()
                language = meta.get("language")
                if isinstance(language, str) and language.strip():
                    payload["language"] = language.strip()
            results.append(payload)
    return results



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


def _run_stt_job(
    job_id: str, speaker: str, source_wav: str, language: Optional[str]
) -> Dict[str, Any]:
    """Run STT for ``speaker`` and return the result dict.

    Raises on failure. Terminal job state (_set_job_complete /
    _set_job_error) is now the dispatcher's responsibility — this
    function only reports in-progress via _set_job_progress. That
    lets the same function run cleanly under every compute mode
    (thread, subprocess, persistent) via the unified compute
    dispatcher, and also keeps direct callers like
    ``_compute_full_pipeline`` simple (try/except + read return value).
    """
    audio_path = _resolve_project_path(source_wav)
    if not audio_path.exists():
        raise FileNotFoundError("Audio file not found: {0}".format(audio_path))

    # NB: the frontend normalizes backend progress values >1 as "percent"
    # and values in [0,1] as "fraction". Sending exactly 1.0 was
    # interpreted as 100%, so the bar flashed full before decoding even
    # started. Use 0.5 (half a percent) for the initial splash.
    _set_job_progress(job_id, 0.5, message="Initializing STT provider ({0})".format(language or "auto"))
    try:
        provider = get_stt_provider()
    except Exception as exc:
        # Capture the full traceback so downstream users see *why* the
        # provider failed to initialize (missing model, CUDA not available,
        # bad config), not just the generic last-message banner.
        import traceback
        tb = traceback.format_exc()
        print("[stt] get_stt_provider failed for speaker={0!r}: {1}".format(speaker, tb), file=sys.stderr, flush=True)
        raise RuntimeError("STT provider init failed: {0}".format(exc)) from exc

    _set_job_progress(job_id, 2.0, message="Loading model")

    # faster-whisper emits segments whose `end` can equal `total_duration`
    # on the very first yield (VAD fuses everything into one chunk for
    # short clips). That makes the raw per-segment progress jump to 100%
    # while decoding is still underway. Cap mid-job progress at 98% so
    # only the dispatcher's _set_job_complete actually fills the bar.
    def _progress_callback(progress: float, segments_processed: int) -> None:
        clamped = min(float(progress) if progress is not None else 0.0, 98.0)
        _set_job_progress(
            job_id,
            max(2.0, clamped),
            message="Transcribing ({0} segments)".format(segments_processed),
            segments_processed=segments_processed,
        )

    try:
        segments = provider.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=_progress_callback,
        )
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print("[stt] transcribe failed for speaker={0!r} path={1!r}: {2}".format(speaker, str(audio_path), tb), file=sys.stderr, flush=True)
        raise RuntimeError("STT transcription failed: {0}".format(exc)) from exc

    result = {
        "speaker": speaker,
        "sourceWav": str(audio_path),
        "language": language,
        "segments": segments,
    }
    _write_stt_cache(speaker, str(audio_path), language, segments)
    return result


def _compute_stt(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compute-dispatcher adapter for STT.

    Unpacks the HTTP/chat payload into ``_run_stt_job``'s positional
    signature. The dispatcher (or persistent worker) handles the
    terminal _set_job_complete / _set_job_error — this wrapper only
    translates payload shapes.
    """
    speaker = str(payload.get("speaker") or "").strip()
    source_wav = str(
        payload.get("sourceWav") or payload.get("source_wav") or ""
    ).strip()
    language_raw = payload.get("language")
    language = str(language_raw).strip() if language_raw is not None else None
    if not language:
        language = None
    if not speaker:
        raise ValueError("stt payload missing 'speaker'")
    if not source_wav:
        raise ValueError("stt payload missing 'sourceWav'")
    return _run_stt_job(job_id, speaker, source_wav, language)


def _parse_concepts_csv(csv_path: pathlib.Path) -> List[Dict[str, str]]:
    """Parse a concepts-style CSV (id, concept_en). Returns [] if columns don't match."""
    import csv as _csv

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as handle:
            reader = _csv.DictReader(handle)
            fieldnames = [str(name or "").strip().lower() for name in (reader.fieldnames or [])]
            if "id" not in fieldnames or "concept_en" not in fieldnames:
                return []
            concepts: List[Dict[str, str]] = []
            for row in reader:
                cid = _normalize_concept_id(row.get("id"))
                label = str(row.get("concept_en") or "").strip()
                if cid and label:
                    concepts.append({"id": cid, "label": label})
            return concepts
    except (OSError, UnicodeDecodeError, _csv.Error):
        return []


def _merge_concepts_into_root_csv(new_concepts: List[Dict[str, str]]) -> int:
    """Merge new concepts into root concepts.csv. Existing rows win on id collision. Returns total."""
    import csv as _csv

    concepts_path = _project_root() / "concepts.csv"
    merged: Dict[str, str] = {}
    if concepts_path.exists():
        try:
            with open(concepts_path, newline="", encoding="utf-8") as handle:
                reader = _csv.DictReader(handle)
                for row in reader:
                    cid = _normalize_concept_id(row.get("id"))
                    label = str(row.get("concept_en") or "").strip()
                    if cid and label:
                        merged[cid] = label
        except (OSError, _csv.Error):
            pass

    for item in new_concepts:
        cid = _normalize_concept_id(item.get("id"))
        label = str(item.get("label") or "").strip()
        if cid and label and cid not in merged:
            merged[cid] = label

    ordered = sorted(merged.items(), key=lambda kv: _concept_sort_key(kv[0]))
    concepts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(concepts_path, "w", newline="", encoding="utf-8") as handle:
        writer = _csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        for cid, label in ordered:
            writer.writerow({"id": cid, "concept_en": label})
    return len(ordered)


def _register_speaker_in_project_json(speaker: str) -> None:
    """Add speaker to project.json speakers block. Preserves existing keys."""
    project = _read_json_file(_project_json_path(), {})
    if not isinstance(project, dict):
        project = {}

    speakers_block = project.get("speakers")
    if isinstance(speakers_block, list):
        speakers_block = {str(item).strip(): {} for item in speakers_block if str(item).strip()}
    elif not isinstance(speakers_block, dict):
        speakers_block = {}
    speakers_block.setdefault(speaker, {})
    project["speakers"] = speakers_block

    _write_json_file(_project_json_path(), project)


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

        _set_job_progress(job_id, 55.0, message="Updating source index")

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

        _set_job_progress(job_id, 70.0, message="Registering speaker in project.json")
        _register_speaker_in_project_json(speaker)

        concept_total: Optional[int] = None
        concepts_added = 0
        comments_imported = 0
        if csv_dest is not None and csv_dest.exists():
            _set_job_progress(job_id, 80.0, message="Merging concepts from CSV")
            parsed = _parse_concepts_csv(csv_dest)
            if parsed:
                concepts_added = len(parsed)
                concept_total = _merge_concepts_into_root_csv(parsed)
            else:
                # Not a concepts CSV — try as an Audition comments export so that
                # onboarding can also seed lexeme-level import notes in one step.
                try:
                    from lexeme_notes import parse_audition_csv as _parse_comments
                    csv_text = csv_dest.read_text(encoding="utf-8-sig")
                    comment_rows = _parse_comments(csv_text)
                    if comment_rows:
                        payload = _read_json_file(_enrichments_path(), _default_enrichments_payload())
                        notes_block = payload.get("lexeme_notes")
                        if not isinstance(notes_block, dict):
                            notes_block = {}
                            payload["lexeme_notes"] = notes_block
                        speaker_block = notes_block.get(speaker)
                        if not isinstance(speaker_block, dict):
                            speaker_block = {}
                            notes_block[speaker] = speaker_block
                        for row in comment_rows:
                            cid = _normalize_concept_id(row.concept_id)
                            note = (row.remainder or "").strip()
                            if not cid or not note:
                                continue
                            entry = speaker_block.get(cid) or {}
                            entry["import_note"] = note
                            entry["import_raw"] = row.raw_name
                            entry["updated_at"] = _utc_now_iso()
                            speaker_block[cid] = entry
                            comments_imported += 1
                        _write_json_file(_enrichments_path(), payload)
                except Exception:
                    comments_imported = 0

        _set_job_progress(job_id, 90.0, message="Finalizing")

        result: Dict[str, Any] = {
            "speaker": speaker,
            "wavPath": wav_relative,
            "csvPath": str(csv_dest.relative_to(_project_root())) if csv_dest else None,
            "annotationPath": str(annotation_path.relative_to(_project_root())),
            "conceptsAdded": concepts_added,
            "conceptTotal": concept_total,
            "commentsImported": comments_imported,
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

        # If the source WAV is already living at the destination (e.g. a
        # processed-speaker import landed the file directly under
        # audio/working/<speaker>/), we can't ask ffmpeg to read-and-write the
        # same file — it will truncate the input mid-read. Route the output
        # through a sibling temp path and atomically replace after ffmpeg
        # reports success.
        try:
            inplace = output_path.resolve() == audio_path.resolve()
        except OSError:
            inplace = str(output_path) == str(audio_path)
        if inplace:
            write_path = output_path.with_name(output_path.stem + ".normalized.tmp.wav")
        else:
            write_path = output_path

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
            str(write_path),
        ]
        proc = subprocess.run(
            normalize_cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if proc.returncode != 0:
            error_tail = (proc.stderr or "")[-800:]
            if inplace and write_path.exists():
                try:
                    write_path.unlink()
                except OSError:
                    pass
            raise RuntimeError("ffmpeg normalize failed (exit {0}): {1}".format(proc.returncode, error_tail))

        if not write_path.exists():
            raise RuntimeError("ffmpeg produced no output file")

        if inplace:
            # Atomic same-filesystem swap keeps the workspace consistent —
            # there's never a window where output_path is missing.
            os.replace(str(write_path), str(output_path))

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


_IPA_ALIGNER: Any = None


def _get_ipa_aligner() -> Any:
    """Lazy-load the Tier 2/3 wav2vec2 Aligner. Cached for the server lifetime.

    Prints one-shot load diagnostics so the very-slow first call ("Loading
    wav2vec2 …" can take 30s+ on first download, minutes on CPU) is
    observable in the API stderr log. Subsequent calls reuse the cached
    model and are free.
    """
    global _IPA_ALIGNER
    if _IPA_ALIGNER is not None:
        _compute_checkpoint("ALIGNER.cached")
        return _IPA_ALIGNER

    import time as _time
    _compute_checkpoint("ALIGNER.import_begin")
    from ai.forced_align import Aligner, DEFAULT_MODEL_NAME
    _compute_checkpoint("ALIGNER.import_done", model=DEFAULT_MODEL_NAME)

    t0 = _time.time()
    print(
        "[IPA] Loading wav2vec2 aligner model={0}…".format(DEFAULT_MODEL_NAME),
        file=sys.stderr,
        flush=True,
    )
    # Honour wav2vec2.force_cpu from ai_config.json, or auto-detect via
    # resolve_device() which forces CPU on WSL to avoid GPU driver crashes.
    try:
        import json as _json
        _ai_cfg = _json.loads((_project_root() / "config" / "ai_config.json").read_text())
        _w2v = _ai_cfg.get("wav2vec2", {})
        if _w2v.get("force_cpu"):
            _ipa_device: Optional[str] = "cpu"
        else:
            _ipa_device = _w2v.get("device") or None
    except Exception:
        _ai_cfg = {}
        _w2v = {}
        _ipa_device = None

    from ai.forced_align import _is_wsl as _fa_is_wsl
    if _fa_is_wsl():
        import os as _os
        _os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "1")
        print("[COMPUTE] WSL detected → CUDA_LAUNCH_BLOCKING=1", file=sys.stderr, flush=True)

    try:
        _compute_checkpoint("ALIGNER.load_begin")
        _IPA_ALIGNER = Aligner.load(device=_ipa_device)
        _compute_checkpoint("ALIGNER.load_done", elapsed=round(_time.time() - t0, 2))
    except Exception as exc:
        elapsed = _time.time() - t0
        _compute_checkpoint(
            "ALIGNER.load_error",
            elapsed=round(elapsed, 2),
            exc_type=type(exc).__name__,
            exc=str(exc)[:200],
        )
        print(
            "[IPA][ERROR] Aligner.load() failed after {0:.1f}s: {1}".format(elapsed, exc),
            file=sys.stderr,
            flush=True,
        )
        raise

    elapsed = _time.time() - t0
    device = getattr(_IPA_ALIGNER, "device", "?")
    vocab_size = len(getattr(_IPA_ALIGNER, "vocab", {}) or {})
    _compute_checkpoint(
        "ALIGNER.ready", elapsed=round(elapsed, 2), device=device, vocab_size=vocab_size
    )
    print(
        "[IPA] Aligner ready in {0:.1f}s device={1} vocab_size={2}".format(
            elapsed, device, vocab_size
        ),
        file=sys.stderr,
        flush=True,
    )
    return _IPA_ALIGNER


def _compute_speaker_ipa(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing IPA cells on a speaker's annotation via acoustic wav2vec2.

    Tier 3 of the acoustic alignment pipeline: for each ortho interval, run
    ``facebook/wav2vec2-xlsr-53-espeak-cv-ft`` CTC directly on the audio
    window ``[start, end]`` and write the greedy-decoded phoneme string
    into the IPA tier. No text → IPA conversion happens anywhere — the
    ortho text is used only to decide whether the interval is worth
    transcribing (empty ortho → skip).

    Intervals with existing non-empty IPA are left alone unless
    ``overwrite=True`` — so this can be re-run safely without clobbering
    manual edits.

    Payload: ``{ "speaker": "Fail02", "overwrite": false }``.
    """
    # Diagnostics v3: stderr prints for human tailers + buffer-free
    # checkpoint log for post-mortem when Windows pipe buffering eats
    # the tail of stderr.
    _compute_checkpoint("IPA.enter", payload=payload)
    print("[IPA] enter _compute_speaker_ipa payload={0}".format(payload), file=sys.stderr, flush=True)

    speaker = _normalize_speaker_id(payload.get("speaker"))
    overwrite = bool(payload.get("overwrite", False))
    _compute_checkpoint("IPA.parsed_args", speaker=speaker, overwrite=overwrite)

    canonical_path = _project_root() / _annotation_record_relative_path(speaker)
    legacy_path = _project_root() / _annotation_legacy_record_relative_path(speaker)
    _compute_checkpoint("IPA.resolved_paths", canonical=str(canonical_path), legacy=str(legacy_path))

    _compute_checkpoint("IPA.is_file_begin")
    if canonical_path.is_file():
        annotation_path = canonical_path
    elif legacy_path.is_file():
        annotation_path = legacy_path
    else:
        raise RuntimeError("No annotation found for speaker {0!r}".format(speaker))
    _compute_checkpoint("IPA.is_file_done", annotation_path=str(annotation_path))

    print("[IPA] loaded annotation_path={0}".format(annotation_path), file=sys.stderr, flush=True)
    _compute_checkpoint("IPA.read_json_begin")
    annotation = _read_json_file(annotation_path, {})
    _compute_checkpoint("IPA.read_json_done")
    if not isinstance(annotation, dict):
        raise RuntimeError("Annotation is not a JSON object")

    tiers = annotation.get("tiers") or {}
    ortho_tier = tiers.get("ortho") or {}
    ortho_intervals = list(ortho_tier.get("intervals") or [])
    if not ortho_intervals:
        print("[IPA] no ortho intervals — early return", file=sys.stderr, flush=True)
        return {"speaker": speaker, "filled": 0, "skipped": 0, "total": 0, "message": "No ortho intervals."}

    ipa_tier = tiers.setdefault("ipa", {"type": "interval", "display_order": 1, "intervals": []})
    ipa_intervals: List[Dict[str, Any]] = list(ipa_tier.get("intervals") or [])

    def _key(interval: Dict[str, Any]) -> Tuple[float, float]:
        return (round(float(interval.get("start", 0.0)), 3), round(float(interval.get("end", 0.0)), 3))

    ipa_by_key: Dict[Tuple[float, float], Dict[str, Any]] = {_key(i): i for i in ipa_intervals}
    print(
        "[IPA] ortho_intervals={0} existing_ipa_intervals={1}".format(
            len(ortho_intervals), len(ipa_intervals)
        ),
        file=sys.stderr,
        flush=True,
    )

    # Resolve the speaker's working audio once; a 5-hour recording loads
    # into ~300 MB of float32 which is fine for a one-shot pass.
    _compute_checkpoint("IPA.resolve_audio_begin", speaker=speaker)
    print("[IPA] resolving audio path for speaker={0}…".format(speaker), file=sys.stderr, flush=True)
    audio_path = _pipeline_audio_path_for_speaker(speaker)
    _compute_checkpoint("IPA.resolve_audio_done", audio_path=str(audio_path))
    print("[IPA] audio_path={0} — importing ai.forced_align".format(audio_path), file=sys.stderr, flush=True)

    _compute_checkpoint("IPA.import_forced_align_begin")
    from ai.forced_align import _load_audio_mono_16k
    _compute_checkpoint("IPA.import_forced_align_done")
    print("[IPA] import ok — calling _load_audio_mono_16k()", file=sys.stderr, flush=True)

    import time as _t_load
    _compute_checkpoint("IPA.load_audio_begin")
    _t0 = _t_load.time()
    audio_tensor = _load_audio_mono_16k(audio_path)
    _load_elapsed = _t_load.time() - _t0
    try:
        _numel = int(audio_tensor.numel())
    except Exception:
        _numel = -1
    _compute_checkpoint(
        "IPA.load_audio_done", elapsed=round(_load_elapsed, 2), numel=_numel
    )
    print(
        "[IPA] audio loaded in {0:.1f}s numel={1} (~{2:.1f}s of 16 kHz mono)".format(
            _load_elapsed, _numel, _numel / 16000.0 if _numel > 0 else 0.0
        ),
        file=sys.stderr,
        flush=True,
    )
    print("[IPA] calling _get_ipa_aligner()…", file=sys.stderr, flush=True)
    _compute_checkpoint("IPA.get_aligner_begin")
    aligner = _get_ipa_aligner()
    _compute_checkpoint("IPA.get_aligner_done")
    # Use the full Tier 2+3 path when the STT cache has word timestamps;
    # fall back to coarse ORTH-interval CTC when it doesn't.
    stt_segments = _read_stt_cache(speaker)
    has_words = bool(stt_segments and any(seg.get("words") for seg in stt_segments))

    exception_samples: List[str] = []
    skipped_empty_ortho = 0
    skipped_existing_ipa = 0
    skipped_zero_range = 0
    skipped_exception = 0
    skipped_empty_ipa = 0

    if has_words:
        print("[IPA] STT cache has words — using full forced-align path (Tier 2+3)", file=sys.stderr, flush=True)
        _compute_checkpoint("IPA.forced_align_begin")
        from ai.ipa_transcribe import transcribe_words_with_forced_align

        total_words = sum(len(seg.get("words") or []) for seg in stt_segments)

        def _word_progress(pct: float, n: int) -> None:
            _set_job_progress(job_id, 5.0 + pct * 0.9, message="IPA {0}/{1} words".format(n, total_words))

        try:
            import json as _json2
            _ai_cfg2 = _json2.loads((_project_root() / "config" / "ai_config.json").read_text())
            _chunk_size = int(_ai_cfg2.get("wav2vec2", {}).get("chunk_size", 150))
        except Exception:
            _chunk_size = 150
        word_results = transcribe_words_with_forced_align(
            audio_path,
            stt_segments,
            aligner=aligner,
            progress_callback=_word_progress,
            chunk_size=_chunk_size,
        )
        _compute_checkpoint("IPA.forced_align_done", word_count=len(word_results))
        print("[IPA] forced-align IPA: {0} word intervals".format(len(word_results)), file=sys.stderr, flush=True)

        ipa_intervals = [
            {"start": r["start"], "end": r["end"], "text": r["ipa"]}
            for r in word_results
        ]
        filled = sum(1 for r in word_results if r["ipa"])
        skipped_empty_ipa = sum(1 for r in word_results if not r["ipa"])
        skipped = skipped_empty_ipa
        total = len(word_results)
    else:
        print("[IPA] no STT word cache — using coarse ORTH-interval fallback", file=sys.stderr, flush=True)
        _compute_checkpoint("IPA.loop_begin", n=len(ortho_intervals))

        filled = 0
        skipped = 0
        total = len(ortho_intervals)

        for idx, ortho in enumerate(ortho_intervals):
            text = str(ortho.get("text") or "").strip()
            start_sec = float(ortho.get("start", 0.0) or 0.0)
            end_sec = float(ortho.get("end", start_sec) or start_sec)
            key = _key(ortho)
            existing = ipa_by_key.get(key)
            existing_text = str((existing or {}).get("text") or "").strip()

            if not text:
                skipped += 1
                skipped_empty_ortho += 1
                continue
            if existing_text and not overwrite:
                skipped += 1
                skipped_existing_ipa += 1
                continue
            if end_sec <= start_sec:
                skipped += 1
                skipped_zero_range += 1
                continue

            _trace_iv = idx < 3 or idx % 10 == 0
            if _trace_iv:
                _compute_checkpoint("IPA.iv_begin", idx=idx, start=start_sec, end=end_sec)
            try:
                new_ipa = _acoustic_transcribe_slice(audio_tensor, start_sec, end_sec, aligner)
            except Exception as exc:
                skipped += 1
                skipped_exception += 1
                if _trace_iv:
                    _compute_checkpoint("IPA.iv_exc", idx=idx, exc_type=type(exc).__name__, exc=str(exc)[:200])
                if len(exception_samples) < 3:
                    exception_samples.append(
                        "interval[{0}] {1:.2f}-{2:.2f}: {3}: {4}".format(
                            idx, start_sec, end_sec, type(exc).__name__, exc
                        )
                    )
                continue

            if _trace_iv:
                _compute_checkpoint("IPA.iv_done", idx=idx, out_len=len(str(new_ipa or "")))
            new_ipa = str(new_ipa or "").strip()
            if not new_ipa:
                skipped += 1
                skipped_empty_ipa += 1
                continue

            if existing is not None:
                existing["text"] = new_ipa
            else:
                new_interval = {"start": ortho["start"], "end": ortho["end"], "text": new_ipa}
                ipa_intervals.append(new_interval)
                ipa_by_key[key] = new_interval
            filled += 1

            progress = 5.0 + ((idx + 1) / total) * 90.0
            _set_job_progress(job_id, progress, message="IPA {0}/{1}".format(idx + 1, total))

    ipa_intervals.sort(key=lambda i: (float(i.get("start", 0.0)), float(i.get("end", 0.0))))
    ipa_tier["intervals"] = ipa_intervals
    tiers["ipa"] = ipa_tier
    annotation["tiers"] = tiers
    _annotation_touch_metadata(annotation, preserve_created=True)

    _write_json_file(annotation_path, annotation)
    # Keep both file shapes in sync (the server prefers .parse.json; external
    # tooling sometimes writes the legacy .json).
    if canonical_path != annotation_path:
        _write_json_file(canonical_path, annotation)
    if legacy_path != annotation_path:
        _write_json_file(legacy_path, annotation)

    skip_breakdown = {
        "empty_ortho": skipped_empty_ortho,
        "existing_ipa_no_overwrite": skipped_existing_ipa,
        "zero_range": skipped_zero_range,
        "exception": skipped_exception,
        "empty_ipa_from_model": skipped_empty_ipa,
    }
    print(
        "[IPA] speaker={0} filled={1} skipped={2} total={3} breakdown={4}".format(
            speaker, filled, skipped, total, skip_breakdown
        ),
        file=sys.stderr,
        flush=True,
    )
    if exception_samples:
        for sample in exception_samples:
            print("[IPA][EXC] {0}".format(sample), file=sys.stderr, flush=True)

    return {
        "speaker": speaker,
        "filled": filled,
        "skipped": skipped,
        "total": total,
        "skip_breakdown": skip_breakdown,
        "exception_samples": exception_samples,
    }


def _compute_speaker_forced_align(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run Tier 2 forced alignment for a speaker.

    Looks up the speaker's most recent STT artifact (which carries nested
    segments[].words[] from Tier 1), refines each word window with
    torchaudio.functional.forced_align + xlsr-53-espeak-cv-ft, and writes
    the refined spans back next to the input artifact as
    ``*.aligned.json``. Ortho / IPA tiers in the annotation are left
    untouched — this job only produces the refined boundary artifact
    that Tier 3 (or a manual UI step) can then consume.
    """
    speaker = _normalize_speaker_id(payload.get("speaker"))
    overwrite = bool(payload.get("overwrite", False))
    language = str(payload.get("language") or "ku").strip() or "ku"
    try:
        pad_ms = int(payload.get("padMs", 100) or 100)
    except (TypeError, ValueError):
        pad_ms = 100
    pad_ms = max(0, min(500, pad_ms))
    emit_phonemes = bool(payload.get("emitPhonemes", True))

    audio_path = _pipeline_audio_path_for_speaker(speaker)

    # Discover a Tier 1 STT artifact for the speaker. Convention:
    # stt_output/<speaker>.stt.json; fall back to any sibling stt.json.
    stt_candidates = [
        _project_root() / "stt_output" / "{0}.stt.json".format(speaker),
        _project_root() / "stt_output" / speaker / "stt.json",
    ]
    stt_artifact_path: Optional[pathlib.Path] = next(
        (p for p in stt_candidates if p.is_file()), None
    )
    if stt_artifact_path is None:
        raise RuntimeError(
            "No Tier 1 STT artifact found for {0!r}. Run stt_word_level_start "
            "first so segments[].words[] are available as alignment seeds.".format(
                speaker
            )
        )

    artifact = _read_json_file(stt_artifact_path, {})
    if not isinstance(artifact, dict):
        raise RuntimeError("STT artifact is not a JSON object: {0}".format(stt_artifact_path))
    segments = artifact.get("segments") or []
    if not isinstance(segments, list):
        raise RuntimeError("STT artifact segments[] is missing or malformed")

    _set_job_progress(job_id, 10.0, message="Loading wav2vec2 aligner")

    from ai.forced_align import align_segments

    aligned = align_segments(
        audio_path=pathlib.Path(audio_path),
        segments=segments,
        language=language,
        pad_ms=pad_ms,
        emit_phonemes=emit_phonemes,
    )

    aligned_segments: List[Dict[str, Any]] = []
    method_counts: Dict[str, int] = {}
    for seg_idx, seg in enumerate(segments):
        refined_words = aligned[seg_idx] if seg_idx < len(aligned) else []
        merged: Dict[str, Any] = dict(seg)
        if refined_words:
            merged["words"] = list(refined_words)
            for w in refined_words:
                m = str(w.get("method", "") or "unknown")
                method_counts[m] = method_counts.get(m, 0) + 1
        aligned_segments.append(merged)

    output_path = stt_artifact_path.with_suffix("")
    if output_path.suffix == ".stt":
        output_path = output_path.with_suffix("")
    output_path = output_path.parent / "{0}.aligned.json".format(output_path.name)

    if output_path.is_file() and not overwrite:
        existing = _read_json_file(output_path, {})
        return {
            "speaker": speaker,
            "skipped": True,
            "reason": "aligned artifact already exists; pass overwrite=true to replace",
            "alignedArtifact": str(output_path),
            "segmentCount": len(existing.get("segments") or []),
        }

    out_payload = {
        **artifact,
        "segments": aligned_segments,
        "alignment": {
            "tier": "tier2_forced_align",
            "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
            "language": language,
            "padMs": pad_ms,
            "emitPhonemes": emit_phonemes,
            "methodCounts": method_counts,
        },
    }
    _write_json_file(output_path, out_payload)

    _set_job_progress(job_id, 95.0, message="Wrote aligned artifact")

    return {
        "speaker": speaker,
        "sttArtifact": str(stt_artifact_path),
        "alignedArtifact": str(output_path),
        "segmentCount": len(aligned_segments),
        "methodCounts": method_counts,
    }


def _pipeline_audio_path_for_speaker(speaker: str) -> pathlib.Path:
    """Resolve the best audio file to feed a Whisper-family model for a speaker.

    Prefers the normalized working copy under ``audio/working/<speaker>/`` if it
    exists; otherwise falls back to the raw source recording recorded in the
    annotation's ``source_audio`` field. Raises ``FileNotFoundError`` if neither
    is reachable.
    """
    annotation_path = _annotation_read_path_for_speaker(speaker)
    if not annotation_path.is_file():
        raise RuntimeError("No annotation found for speaker {0!r}".format(speaker))

    record = _read_json_file(annotation_path, {})
    source_rel = ""
    if isinstance(record, dict):
        source_rel = str(
            record.get("source_audio") or record.get("source_wav") or ""
        ).strip()
    if not source_rel:
        source_rel = _annotation_primary_source_wav(speaker)
    if not source_rel:
        raise RuntimeError(
            "No source_audio on annotation for {0!r}; import or onboard the speaker first".format(
                speaker
            )
        )

    source_path = _resolve_project_path(source_rel)
    working_dir = _project_root() / "audio" / "working" / speaker
    normalized_path = build_normalized_output_path(source_path, working_dir)
    if normalized_path.exists():
        return normalized_path
    if source_path.exists():
        return source_path
    raise FileNotFoundError(
        "Neither normalized ({0}) nor source audio ({1}) exists for {2!r}".format(
            normalized_path, source_path, speaker
        )
    )


def _audio_duration_sec(path: pathlib.Path) -> Optional[float]:
    """Best-effort audio duration in seconds.

    Reads the WAV RIFF header via the stdlib ``wave`` module — no optional
    deps, no decode overhead. Returns ``None`` when the file is missing,
    unreadable, or not a standard PCM WAV (the caller falls back to the
    annotation's ``source_audio_duration_sec`` hint).
    """
    try:
        if not path.is_file():
            return None
        import wave
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if not rate:
                return None
            return float(frames) / float(rate)
    except Exception:
        return None


# Tier coverage is considered "full-file" when either:
#   - the tier's last interval ends within this fraction of the audio
#     duration, OR
#   - within ``_COVERAGE_ABSOLUTE_TOLERANCE_SEC`` of the audio end.
#
# Both checks matter: a 6-minute recording with coverage at 95% still has
# 18 unprocessed seconds (not "full"), but a 30-second clip with coverage
# ending 1 second short IS effectively full. The absolute tolerance
# catches the short-clip case; the fractional tolerance catches long-clip
# tail silence that razhan/Whisper legitimately skips.
_COVERAGE_FRACTION_THRESHOLD = 0.95
_COVERAGE_ABSOLUTE_TOLERANCE_SEC = 3.0


def _tier_coverage(
    intervals: Any,
    duration_sec: Optional[float],
) -> Dict[str, Any]:
    """Summarise how much of a file a tier's intervals cover.

    Returns a dict with ``coverage_start_sec``, ``coverage_end_sec``,
    ``coverage_fraction`` (None when duration is unknown), and
    ``full_coverage`` (None when duration is unknown, else bool).

    This is the signal that answers "was the whole WAV processed, or just
    the slice where pre-existing concept timestamps happened to live?"
    Non-empty text is required — empty intervals don't count as coverage.
    """
    coverage_start: Optional[float] = None
    coverage_end: Optional[float] = None
    if isinstance(intervals, list):
        for iv in intervals:
            if not isinstance(iv, dict):
                continue
            if not str(iv.get("text") or "").strip():
                continue
            try:
                start = float(iv.get("start") or 0.0)
                end = float(iv.get("end") or start)
            except (TypeError, ValueError):
                continue
            if coverage_start is None or start < coverage_start:
                coverage_start = start
            if coverage_end is None or end > coverage_end:
                coverage_end = end

    fraction: Optional[float] = None
    full: Optional[bool] = None
    if duration_sec is not None and duration_sec > 0 and coverage_end is not None:
        fraction = max(0.0, min(1.0, coverage_end / duration_sec))
        full = bool(
            fraction >= _COVERAGE_FRACTION_THRESHOLD
            or (duration_sec - coverage_end) < _COVERAGE_ABSOLUTE_TOLERANCE_SEC
        )
    elif duration_sec is not None and duration_sec > 0 and coverage_end is None:
        # No intervals at all → explicitly not-full.
        fraction = 0.0
        full = False

    return {
        "coverage_start_sec": coverage_start,
        "coverage_end_sec": coverage_end,
        "coverage_fraction": fraction,
        "full_coverage": full,
    }


def _pipeline_state_for_speaker(speaker: str) -> Dict[str, Any]:
    """Return what's already been done for a speaker, per pipeline step.

    Shape (per step)::

        {
          "done": true,            # tier has ≥1 non-empty interval (or normalize WAV exists)
          "intervals": 84,         # or "segments" for stt, "path" for normalize
          "can_run": true,         # step can be invoked right now
          "reason": null,          # populated when can_run is false

          # Full-file coverage (new — the "whole WAV processed?" signal):
          "coverage_start_sec": 0.12,   # first non-empty interval start
          "coverage_end_sec": 351.44,   # last non-empty interval end
          "coverage_fraction": 0.98,    # coverage_end / duration
          "full_coverage": true         # true when coverage spans ≥95% OR
                                        # within 3s of the audio end
        }

    Top-level adds ``duration_sec`` so callers can reason about absolute
    coverage.

    ``done`` is a cheap "has any data?" signal — useful for the UI's
    "will overwrite" warning. ``full_coverage`` is the signal an agent
    should check before declaring the step truly complete: a tier with
    128 intervals that cover only the first 30 seconds of a 6-minute
    recording reports ``done=True`` + ``full_coverage=False``, and the
    tier should be re-run.

    ``can_run`` is computed against the *current* filesystem; for a
    batch that runs multiple steps, ``ipa.can_run`` may be false today
    but will succeed after the ORTH step in the same batch runs.
    """
    speaker_norm = _normalize_speaker_id(speaker)
    result: Dict[str, Any] = {"speaker": speaker_norm}

    try:
        annotation_path = _annotation_read_path_for_speaker(speaker_norm)
        record = _read_json_file(annotation_path, {}) if annotation_path.is_file() else {}
    except Exception:
        record = {}

    has_annotation = isinstance(record, dict) and bool(record)

    source_rel = ""
    if isinstance(record, dict):
        source_rel = str(
            record.get("source_audio") or record.get("source_wav") or ""
        ).strip()
    source_path: Optional[pathlib.Path] = None
    source_exists = False
    normalized_path: Optional[pathlib.Path] = None
    normalized_exists = False
    if source_rel:
        try:
            source_path = _resolve_project_path(source_rel)
            source_exists = source_path.exists()
            working_dir = _project_root() / "audio" / "working" / speaker_norm
            normalized_path = build_normalized_output_path(source_path, working_dir)
            normalized_exists = normalized_path.exists()
        except Exception:
            pass

    # Resolve duration: prefer the actual WAV header on disk (truth),
    # fall back to ``source_audio_duration_sec`` from the annotation.
    # Coverage ratios use the truthiest number we can find.
    duration_sec: Optional[float] = None
    for candidate in (normalized_path, source_path):
        if candidate is not None and candidate.is_file():
            duration_sec = _audio_duration_sec(candidate)
            if duration_sec:
                break
    if duration_sec is None and isinstance(record, dict):
        meta_dur = record.get("source_audio_duration_sec")
        try:
            meta_float = float(meta_dur) if meta_dur is not None else None
        except (TypeError, ValueError):
            meta_float = None
        if meta_float and meta_float > 0:
            duration_sec = meta_float
    result["duration_sec"] = duration_sec

    # --- Normalize ---
    normalize_info: Dict[str, Any] = {
        "done": normalized_exists,
        "path": (
            str(normalized_path.relative_to(_project_root()))
            if normalized_exists and normalized_path is not None
            else None
        ),
        "can_run": False,
        "reason": None,
    }
    if not has_annotation:
        normalize_info["reason"] = "No annotation for speaker"
    elif not source_rel:
        normalize_info["reason"] = "No source_audio on annotation"
    elif not source_exists:
        normalize_info["reason"] = "Source audio not found: {0}".format(source_rel)
    else:
        normalize_info["can_run"] = True
    result["normalize"] = normalize_info

    # --- STT ---
    cached_stt = _latest_stt_segments_for_speaker(speaker_norm)
    stt_info: Dict[str, Any] = {
        "done": bool(cached_stt),
        "segments": len(cached_stt) if cached_stt else 0,
        "can_run": False,
        "reason": None,
    }
    stt_info.update(_tier_coverage(cached_stt, duration_sec))
    if not has_annotation:
        stt_info["reason"] = "No annotation for speaker"
    elif not (normalized_exists or source_exists):
        stt_info["reason"] = "No audio file reachable (neither normalized nor source exists)"
    else:
        stt_info["can_run"] = True
    result["stt"] = stt_info

    # --- ORTH + IPA (tier intervals) ---
    tiers = {}
    if isinstance(record, dict):
        tiers = record.get("tiers") if isinstance(record.get("tiers"), dict) else {}

    def _non_empty_count(tier_name: str) -> int:
        tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
        if not isinstance(tier, dict):
            return 0
        intervals = tier.get("intervals") or []
        if not isinstance(intervals, list):
            return 0
        return sum(
            1 for iv in intervals
            if isinstance(iv, dict) and str(iv.get("text") or "").strip()
        )

    def _tier_intervals(tier_name: str) -> Any:
        tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
        return tier.get("intervals") if isinstance(tier, dict) else None

    ortho_intervals = _tier_intervals("ortho")
    ipa_intervals = _tier_intervals("ipa")
    ortho_count = _non_empty_count("ortho")
    ipa_count = _non_empty_count("ipa")

    ortho_info: Dict[str, Any] = {
        "done": ortho_count > 0,
        "intervals": ortho_count,
        "can_run": False,
        "reason": None,
    }
    ortho_info.update(_tier_coverage(ortho_intervals, duration_sec))
    if not has_annotation:
        ortho_info["reason"] = "No annotation for speaker"
    elif not (normalized_exists or source_exists):
        ortho_info["reason"] = "No audio file reachable (neither normalized nor source exists)"
    else:
        ortho_info["can_run"] = True
    result["ortho"] = ortho_info

    ipa_info: Dict[str, Any] = {
        "done": ipa_count > 0,
        "intervals": ipa_count,
        "can_run": False,
        "reason": None,
    }
    ipa_info.update(_tier_coverage(ipa_intervals, duration_sec))
    if not has_annotation:
        ipa_info["reason"] = "No annotation for speaker"
    elif ortho_count == 0:
        ipa_info["reason"] = "No ortho intervals yet — run ORTH first (or include it in this batch)"
    else:
        ipa_info["can_run"] = True
    result["ipa"] = ipa_info

    return result


def _ortho_tier2_align_to_words(
    audio_path: pathlib.Path,
    segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Run Tier-2 forced alignment on ORTH segments, returning a flat word tier.

    Takes the full raw segment list (with Whisper ``words[]`` per segment)
    and returns a flat sorted list of ``{start, end, text, confidence,
    source}`` dicts suitable for ``tiers.ortho_words.intervals``.

    Any exception is logged and an empty list is returned — alignment is a
    refinement pass, not a gate; the coarse ortho tier has already been
    written by the caller.
    """
    if not segments:
        return []
    has_any_words = any(seg.get("words") for seg in segments)
    if not has_any_words:
        print(
            "[ORTH] Tier-2 skipped: no word-level timestamps on any segment",
            file=sys.stderr,
        )
        return []

    try:
        from ai.forced_align import align_segments
    except Exception as exc:  # pragma: no cover - import failure is rare
        print("[ORTH] Tier-2 import failed: {0}".format(exc), file=sys.stderr)
        return []

    try:
        aligned = align_segments(audio_path=audio_path, segments=segments)
    except Exception as exc:
        print("[ORTH] Tier-2 alignment failed: {0}".format(exc), file=sys.stderr)
        return []

    flat: List[Dict[str, Any]] = []
    for seg_words in aligned:
        for word in seg_words or []:
            text = str(word.get("word", "") or "").strip()
            if not text:
                continue
            try:
                start = float(word.get("start", 0.0) or 0.0)
                end = float(word.get("end", start) or start)
            except (TypeError, ValueError):
                continue
            if end < start:
                continue
            interval: Dict[str, Any] = {
                "start": start,
                "end": end,
                "text": text,
                "source": "forced_align",
            }
            conf = word.get("confidence")
            if conf is not None:
                try:
                    interval["confidence"] = float(conf)
                except (TypeError, ValueError):
                    pass
            flat.append(interval)

    flat.sort(key=lambda iv: (float(iv["start"]), float(iv["end"])))
    return flat


def _short_clip_refine_lexemes(
    audio_path: pathlib.Path,
    concept_intervals: List[Dict[str, Any]],
    ortho_words: List[Dict[str, Any]],
    provider: Any,
    *,
    pad_sec: float = 0.8,
    weak_conf: float = 0.5,
    job_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Re-transcribe a ±``pad_sec`` window per concept whose ortho_words
    match is missing or weak, using a Whisper ``initial_prompt`` built from
    the concept labels themselves. Returns new ``ortho_words``-shaped
    entries with ``source="short_clip_fallback"`` that the caller should
    merge (upsert) into the main list.
    """
    if not concept_intervals:
        return []

    concept_labels = sorted({
        str(iv.get("text") or "").strip()
        for iv in concept_intervals
        if isinstance(iv, dict) and str(iv.get("text") or "").strip()
    })
    if not concept_labels:
        return []
    # Whisper's prompt is capped around ~224 tokens; keep the concept list
    # comfortably below that so the slice inference stays fast.
    initial_prompt = ", ".join(concept_labels)[:400]

    try:
        from ai.forced_align import _load_audio_mono_16k, DEFAULT_SAMPLE_RATE
    except Exception as exc:
        print("[ORTH] short-clip fallback import failed: {0}".format(exc), file=sys.stderr)
        return []

    try:
        waveform = _load_audio_mono_16k(audio_path)
    except Exception as exc:
        print("[ORTH] short-clip audio load failed: {0}".format(exc), file=sys.stderr)
        return []

    import numpy as np  # type: ignore

    # waveform may be shape (n,) or (1, n) — normalize to 1-D numpy.
    try:
        tensor = waveform
        if hasattr(tensor, "squeeze"):
            tensor = tensor.squeeze()
        audio_np = tensor.numpy() if hasattr(tensor, "numpy") else np.asarray(tensor)
        audio_np = np.asarray(audio_np, dtype=np.float32).reshape(-1)
    except Exception as exc:
        print("[ORTH] short-clip audio conversion failed: {0}".format(exc), file=sys.stderr)
        return []

    total_samples = audio_np.shape[0]
    duration_sec = total_samples / float(DEFAULT_SAMPLE_RATE) if total_samples else 0.0

    ortho_sorted = sorted(
        (w for w in ortho_words if isinstance(w, dict)),
        key=lambda w: (float(w.get("start", 0.0) or 0.0), float(w.get("end", 0.0) or 0.0)),
    )

    def _best_match(concept_iv: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        c_start = float(concept_iv.get("start", 0.0) or 0.0)
        c_end = float(concept_iv.get("end", c_start) or c_start)
        if c_end <= c_start:
            return None
        best: Optional[Dict[str, Any]] = None
        best_overlap = 0.0
        for w in ortho_sorted:
            w_start = float(w.get("start", 0.0) or 0.0)
            w_end = float(w.get("end", w_start) or w_start)
            if w_end <= c_start or w_start >= c_end:
                continue
            ov = min(c_end, w_end) - max(c_start, w_start)
            if ov > best_overlap:
                best_overlap = ov
                best = w
        return best

    additions: List[Dict[str, Any]] = []
    total = len(concept_intervals)
    for idx, concept_iv in enumerate(concept_intervals):
        if not isinstance(concept_iv, dict):
            continue
        try:
            c_start = float(concept_iv.get("start", 0.0) or 0.0)
            c_end = float(concept_iv.get("end", c_start) or c_start)
        except (TypeError, ValueError):
            continue
        if c_end <= c_start or duration_sec <= 0.0:
            continue

        match = _best_match(concept_iv)
        match_conf = 0.0
        if match is not None:
            try:
                match_conf = float(match.get("confidence") or 0.0)
            except (TypeError, ValueError):
                match_conf = 0.0
            if match_conf >= weak_conf and str(match.get("text") or "").strip():
                continue  # strong forced-alignment match — don't re-transcribe.

        slice_start = max(0.0, c_start - pad_sec)
        slice_end = min(duration_sec, c_end + pad_sec)
        if slice_end <= slice_start:
            continue
        s0 = int(slice_start * DEFAULT_SAMPLE_RATE)
        s1 = int(slice_end * DEFAULT_SAMPLE_RATE)
        clip = audio_np[s0:s1]
        if clip.size == 0:
            continue

        text, conf = provider.transcribe_clip(
            clip,
            initial_prompt=initial_prompt,
        )
        text = (text or "").strip()
        if not text:
            continue

        additions.append({
            "start": c_start,
            "end": c_end,
            "text": text,
            "confidence": float(conf or 0.0),
            "source": "short_clip_fallback",
        })

        # Per-concept stderr log keeps long runs legible in the server log.
        # The UI progress bar is throttled to every 10 concepts so the
        # websocket/poll channel doesn't drown in updates.
        print(
            "[ORTH] refine_lexemes {0}/{1} concept='{2}' → '{3}' (conf {4:.2f})".format(
                idx + 1, total, str(concept_iv.get("text") or "")[:40], text[:40], float(conf or 0.0),
            ),
            file=sys.stderr,
            flush=True,
        )
        if job_id and (idx + 1) % 10 == 0:
            pct = 97.0 + 2.0 * (idx + 1) / max(total, 1)
            _set_job_progress(
                job_id,
                pct,
                message="Refining lexeme {0}/{1}".format(idx + 1, total),
            )

    return additions


def _merge_ortho_words(
    aligned: List[Dict[str, Any]],
    refined: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge short-clip refined entries into the forced-alignment list.

    Refined entries replace any aligned entry whose span falls inside the
    refined ``[start, end]`` window; aligned entries not covered by any
    refined window are preserved.
    """
    if not refined:
        return list(aligned)

    def _iv_bounds(iv: Dict[str, Any]) -> Tuple[float, float]:
        return (float(iv.get("start", 0.0) or 0.0), float(iv.get("end", 0.0) or 0.0))

    kept: List[Dict[str, Any]] = []
    for a in aligned:
        a_start, a_end = _iv_bounds(a)
        covered = False
        for r in refined:
            r_start, r_end = _iv_bounds(r)
            if a_start >= r_start and a_end <= r_end:
                covered = True
                break
        if not covered:
            kept.append(a)

    combined = kept + list(refined)
    combined.sort(key=lambda iv: (float(iv.get("start", 0.0) or 0.0), float(iv.get("end", 0.0) or 0.0)))
    return combined


def _compute_speaker_ortho(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an orthographic transcript for a speaker using the razhan model.

    Runs the ORTH provider (faster-whisper with razhan/whisper-base-sdh)
    full-file against the speaker's working WAV (normalized copy preferred,
    raw source as fallback) and writes razhan's own segments to the
    ``ortho`` tier of the annotation. After the coarse tier is written, a
    Tier-2 forced-alignment pass refines the Whisper word-level timestamps
    into ``tiers.ortho_words`` for precise per-lexeme lookup in the UI.

    Payload: ``{"speaker": "Fail02", "overwrite": false, "refine_lexemes": bool?}``.

    If ``refine_lexemes`` is omitted the provider's config default (from
    ai_config.json) is used.

    Overwrite semantics differ from IPA: razhan's segmentation isn't stable
    across runs, so we can't pair segments by ``(start, end)`` the way IPA
    does. Rule: if the ortho tier already has any non-empty text intervals,
    the caller must set ``overwrite=True`` to replace the whole tier;
    otherwise the run is a no-op and returns ``skipped=True``. Empty tiers
    are always populated. When overwrite runs, ``tiers.ortho_words`` is
    always rebuilt from scratch alongside ``tiers.ortho``.
    """
    speaker = _normalize_speaker_id(payload.get("speaker"))
    overwrite = bool(payload.get("overwrite", False))
    language = payload.get("language")
    language_str = str(language).strip() if isinstance(language, str) and language.strip() else None
    refine_payload = payload.get("refine_lexemes")

    canonical_path = _project_root() / _annotation_record_relative_path(speaker)
    legacy_path = _project_root() / _annotation_legacy_record_relative_path(speaker)

    if canonical_path.is_file():
        annotation_path = canonical_path
    elif legacy_path.is_file():
        annotation_path = legacy_path
    else:
        raise RuntimeError("No annotation found for speaker {0!r}".format(speaker))

    annotation = _read_json_file(annotation_path, {})
    if not isinstance(annotation, dict):
        raise RuntimeError("Annotation is not a JSON object")

    tiers = annotation.get("tiers") or {}
    ortho_tier = tiers.get("ortho") if isinstance(tiers.get("ortho"), dict) else None
    existing_intervals: List[Dict[str, Any]] = []
    if isinstance(ortho_tier, dict):
        existing_intervals = [iv for iv in (ortho_tier.get("intervals") or []) if isinstance(iv, dict)]
    has_existing_text = any(str(iv.get("text") or "").strip() for iv in existing_intervals)

    if has_existing_text and not overwrite:
        return {
            "speaker": speaker,
            "filled": 0,
            "skipped": True,
            "reason": "ortho tier already populated; pass overwrite=True to replace",
            "existing_intervals": len(existing_intervals),
        }

    audio_path = _pipeline_audio_path_for_speaker(speaker)
    _set_job_progress(job_id, 2.0, message="Loading ortho model (razhan)")

    provider = get_ortho_provider()

    def _progress_callback(progress: float, segments_processed: int) -> None:
        clamped = min(float(progress) if progress is not None else 0.0, 94.0)
        _set_job_progress(
            job_id,
            max(2.0, clamped),
            message="ORTH transcribing ({0} segments)".format(segments_processed),
            segments_processed=segments_processed,
        )

    segments = provider.transcribe(
        audio_path=audio_path,
        language=language_str,
        progress_callback=_progress_callback,
    )

    new_intervals: List[Dict[str, Any]] = []
    for seg in segments:
        start = float(seg.get("start", 0.0) or 0.0)
        end = float(seg.get("end", start) or start)
        text = str(seg.get("text", "") or "").strip()
        if not text:
            continue
        new_intervals.append({"start": start, "end": end, "text": text})

    new_intervals.sort(key=lambda iv: (float(iv["start"]), float(iv["end"])))

    if ortho_tier is None:
        ortho_tier = {"type": "interval", "display_order": 3, "intervals": []}
    ortho_tier["intervals"] = new_intervals
    tiers["ortho"] = ortho_tier

    _set_job_progress(job_id, 95.0, message="ORTH Tier-2 forced alignment")
    ortho_words = _ortho_tier2_align_to_words(audio_path, segments)

    if refine_payload is None:
        refine_lexemes = bool(getattr(provider, "refine_lexemes", False))
    else:
        refine_lexemes = bool(refine_payload)

    refined_additions: List[Dict[str, Any]] = []
    if refine_lexemes:
        concept_tier = tiers.get("concept") if isinstance(tiers.get("concept"), dict) else None
        concept_intervals = [
            iv for iv in (concept_tier.get("intervals") or [] if concept_tier else [])
            if isinstance(iv, dict)
        ]
        if concept_intervals:
            _set_job_progress(
                job_id,
                97.0,
                message="ORTH refine_lexemes (short-clip, {0} concepts)".format(len(concept_intervals)),
            )
            refined_additions = _short_clip_refine_lexemes(
                audio_path=audio_path,
                concept_intervals=concept_intervals,
                ortho_words=ortho_words,
                provider=provider,
                job_id=job_id,
            )

    merged_words = _merge_ortho_words(ortho_words, refined_additions)

    ortho_words_tier = tiers.get("ortho_words") if isinstance(tiers.get("ortho_words"), dict) else None
    if ortho_words_tier is None:
        ortho_words_tier = {"type": "interval", "display_order": 4, "intervals": []}
    ortho_words_tier["intervals"] = merged_words
    tiers["ortho_words"] = ortho_words_tier

    annotation["tiers"] = tiers
    _annotation_touch_metadata(annotation, preserve_created=True)

    _write_json_file(annotation_path, annotation)
    if canonical_path != annotation_path:
        _write_json_file(canonical_path, annotation)
    if legacy_path != annotation_path:
        _write_json_file(legacy_path, annotation)

    _set_job_progress(
        job_id,
        99.0,
        message="ORTH written ({0} intervals, {1} word-level, {2} refined)".format(
            len(new_intervals), len(merged_words), len(refined_additions)
        ),
    )

    return {
        "speaker": speaker,
        "filled": len(new_intervals),
        "ortho_words": len(merged_words),
        "refined_lexemes": len(refined_additions),
        "refine_lexemes_enabled": refine_lexemes,
        "skipped": False,
        "replaced_existing": has_existing_text,
        "audio_path": str(audio_path),
        "total": len(new_intervals),
    }


# Canonical step identifiers recognised by the full-pipeline sequencer.
PIPELINE_STEPS: Tuple[str, ...] = ("normalize", "stt", "ortho", "ipa")


def _compute_training_job(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Stub for the wav2vec2 / IPA fine-tuning training job.

    Wired into the compute dispatcher so the frontend / API can already
    POST `/api/compute/train_ipa_model`. The actual run will delegate to
    the `ipa-phonetic-autoresearch` harness (runs in the persistent worker
    once that integration lands — GPU training will be fully supported here).
    """
    _set_job_progress(
        job_id,
        0.0,
        message="Training job accepted (persistent-worker GPU harness pending)",
    )
    return {
        "status": "pending",
        "message": "train_ipa_model not yet implemented — harness integration pending.",
        "payload_keys": sorted(list(payload.keys())) if isinstance(payload, dict) else [],
    }


def _compute_full_pipeline(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run a user-selected subset of the speaker pipeline sequentially.

    Payload::

        {
          "speaker": "Fail02",
          "steps": ["normalize", "stt", "ortho", "ipa"],
          "overwrites": {"normalize": false, "stt": false, "ortho": true, "ipa": false},
          "language": "sd"       // optional, forwarded to STT + ORTH
        }

    Steps run in canonical order (normalize → stt → ortho → ipa). Unselected
    steps are skipped silently. Overwrite flags only matter for steps whose
    prior state already has data — an unchecked "overwrite" on a populated
    tier causes that step to skip with ``skipped=True`` in its sub-result.

    **Step-level resilience:** each step runs in its own try/except. A
    failure in STT does NOT stop ORTH / IPA from being attempted for this
    speaker. Each step's result includes ``status`` (``"ok"`` /
    ``"skipped"`` / ``"error"``), and errors capture the full traceback
    for post-mortem in the UI. The pipeline job completes successfully
    even if every step failed — the caller inspects the per-step
    ``status`` field. This is a walk-away-friendly design: the user can
    kick off a batch of 10 speakers × 4 steps, come back, and see
    exactly what worked and what didn't.
    """
    speaker = _normalize_speaker_id(payload.get("speaker"))

    raw_steps = payload.get("steps")
    if raw_steps is None:
        selected = list(PIPELINE_STEPS)
    elif isinstance(raw_steps, (list, tuple)):
        selected_set = {str(s).strip().lower() for s in raw_steps if str(s).strip()}
        selected = [s for s in PIPELINE_STEPS if s in selected_set]
    else:
        raise RuntimeError("steps must be a list, got {0}".format(type(raw_steps).__name__))

    if not selected:
        return {"speaker": speaker, "steps_run": [], "results": {}, "message": "No steps selected"}

    overwrites_raw = payload.get("overwrites") or {}
    if not isinstance(overwrites_raw, dict):
        overwrites_raw = {}
    overwrites = {str(k).strip().lower(): bool(v) for k, v in overwrites_raw.items()}

    language = payload.get("language")
    language_str = (
        str(language).strip() if isinstance(language, str) and language.strip() else None
    )

    import traceback as _traceback_module

    results: Dict[str, Any] = {}
    steps_run: List[str] = []
    total = len(selected)

    def _capture_error(exc: BaseException) -> Dict[str, Any]:
        return {
            "status": "error",
            "error": str(exc),
            "traceback": _traceback_module.format_exc(),
        }

    for idx, step in enumerate(selected):
        step_base_pct = 5.0 + (idx / total) * 90.0
        _set_job_progress(
            job_id,
            step_base_pct,
            message="Pipeline step {0}/{1}: {2}".format(idx + 1, total, step),
        )

        try:
            if step == "normalize":
                source_rel = _annotation_primary_source_wav(speaker)
                if not source_rel:
                    raise RuntimeError(
                        "Cannot normalize {0!r}: no source_audio on annotation".format(speaker)
                    )
                audio_path = _resolve_project_path(source_rel)
                working_dir = _project_root() / "audio" / "working" / speaker
                normalized_path = build_normalized_output_path(audio_path, working_dir)
                if normalized_path.exists() and not overwrites.get("normalize", False):
                    results["normalize"] = {
                        "status": "skipped",
                        "reason": "normalized output already exists; overwrite=False",
                        "path": str(normalized_path.relative_to(_project_root())),
                    }
                    steps_run.append(step)
                    continue
                _run_normalize_job(job_id, speaker, source_rel)
                snapshot = _get_job_snapshot(job_id) or {}
                if str(snapshot.get("status") or "") == "error":
                    raise RuntimeError(
                        "normalize step failed: {0}".format(snapshot.get("error") or "unknown error")
                    )
                sub_result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
                results["normalize"] = {
                    "status": "ok",
                    **(dict(sub_result) if sub_result else {"done": True}),
                }
                _reset_job_to_running(job_id)
                steps_run.append(step)

            elif step == "stt":
                # Resolve the audio the same way the ORTH step does — prefer
                # the normalized working WAV, fall back to the raw source.
                cached = _latest_stt_segments_for_speaker(speaker)
                if cached and not overwrites.get("stt", False):
                    results["stt"] = {
                        "status": "skipped",
                        "reason": "STT cache already exists; overwrite=False",
                        "segments": len(cached),
                    }
                    steps_run.append(step)
                    continue
                try:
                    audio_path = _pipeline_audio_path_for_speaker(speaker)
                except (RuntimeError, FileNotFoundError) as exc:
                    raise RuntimeError("Cannot run STT for {0!r}: {1}".format(speaker, exc))
                try:
                    stt_result = _run_stt_job(job_id, speaker, str(audio_path), language_str)
                except Exception as exc:
                    raise RuntimeError("stt step failed: {0}".format(exc)) from exc
                results["stt"] = {
                    "status": "ok",
                    "segments": len(stt_result.get("segments") or []),
                    "done": True,
                }
                # _run_stt_job no longer calls _set_job_complete (dispatcher
                # owns terminal state), so we don't need _reset_job_to_running
                # before the next pipeline step.
                steps_run.append(step)

            elif step == "ortho":
                ortho_sub_payload: Dict[str, Any] = {
                    "speaker": speaker,
                    "overwrite": overwrites.get("ortho", False),
                    "language": language_str,
                }
                # Forward the batch-level refine_lexemes flag so the ORTH
                # runner's provider-config default can be overridden by the
                # compute dialog. Omit when unset so _compute_speaker_ortho
                # falls back to the provider's ai_config default.
                if payload.get("refine_lexemes") is not None:
                    ortho_sub_payload["refine_lexemes"] = bool(payload.get("refine_lexemes"))
                sub_result = _compute_speaker_ortho(job_id, ortho_sub_payload)
                # _compute_speaker_ortho returns {"skipped": True/False, ...} —
                # translate to status vocabulary shared across steps.
                if sub_result.get("skipped"):
                    results["ortho"] = {"status": "skipped", **sub_result}
                else:
                    results["ortho"] = {"status": "ok", **sub_result}
                steps_run.append(step)

            elif step == "ipa":
                sub_result = _compute_speaker_ipa(
                    job_id,
                    {"speaker": speaker, "overwrite": overwrites.get("ipa", False)},
                )
                # _compute_speaker_ipa returns counts, not skipped flag, but
                # has a "message" when there's no ortho to work from.
                if "message" in sub_result and sub_result.get("total", 0) == 0:
                    results["ipa"] = {
                        "status": "skipped",
                        "reason": sub_result["message"],
                        **sub_result,
                    }
                else:
                    results["ipa"] = {"status": "ok", **sub_result}
                steps_run.append(step)

            else:
                results[step] = {
                    "status": "error",
                    "error": "Unknown pipeline step: {0}".format(step),
                    "traceback": None,
                }

        except Exception as exc:  # noqa: BLE001 — by design, we capture every failure
            results[step] = _capture_error(exc)
            steps_run.append(step)
            # Make sure the outer job is back to "running" so subsequent
            # steps can still report progress.
            _reset_job_to_running(job_id)

    _set_job_progress(job_id, 99.0, message="Pipeline complete")

    # Roll-up counts for the report UI — saves the client from iterating.
    summary = {
        "ok": sum(1 for r in results.values() if r.get("status") == "ok"),
        "skipped": sum(1 for r in results.values() if r.get("status") == "skipped"),
        "error": sum(1 for r in results.values() if r.get("status") == "error"),
    }

    # Diagnostic tail: always land the per-step outcome on stderr so the
    # API log gives a clear post-mortem even when the frontend batch
    # report drops ``result`` (as happened on the 2026-04-23 Fail02 run).
    print(
        "[PIPELINE] speaker={0} steps={1} summary={2}".format(
            speaker, steps_run, summary
        ),
        file=sys.stderr,
        flush=True,
    )
    for step_name, step_result in results.items():
        status = step_result.get("status")
        if status == "ok":
            concise = {k: v for k, v in step_result.items() if k not in ("status", "traceback")}
            print(
                "[PIPELINE][{0}] ok {1}".format(step_name, concise),
                file=sys.stderr,
                flush=True,
            )
        elif status == "skipped":
            print(
                "[PIPELINE][{0}] skipped reason={1}".format(
                    step_name, step_result.get("reason")
                ),
                file=sys.stderr,
                flush=True,
            )
        elif status == "error":
            print(
                "[PIPELINE][{0}] ERROR {1}".format(step_name, step_result.get("error")),
                file=sys.stderr,
                flush=True,
            )
            tb = step_result.get("traceback")
            if tb:
                print(tb, file=sys.stderr, flush=True)

    return {
        "speaker": speaker,
        "steps_run": steps_run,
        "results": results,
        "summary": summary,
    }


def _reset_job_to_running(job_id: str) -> None:
    """Clear terminal-state flags on a job so later pipeline steps can report progress.

    ``_run_normalize_job`` and ``_run_stt_job`` are designed as one-shot background
    workers that call ``_set_job_complete`` on success. When we call them inline
    from the full-pipeline sequencer we need to undo that so the outer job stays
    in a ``running`` state for the next step.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not isinstance(job, dict):
            return
        job["status"] = "running"
        job["result"] = None
        job["error"] = None
        job["completed_at"] = None
        job["completed_ts"] = None



_OFFSET_DETECT_TIMEOUT_SEC_DEFAULT = 600.0


def _offset_detect_timeout_sec() -> float:
    """Hard cap on offset-detection runtime. Defaults to 10 minutes.
    Override via ``PARSE_OFFSET_DETECT_TIMEOUT_SEC``. Covers both
    ``offset_detect`` and ``offset_detect_from_pair`` — the manual path
    is normally sub-second but shares the guard for consistency."""
    try:
        raw = os.environ.get("PARSE_OFFSET_DETECT_TIMEOUT_SEC", "").strip()
        if not raw:
            return _OFFSET_DETECT_TIMEOUT_SEC_DEFAULT
        val = float(raw)
        if val <= 0 or not math.isfinite(val):
            return _OFFSET_DETECT_TIMEOUT_SEC_DEFAULT
        return val
    except (TypeError, ValueError):
        return _OFFSET_DETECT_TIMEOUT_SEC_DEFAULT


def _enforce_offset_deadline(deadline: float, label: str) -> None:
    """Raise TimeoutError if ``deadline`` (monotonic sec) has passed.

    Called at progress checkpoints inside the offset compute functions.
    Doesn't interrupt in-flight work on its own — Python can't kill a
    thread mid-numerics — but guarantees the UI gets a clean "timed out"
    error with the full traceback instead of an indefinite detecting
    modal. The compute worker survives the TimeoutError like any other
    raised exception (worker_main's try/except captures + emits it)."""
    if time.monotonic() > deadline:
        raise TimeoutError(
            "Offset detection exceeded {0:.0f}s hard timeout at stage '{1}'. "
            "Raise PARSE_OFFSET_DETECT_TIMEOUT_SEC if your corpus legitimately "
            "needs more time.".format(_offset_detect_timeout_sec(), label)
        )


def _compute_offset_detect(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compute-dispatcher adapter for timestamp offset detection.

    Runs the lightweight pure-Python offset algorithm asynchronously so the
    header progress bar appears while annotation and STT data are correlated.
    No GPU work — intentionally CPU-only.
    """
    deadline = time.monotonic() + _offset_detect_timeout_sec()
    speaker = str(payload.get("speaker") or "").strip()
    if not speaker:
        raise ValueError("offset_detect payload missing 'speaker'")

    try:
        n_anchors = max(2, min(50, int(payload.get("nAnchors") or payload.get("n_anchors") or 12)))
    except (TypeError, ValueError):
        n_anchors = 12

    try:
        bucket_sec = max(0.1, float(payload.get("bucketSec") or payload.get("bucket_sec") or 1.0))
    except (TypeError, ValueError):
        bucket_sec = 1.0

    try:
        min_match_score = max(
            0.0,
            min(1.0, float(payload.get("minMatchScore") or payload.get("min_match_score") or 0.56)),
        )
    except (TypeError, ValueError):
        min_match_score = 0.56

    distribution_raw = str(
        payload.get("distribution") or payload.get("anchorDistribution") or "quantile"
    ).strip().lower()
    if distribution_raw not in {"quantile", "earliest"}:
        distribution_raw = "quantile"

    _set_job_progress(job_id, 10, message="Loading annotation")
    annotation_path = _annotation_read_path_for_speaker(speaker)
    annotation = _normalize_annotation_record(_read_json_any_file(annotation_path), speaker)
    intervals = _annotation_offset_anchor_intervals(annotation)
    if not intervals:
        raise ValueError(
            "Speaker '{0}' has no annotated intervals to use as offset anchors".format(speaker)
        )

    _set_job_progress(job_id, 25, message="Resolving STT segments")
    stt_segments_payload = payload.get("sttSegments") or payload.get("stt_segments")
    stt_job_id = str(payload.get("sttJobId") or payload.get("stt_job_id") or "").strip()

    if stt_segments_payload is None and stt_job_id:
        stt_job = _get_job_snapshot(stt_job_id)
        if stt_job is None:
            raise ValueError("Unknown sttJobId: {0}".format(stt_job_id))
        if str(stt_job.get("type") or "") != "stt":
            raise ValueError("sttJobId is not an STT job")
        if str(stt_job.get("status") or "") != "complete":
            raise ValueError("STT job has not completed")
        stt_result = stt_job.get("result") if isinstance(stt_job.get("result"), dict) else {}
        stt_segments_payload = stt_result.get("segments")

    if stt_segments_payload is None:
        stt_segments_payload = _latest_stt_segments_for_speaker(speaker)

    if not stt_segments_payload:
        raise ValueError(
            "No STT segments available. Run STT first or pass sttJobId / sttSegments."
        )

    from compare import (
        anchors_from_intervals as _anchors_from_intervals,
        detect_offset_detailed as _detect_offset_detailed,
        load_rules_from_file as _load_rules,
        segments_from_raw as _segments_from_raw,
    )

    _set_job_progress(job_id, 40, message="Loading phonetic rules")
    rules_path = _project_root() / "config" / "phonetic_rules.json"
    try:
        rules = _load_rules(rules_path) if rules_path.exists() else []
    except Exception:
        rules = []

    _set_job_progress(job_id, 55, message="Selecting anchors")
    anchors = _anchors_from_intervals(intervals, n_anchors, distribution=distribution_raw)
    if not anchors:
        raise ValueError("No usable anchors with both timestamp and text in annotation")

    _set_job_progress(job_id, 65, message="Parsing STT segments")
    segments = _segments_from_raw(stt_segments_payload)
    if not segments:
        raise ValueError("STT input contained no usable segments")

    _enforce_offset_deadline(deadline, "pre-match")
    _set_job_progress(job_id, 75, message="Computing timestamp offset")
    try:
        detailed = _detect_offset_detailed(
            anchors=anchors,
            segments=segments,
            rules=rules,
            bucket_sec=bucket_sec,
            min_match_score=min_match_score,
        )
    except ValueError as exc:
        raise ValueError("Offset detection failed: {0}".format(exc)) from exc

    _enforce_offset_deadline(deadline, "post-match")
    _set_job_progress(job_id, 92, message="Finalizing result")
    return _offset_detect_payload(
        speaker=speaker,
        offset_sec=float(detailed.offset_sec),
        confidence=float(detailed.confidence),
        n_matched=int(detailed.n_matched),
        total_anchors=len(anchors),
        total_segments=len(segments),
        method=detailed.method,
        spread_sec=float(detailed.spread_sec),
        matches=detailed.matches,
        anchor_distribution=distribution_raw,
    )


def _compute_offset_detect_from_pair(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compute-dispatcher adapter for manual-pair timestamp offset detection.

    Accepts one or more (audioTimeSec, csvTimeSec/conceptId) pairs and returns
    the median offset. Pure arithmetic — no STT or GPU work.
    """
    deadline = time.monotonic() + _offset_detect_timeout_sec()
    speaker = str(payload.get("speaker") or "").strip()
    if not speaker:
        raise ValueError("offset_detect_from_pair payload missing 'speaker'")

    raw_pairs: Any = payload.get("pairs")
    if raw_pairs is None:
        raw_pairs = [
            {
                "audioTimeSec": payload.get("audioTimeSec") or payload.get("audio_time_sec"),
                "csvTimeSec": payload.get("csvTimeSec") or payload.get("csv_time_sec"),
                "conceptId": payload.get("conceptId") or payload.get("concept_id"),
            }
        ]
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise ValueError("pairs must be a non-empty list")

    _set_job_progress(job_id, 20, message="Validating pairs")

    annotation_cache: Optional[Dict[str, Any]] = None

    def _get_annotation() -> Dict[str, Any]:
        nonlocal annotation_cache
        if annotation_cache is None:
            annotation_cache = _normalize_annotation_record(
                _read_json_any_file(_annotation_read_path_for_speaker(speaker)), speaker
            )
        return annotation_cache

    matches: List[Dict[str, Any]] = []
    offsets: List[float] = []

    for raw in raw_pairs:
        if not isinstance(raw, dict):
            raise ValueError("Each pair must be a JSON object")

        audio_raw = raw.get("audioTimeSec")
        if audio_raw is None:
            audio_raw = raw.get("audio_time_sec")
        try:
            audio_time = float(audio_raw)
        except (TypeError, ValueError):
            raise ValueError("Each pair needs a numeric audioTimeSec")
        if not math.isfinite(audio_time) or audio_time < 0:
            raise ValueError("audioTimeSec must be finite and non-negative")

        csv_raw = raw.get("csvTimeSec")
        if csv_raw is None:
            csv_raw = raw.get("csv_time_sec")
        concept_raw = raw.get("conceptId") or raw.get("concept_id")

        anchor_csv_time: Optional[float] = None
        anchor_label: Optional[str] = None

        if csv_raw is not None and (not isinstance(csv_raw, str) or csv_raw.strip() != ""):
            try:
                anchor_csv_time = float(csv_raw)
            except (TypeError, ValueError):
                raise ValueError("csvTimeSec must be a number when provided")
            if not math.isfinite(anchor_csv_time) or anchor_csv_time < 0:
                raise ValueError("csvTimeSec must be finite and non-negative")
            anchor_label = "csvTimeSec={0:.3f}s".format(anchor_csv_time)
        elif concept_raw is not None and str(concept_raw).strip():
            concept_id = str(concept_raw).strip()
            interval = _annotation_find_concept_interval(_get_annotation(), concept_id)
            if interval is None:
                raise ValueError(
                    "No annotation interval found for concept '{0}'".format(concept_id)
                )
            anchor_csv_time = float(interval["start"])
            anchor_label = "concept '{0}' @ {1:.3f}s".format(concept_id, anchor_csv_time)
        else:
            raise ValueError("Each pair needs either csvTimeSec or conceptId")

        pair_offset = round(audio_time - float(anchor_csv_time), 3)
        offsets.append(pair_offset)
        matches.append(
            {
                "anchor_index": -1,
                "anchor_text": anchor_label or "",
                "anchor_start": float(anchor_csv_time),
                "segment_index": -1,
                "segment_text": "(user-supplied audio time)",
                "segment_start": float(audio_time),
                "score": 1.0,
                "offset_sec": pair_offset,
            }
        )

    _enforce_offset_deadline(deadline, "pre-median")
    _set_job_progress(job_id, 75, message="Computing median offset")
    import statistics as _statistics

    median_offset = round(_statistics.median(offsets), 3)
    if len(offsets) >= 2:
        deviations = [abs(o - median_offset) for o in offsets]
        spread = round(_statistics.median(deviations), 3)
        max_deviation = max(deviations)
        confidence = max(0.5, min(0.99, 0.99 - (max_deviation / 60.0)))
    else:
        spread = 0.0
        confidence = 0.99

    _set_job_progress(job_id, 92, message="Finalizing result")
    return _offset_detect_payload(
        speaker=speaker,
        offset_sec=median_offset,
        confidence=float(confidence),
        n_matched=len(matches),
        total_anchors=len(matches),
        total_segments=0,
        method="manual_pair",
        spread_sec=float(spread),
        matches=matches,
        anchor_distribution="manual",
    )

def _run_compute_job(job_id: str, compute_type: str, payload: Dict[str, Any]) -> None:
    # Diagnostics v3: belt-and-suspenders observability.
    #   - stderr print for humans watching the log
    #   - checkpoint file for buffer-safe post-mortem (see
    #     ``_compute_checkpoint`` for why Windows-python.exe stderr is
    #     unreliable)
    _compute_checkpoint("COMPUTE.entry", job_id=job_id, compute_type=compute_type)
    print(
        "[COMPUTE] _run_compute_job entry job_id={0} compute_type={1} payload={2}".format(
            job_id, compute_type, payload
        ),
        file=sys.stderr,
        flush=True,
    )
    try:
        normalized_type = str(compute_type or "").strip().lower()
        _set_job_progress(job_id, 5.0, message="Starting compute job")
        _compute_checkpoint("COMPUTE.dispatch", job_id=job_id, normalized=normalized_type)
        print(
            "[COMPUTE] dispatching normalized_type={0}".format(normalized_type),
            file=sys.stderr,
            flush=True,
        )

        if normalized_type in {"cognates", "similarity"}:
            result = _compute_cognates(job_id, payload)
        elif normalized_type == "contact-lexemes":
            result = _compute_contact_lexemes(job_id, payload)
        elif normalized_type in {"ipa_only", "ipa-only", "ipa"}:
            result = _compute_speaker_ipa(job_id, payload)
        elif normalized_type in {"ortho", "ortho_only", "ortho-only"}:
            result = _compute_speaker_ortho(job_id, payload)
        elif normalized_type in {"forced_align", "forced-align", "align"}:
            result = _compute_speaker_forced_align(job_id, payload)
        elif normalized_type in {"full_pipeline", "full-pipeline", "pipeline"}:
            result = _compute_full_pipeline(job_id, payload)
        elif normalized_type in {"train_ipa_model", "train-ipa-model", "train_ipa"}:
            result = _compute_training_job(job_id, payload)
        elif normalized_type == "stt":
            result = _compute_stt(job_id, payload)
        elif normalized_type in {"offset_detect", "offset-detect"}:
            result = _compute_offset_detect(job_id, payload)
        elif normalized_type in {"offset_detect_from_pair", "offset-detect-from-pair"}:
            result = _compute_offset_detect_from_pair(job_id, payload)
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
        if self._handle_builtin_docs_get():
            return
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

    def _request_query_params(self) -> Dict[str, List[str]]:
        return parse_qs(urlparse(self.path).query, keep_blank_values=True)

    def _request_base_url(self) -> str:
        host = str(self.headers.get("Host") or "127.0.0.1:{0}".format(PORT)).strip() or "127.0.0.1:{0}".format(PORT)
        return "http://{0}".format(host)

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

    def _send_text(self, status: HTTPStatus, body: str, *, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except BrokenPipeError:
            pass

    def _send_json_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": str(message)})

    def _handle_builtin_docs_get(self) -> bool:
        request_path = self._request_path()
        if request_path == "/openapi.json":
            self._send_json(HTTPStatus.OK, build_openapi_document(base_url=self._request_base_url()))
            return True
        if request_path == "/docs":
            self._send_text(HTTPStatus.OK, render_swagger_ui_html("/openapi.json"), content_type="text/html; charset=utf-8")
            return True
        if request_path == "/redoc":
            self._send_text(HTTPStatus.OK, render_redoc_html("/openapi.json"), content_type="text/html; charset=utf-8")
            return True
        return False

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

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "stt-segments":
            self._api_get_stt_segments(parts[2])
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "pipeline" and parts[2] == "state":
            self._api_get_pipeline_state(parts[3])
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "chat" and parts[2] == "session":
            self._api_get_chat_session(parts[3])
            return

        if request_path == "/api/mcp/exposure":
            self._api_get_mcp_exposure()
            return

        if request_path == "/api/mcp/tools":
            self._api_get_mcp_tools()
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "mcp" and parts[2] == "tools":
            self._api_get_mcp_tool(parts[3])
            return

        if request_path == "/api/jobs":
            self._api_get_jobs()
            return

        if request_path == "/api/jobs/active":
            self._api_get_jobs_active()
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "logs":
            self._api_get_job_logs(parts[2])
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "jobs":
            self._api_get_job(parts[2])
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

        if request_path == "/api/worker/status":
            self._api_get_worker_status()
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

        if request_path == "/api/spectrogram":
            self._api_get_spectrogram()
            return

        if request_path == "/api/lexeme/search":
            self._api_get_lexeme_search()
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

        if request_path == "/api/concepts/import":
            self._api_post_concepts_import()
            return

        if request_path == "/api/tags/import":
            self._api_post_tags_import()
            return

        if request_path == "/api/lexeme-notes":
            self._api_post_lexeme_note()
            return

        if request_path == "/api/lexeme-notes/import":
            self._api_post_lexeme_notes_import()
            return

        if request_path == "/api/offset/detect":
            self._api_post_offset_detect()
            return

        if request_path == "/api/offset/detect-from-pair":
            self._api_post_offset_detect_from_pair()
            return

        if request_path == "/api/offset/apply":
            self._api_post_offset_apply()
            return

        parts = self._path_parts(request_path)

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "mcp" and parts[2] == "tools":
            self._api_post_mcp_tool(parts[3])
            return

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

    def _api_get_stt_segments(self, speaker_part: str) -> None:
        """Return cached STT segments for a speaker.

        Reads ``coarse_transcripts/<speaker>.json`` — the cache seeded by
        ``_run_stt_job`` and also used by ``/api/offset/detect``. Always
        returns HTTP 200 with ``{"speaker", "source_wav", "language",
        "segments"}``; missing cache yields ``segments: []``. The frontend
        treats an empty array as "run STT first" — keeping the response
        uniform avoids noisy 404s in the console on every speaker switch.
        """
        try:
            speaker = _normalize_speaker_id(speaker_part)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        cache_path = _stt_cache_path(speaker)
        if not cache_path.exists():
            self._send_json(HTTPStatus.OK, {"speaker": speaker, "segments": []})
            return
        try:
            with open(cache_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "Failed to read STT cache: {0}".format(exc))
        if not isinstance(data, dict):
            data = {"speaker": speaker, "segments": []}
        data.setdefault("speaker", speaker)
        segments = data.get("segments") if isinstance(data.get("segments"), list) else []
        data["segments"] = segments
        self._send_json(HTTPStatus.OK, data)

    def _api_get_pipeline_state(self, speaker_part: str) -> None:
        """Return per-step pipeline state for a speaker.

        Drives the pre-flight checklist modal shown before ``Run Full Pipeline``.
        Shape is documented on ``_pipeline_state_for_speaker``.
        """
        try:
            speaker = _normalize_speaker_id(speaker_part)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))
        try:
            payload = _pipeline_state_for_speaker(speaker)
        except Exception as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
        self._send_json(HTTPStatus.OK, payload)

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
        try:
            job_id = _create_job(
                "onboard:speaker",
                {
                    "speaker": speaker,
                    "wavPath": str(wav_dest.relative_to(_project_root())),
                    "csvPath": str(csv_dest.relative_to(_project_root())) if csv_dest else None,
                },
            )
        except JobResourceConflictError as exc:
            raise ApiError(HTTPStatus.CONFLICT, str(exc))

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
        callback_url = _job_callback_url_from_mapping(body)
        if not source_wav:
            source_wav = _annotation_primary_source_wav(speaker)

        if not source_wav:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "No source audio found for speaker '{0}'. Provide sourceWav explicitly.".format(speaker),
            )

        try:
            job_id = _create_job(
                "normalize",
                {
                    "speaker": speaker,
                    "sourceWav": source_wav,
                    "callbackUrl": callback_url,
                },
            )
        except JobResourceConflictError as exc:
            raise ApiError(HTTPStatus.CONFLICT, str(exc))

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

    def _api_post_offset_detect(self) -> None:
        """Submit a compute job to detect a constant timestamp offset for a speaker.

        Validates the speaker field, then queues the detection as a compute job
        and returns the job_id immediately. The caller should poll
        POST /api/compute/offset_detect/status with {jobId} to track progress
        and retrieve the OffsetDetectResult from result when done.

        All original options (nAnchors, bucketSec, minMatchScore, distribution,
        sttJobId, sttSegments) are forwarded to the compute function unchanged.
        """
        body = self._expect_object(self._read_json_body(), "Request body")

        try:
            speaker = _normalize_speaker_id(body.get("speaker"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        compute_payload: Dict[str, Any] = {
            "speaker": speaker,
            "nAnchors": body.get("nAnchors") or body.get("n_anchors"),
            "bucketSec": body.get("bucketSec") or body.get("bucket_sec"),
            "minMatchScore": body.get("minMatchScore") or body.get("min_match_score"),
            "distribution": body.get("distribution") or body.get("anchorDistribution"),
            "sttJobId": body.get("sttJobId") or body.get("stt_job_id"),
            "sttSegments": body.get("sttSegments") or body.get("stt_segments"),
        }

        job_id = _create_job("compute:offset_detect", {"speaker": speaker})
        _launch_compute_runner(job_id, "offset_detect", compute_payload)
        self._send_json(HTTPStatus.OK, {"jobId": job_id, "status": "running"})

    def _api_post_offset_detect_from_pair(self) -> None:
        """Submit a compute job to detect offset from manual (csv_time, audio_time) pairs.

        Accepts the same body shapes as before (single pair or pairs array),
        queues the arithmetic as a compute job, and returns the job_id immediately.
        Poll POST /api/compute/offset_detect_from_pair/status with {jobId} to
        retrieve the OffsetDetectResult from result when the job completes.

        Body shapes accepted:
            Single: {speaker, audioTimeSec, csvTimeSec? | conceptId?}
            Multi:  {speaker, pairs: [{audioTimeSec, csvTimeSec? | conceptId?}, ...]}
        """
        body = self._expect_object(self._read_json_body(), "Request body")

        try:
            speaker = _normalize_speaker_id(body.get("speaker"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        raw_pairs = body.get("pairs")
        if raw_pairs is None:
            raw_pairs = [
                {
                    "audioTimeSec": body.get("audioTimeSec") or body.get("audio_time_sec"),
                    "csvTimeSec": body.get("csvTimeSec") or body.get("csv_time_sec"),
                    "conceptId": body.get("conceptId") or body.get("concept_id"),
                }
            ]
        if not isinstance(raw_pairs, list) or not raw_pairs:
            raise ApiError(HTTPStatus.BAD_REQUEST, "pairs must be a non-empty array")

        compute_payload: Dict[str, Any] = {"speaker": speaker, "pairs": raw_pairs}
        job_id = _create_job("compute:offset_detect_from_pair", {"speaker": speaker})
        _launch_compute_runner(job_id, "offset_detect_from_pair", compute_payload)
        self._send_json(HTTPStatus.OK, {"jobId": job_id, "status": "running"})

    def _api_post_offset_apply(self) -> None:
        """Shift every annotation interval by ``offsetSec`` (start/end += offset).

        For the typical "WAV missing leading audio" case the detected offset is
        negative, so applying it pulls every CSV-sourced timestamp earlier so
        the lexemes line up with the truncated recording.
        """
        body = self._expect_object(self._read_json_body(), "Request body")

        try:
            speaker = _normalize_speaker_id(body.get("speaker"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        offset_raw = body.get("offsetSec")
        if offset_raw is None:
            offset_raw = body.get("offset_sec")
        if offset_raw is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "offsetSec is required")

        try:
            offset_sec = float(offset_raw)
        except (TypeError, ValueError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "offsetSec must be a number")

        if not math.isfinite(offset_sec):
            raise ApiError(HTTPStatus.BAD_REQUEST, "offsetSec must be a finite number")

        if abs(offset_sec) < 1e-6:
            raise ApiError(HTTPStatus.BAD_REQUEST, "offsetSec is effectively zero — nothing to apply")

        annotation_path = _annotation_read_path_for_speaker(speaker)
        annotation = _normalize_annotation_record(_read_json_any_file(annotation_path), speaker)

        shifted_count, protected_count = _annotation_shift_intervals(
            annotation, offset_sec
        )
        if shifted_count == 0 and protected_count == 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "No intervals were shifted")

        # "Lexemes" ≈ unique (start,end) pairs on the concept tier — this is
        # the user-facing count in the Review & apply modal. ``protected_count``
        # above sums every interval row on every tier (ipa/ortho/speaker…)
        # which would be ~4× larger and confusing.
        protected_lexemes = 0
        concept_tier = annotation.get("tiers", {}).get("concept") if isinstance(annotation, dict) else None
        if isinstance(concept_tier, dict):
            concept_intervals = concept_tier.get("intervals")
            if isinstance(concept_intervals, list):
                protected_lexemes = sum(
                    1
                    for iv in concept_intervals
                    if isinstance(iv, dict) and bool(iv.get("manuallyAdjusted"))
                )

        if shifted_count > 0:
            _annotation_touch_metadata(annotation, preserve_created=True)
            write_path = _annotation_record_path_for_speaker(speaker)
            _write_json_file(write_path, annotation)

        self._send_json(
            HTTPStatus.OK,
            {
                "speaker": speaker,
                "appliedOffsetSec": offset_sec,
                "shiftedIntervals": shifted_count,
                "protectedIntervals": protected_count,
                "protectedLexemes": protected_lexemes,
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

    def _api_get_jobs(self) -> None:
        query = urlparse(self.path).query
        params = {}
        for piece in query.split("&"):
            if not piece or "=" not in piece:
                continue
            key, value = piece.split("=", 1)
            params.setdefault(key, []).append(unquote(value))

        statuses = params.get("status") or params.get("statuses")
        job_types = params.get("type") or params.get("types")
        speaker = (params.get("speaker") or [None])[0]
        limit_raw = (params.get("limit") or ["100"])[0]
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 100

        rows = _list_jobs_snapshots(
            statuses=statuses,
            job_types=job_types,
            speaker=speaker,
            limit=limit,
        )
        self._send_json(HTTPStatus.OK, {"jobs": rows, "count": len(rows)})

    def _api_get_job(self, job_id_part: str) -> None:
        job_id = str(job_id_part or "").strip()
        if not job_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId is required")
        job = _get_job_snapshot(job_id)
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown jobId")
        self._send_json(HTTPStatus.OK, _job_detail_payload(job))

    def _api_get_job_logs(self, job_id_part: str) -> None:
        job_id = str(job_id_part or "").strip()
        if not job_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "jobId is required")
        job = _get_job_snapshot(job_id)
        if job is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown jobId")
        query = urlparse(self.path).query
        offset = 0
        limit = _job_log_limit()
        for piece in query.split("&"):
            if not piece or "=" not in piece:
                continue
            key, value = piece.split("=", 1)
            if key == "offset":
                try:
                    offset = int(unquote(value))
                except (TypeError, ValueError):
                    offset = 0
            elif key == "limit":
                try:
                    limit = int(unquote(value))
                except (TypeError, ValueError):
                    limit = JOB_LOG_MAX_ENTRIES
        self._send_json(HTTPStatus.OK, _job_logs_payload(job, offset=offset, limit=limit))

    def _api_get_jobs_active(self) -> None:
        """Return a list of currently-running jobs so the UI can rehydrate
        progress after a page reload. See ``_list_active_jobs_snapshots``."""
        self._send_json(HTTPStatus.OK, {"jobs": _list_active_jobs_snapshots()})

    def _api_get_job_error_logs(self, job_id: str) -> None:
        """Return the error, traceback, and tail of any stderr log files
        associated with a job. Powers the UI's "View crash log" modal.

        Reads from two places:
          1. The in-memory job record — ``error`` (short reason) and
             ``traceback`` (full Python traceback), when the job failed.
          2. The per-job stderr log written by ``_compute_subprocess_entry``
             at ``/tmp/parse-compute-<job_id>.stderr.log`` and the shared
             persistent-worker log at ``/tmp/parse-compute-worker.stderr.log``.
             Only the last ~200 lines of each are returned so a runaway
             log doesn't bloat the response.

        Response shape: ``{jobId, status, type, error?, traceback?,
        message?, stderrLog?, workerStderrLog?}``. All log fields are
        omitted when unavailable — the UI renders whatever is present.
        """
        snapshot = _get_job_snapshot(job_id)
        if snapshot is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown job_id")

        payload: Dict[str, Any] = {
            "jobId": job_id,
            "status": str(snapshot.get("status") or ""),
            "type": str(snapshot.get("type") or ""),
        }
        if snapshot.get("error"):
            payload["error"] = str(snapshot.get("error"))
        if snapshot.get("traceback"):
            payload["traceback"] = str(snapshot.get("traceback"))
        if snapshot.get("message"):
            payload["message"] = str(snapshot.get("message"))

        job_stderr = _tail_log_file(
            "/tmp/parse-compute-{0}.stderr.log".format(job_id), max_lines=200
        )
        if job_stderr:
            payload["stderrLog"] = job_stderr

        worker_stderr = _tail_log_file(
            "/tmp/parse-compute-worker.stderr.log", max_lines=200
        )
        if worker_stderr:
            payload["workerStderrLog"] = worker_stderr

        self._send_json(HTTPStatus.OK, payload)

    def _api_get_worker_status(self) -> None:
        """Health check for the persistent compute worker.

        Returns 200 with ``{mode, alive, pid, jobs_in_flight}`` when the
        worker is healthy (persistent mode + process alive) or when
        persistent mode is not active (thread/subprocess modes always
        report ``alive: null`` since there is no long-lived worker to
        probe). Returns 503 when persistent mode is active but the
        worker has exited — suitable for an external monitor (PM2,
        uptime-robot, Grafana) to trigger a restart.
        """
        mode = _resolve_compute_mode()
        payload: Dict[str, Any] = {"mode": mode}

        if mode != "persistent":
            payload["alive"] = None
            payload["message"] = "Persistent worker mode is not active"
            self._send_json(HTTPStatus.OK, payload)
            return

        handle = _PERSISTENT_WORKER_HANDLE
        if handle is None:
            payload["alive"] = False
            payload["message"] = "Persistent worker handle not initialised"
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, payload)
            return

        alive = handle.is_alive()
        payload["alive"] = alive
        payload["pid"] = handle.process_pid()
        payload["jobs_in_flight"] = handle.in_flight_count()
        if alive:
            self._send_json(HTTPStatus.OK, payload)
            return
        payload["message"] = "Persistent worker process has exited"
        self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, payload)

    def _api_post_stt_start(self) -> None:
        body = self._expect_object(self._read_json_body(), "Request body")
        speaker = str(body.get("speaker") or "").strip()
        source_wav = str(body.get("sourceWav") or body.get("source_wav") or "").strip()

        language_raw = body.get("language")
        language = str(language_raw).strip() if language_raw is not None else None
        if language == "":
            language = None
        callback_url = _job_callback_url_from_mapping(body)

        if not speaker:
            raise ApiError(HTTPStatus.BAD_REQUEST, "speaker is required")
        if not source_wav:
            raise ApiError(HTTPStatus.BAD_REQUEST, "sourceWav is required")

        try:
            job_id = _create_job(
                "stt",
                {
                    "speaker": speaker,
                    "sourceWav": source_wav,
                    "language": language,
                    "callbackUrl": callback_url,
                },
            )
        except JobResourceConflictError as exc:
            raise ApiError(HTTPStatus.CONFLICT, str(exc))

        _launch_compute_runner(
            job_id, "stt",
            {"speaker": speaker, "sourceWav": source_wav, "language": language},
        )

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

    def _api_get_mcp_exposure(self) -> None:
        try:
            mode = resolve_catalog_mode((self._request_query_params().get("mode") or ["active"])[0])
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        catalog = build_mcp_http_catalog(project_root=_project_root(), mode=mode, parse_tools=_get_chat_runtime()[0], workflow_tools=_build_workflow_runtime())
        self._send_json(HTTPStatus.OK, catalog["exposure"])

    def _api_get_mcp_tools(self) -> None:
        try:
            mode = resolve_catalog_mode((self._request_query_params().get("mode") or ["active"])[0])
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        catalog = build_mcp_http_catalog(project_root=_project_root(), mode=mode, parse_tools=_get_chat_runtime()[0], workflow_tools=_build_workflow_runtime())
        self._send_json(HTTPStatus.OK, catalog)

    def _api_get_mcp_tool(self, tool_name: str) -> None:
        try:
            mode = resolve_catalog_mode((self._request_query_params().get("mode") or ["active"])[0])
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        tool_entry = get_mcp_tool_entry(
            tool_name,
            project_root=_project_root(),
            mode=mode,
            parse_tools=_get_chat_runtime()[0],
            workflow_tools=_build_workflow_runtime(),
        )
        if tool_entry is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Unknown MCP tool: {0}".format(tool_name))
        self._send_json(HTTPStatus.OK, tool_entry)

    def _api_post_mcp_tool(self, tool_name: str) -> None:
        try:
            mode = resolve_catalog_mode((self._request_query_params().get("mode") or ["active"])[0])
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        body = self._expect_object(self._read_json_body(required=False) or {}, "Request body")
        self._send_json(HTTPStatus.OK, _execute_mcp_http_tool(tool_name, body, mode=mode))

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
        callback_url = _job_callback_url_from_mapping(body)

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
                "callbackUrl": callback_url,
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
        callback_url = _job_callback_url_from_mapping(body_obj)

        speaker = str(body_obj.get("speaker") or "").strip() or None
        job_metadata = {
            "computeType": normalized_type,
            "payload": body_obj,
            "callbackUrl": callback_url,
        }
        if speaker:
            job_metadata["speaker"] = speaker

        try:
            job_id = _create_job(
                "compute:{0}".format(normalized_type),
                job_metadata,
            )
        except JobResourceConflictError as exc:
            raise ApiError(HTTPStatus.CONFLICT, str(exc))

        _launch_compute_runner(job_id, normalized_type, body_obj)

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

    # ── Lexeme notes (per speaker + concept) ────────────────────────

    def _api_post_lexeme_note(self) -> None:
        """Write a single lexeme-level note into parse-enrichments.json."""
        body = self._expect_object(self._read_json_body(required=True), "Request body")
        speaker_raw = str(body.get("speaker") or "").strip()
        concept_id = _normalize_concept_id(body.get("concept_id"))
        if not speaker_raw or not concept_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "speaker and concept_id are required")
        try:
            speaker = _normalize_speaker_id(speaker_raw)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        payload = _read_json_file(_enrichments_path(), _default_enrichments_payload())
        notes_block = payload.get("lexeme_notes")
        if not isinstance(notes_block, dict):
            notes_block = {}
            payload["lexeme_notes"] = notes_block
        speaker_block = notes_block.get(speaker)
        if not isinstance(speaker_block, dict):
            speaker_block = {}
            notes_block[speaker] = speaker_block

        if body.get("delete") is True:
            speaker_block.pop(concept_id, None)
            if not speaker_block:
                notes_block.pop(speaker, None)
        else:
            entry = speaker_block.get(concept_id)
            if not isinstance(entry, dict):
                entry = {}
            if "user_note" in body:
                entry["user_note"] = str(body.get("user_note") or "")
            if "import_note" in body:
                entry["import_note"] = str(body.get("import_note") or "")
            entry["updated_at"] = _utc_now_iso()
            speaker_block[concept_id] = entry

        _write_json_file(_enrichments_path(), payload)
        self._send_json(HTTPStatus.OK, {
            "success": True,
            "lexeme_notes": payload.get("lexeme_notes") or {},
        })

    def _api_post_lexeme_notes_import(self) -> None:
        """Multipart POST — parse Audition comments CSV into lexeme_notes."""
        from lexeme_notes import parse_audition_csv, match_rows_to_lexemes

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Type must be multipart/form-data")

        raw_length = self.headers.get("Content-Length", "")
        try:
            content_length = int(raw_length)
        except (ValueError, TypeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Length header is required")
        if content_length > ONBOARD_MAX_UPLOAD_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload exceeds limit")

        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(content_length),
        }
        form = cgi.FieldStorage(
            fp=self.rfile, headers=self.headers, environ=environ, keep_blank_values=True,
        )

        speaker_field = form.getfirst("speaker_id", "") if "speaker_id" in form else ""
        if isinstance(speaker_field, bytes):
            speaker_field = speaker_field.decode("utf-8", errors="replace")
        try:
            speaker = _normalize_speaker_id(str(speaker_field or "").strip())
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        csv_item = form["csv"] if "csv" in form else None
        if csv_item is None or not getattr(csv_item, "filename", None):
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv file is required (field name: csv)")
        try:
            csv_text = csv_item.file.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv must be UTF-8: {0}".format(exc))

        rows = parse_audition_csv(csv_text)
        if not rows:
            self._send_json(HTTPStatus.OK, {
                "success": True, "imported": 0, "matched": 0, "total_rows": 0,
            })
            return

        annotation_path = _annotation_read_path_for_speaker(speaker)
        annotation_payload = _read_json_any_file(annotation_path)
        normalized = _normalize_annotation_record(annotation_payload, speaker)
        tiers = normalized.get("tiers") or {}
        concept_tier = tiers.get("concept") if isinstance(tiers, dict) else None
        intervals: List[Dict[str, Any]] = []
        if isinstance(concept_tier, dict):
            for iv in concept_tier.get("intervals") or []:
                if not isinstance(iv, dict):
                    continue
                cid = _normalize_concept_id(iv.get("text"))
                if not cid:
                    continue
                try:
                    start = float(iv.get("start") or 0.0)
                    end = float(iv.get("end") or 0.0)
                except (TypeError, ValueError):
                    continue
                intervals.append({"concept_id": cid, "start": start, "end": end})

        concept_labels: Dict[str, str] = {}
        survey_to_id: Dict[str, str] = {}
        try:
            import csv as _csv
            concepts_path = _project_root() / "concepts.csv"
            if concepts_path.exists():
                with open(concepts_path, newline="", encoding="utf-8") as fh:
                    for row in _csv.DictReader(fh):
                        cid = _normalize_concept_id(row.get("id"))
                        label = str(row.get("concept_en") or "").strip()
                        survey = str(row.get("survey_item") or "").strip()
                        if cid and label:
                            concept_labels[cid] = label
                        if cid and survey:
                            m = re.match(r"^[A-Za-z]+_([0-9]+(?:\.[0-9]+)?)", survey)
                            if m:
                                key = m.group(1)
                                survey_to_id.setdefault(key, cid)
                                concept_labels.setdefault(key, label)
        except Exception:
            concept_labels = {}
            survey_to_id = {}

        matches = match_rows_to_lexemes(rows, intervals, concept_labels=concept_labels)
        label_to_id = {lbl.lower(): cid for cid, lbl in concept_labels.items() if cid.isdigit()}
        for row, match in zip(rows, matches):
            csv_id = _normalize_concept_id(row.concept_id)
            if csv_id in survey_to_id:
                match["concept_id"] = survey_to_id[csv_id]
                continue
            current = _normalize_concept_id(match.get("concept_id"))
            if current.isdigit():
                continue
            if current.lower() in label_to_id:
                match["concept_id"] = label_to_id[current.lower()]

        payload = _read_json_file(_enrichments_path(), _default_enrichments_payload())
        notes_block = payload.get("lexeme_notes")
        if not isinstance(notes_block, dict):
            notes_block = {}
            payload["lexeme_notes"] = notes_block
        speaker_block = notes_block.get(speaker)
        if not isinstance(speaker_block, dict):
            speaker_block = {}
            notes_block[speaker] = speaker_block

        imported = 0
        for match in matches:
            note_text = str(match.get("note") or "").strip()
            if not note_text:
                continue
            cid = _normalize_concept_id(match.get("concept_id"))
            if not cid:
                continue
            entry = speaker_block.get(cid)
            if not isinstance(entry, dict):
                entry = {}
            entry["import_note"] = note_text
            entry["import_raw"] = str(match.get("raw_name") or "")
            entry["updated_at"] = _utc_now_iso()
            speaker_block[cid] = entry
            imported += 1

        _write_json_file(_enrichments_path(), payload)

        self._send_json(HTTPStatus.OK, {
            "success": True,
            "speaker": speaker,
            "total_rows": len(rows),
            "imported": imported,
            "matched": sum(1 for m in matches if m.get("was_matched")),
            "lexeme_notes": payload.get("lexeme_notes") or {},
        })

    # ── Spectrogram (shared cache) ───────────────────────────────────

    def _api_get_spectrogram(self) -> None:
        """Return (or generate) a PNG spectrogram for a clip; cached on disk."""
        import spectrograms as spectro_module
        from urllib.parse import parse_qs

        query = urlparse(self.path).query
        params = {k: v[0] for k, v in parse_qs(query).items() if v}

        speaker_raw = str(params.get("speaker") or "").strip()
        if not speaker_raw:
            raise ApiError(HTTPStatus.BAD_REQUEST, "speaker is required")
        try:
            speaker = _normalize_speaker_id(speaker_raw)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        try:
            start_sec = float(params.get("start") or 0.0)
            end_sec = float(params.get("end") or 0.0)
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "start and end must be numbers")
        if end_sec <= start_sec:
            raise ApiError(HTTPStatus.BAD_REQUEST, "end must be greater than start")

        audio_hint = str(params.get("audio") or "").strip()
        audio_path: Optional[pathlib.Path] = None
        if audio_hint:
            try:
                audio_path = _resolve_project_path(audio_hint)
            except ValueError as exc:
                raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            working_candidate = _project_root() / "audio" / "working" / speaker
            if working_candidate.is_dir():
                for candidate in sorted(working_candidate.iterdir()):
                    if candidate.is_file() and candidate.suffix.lower() in {".wav", ".flac"}:
                        audio_path = candidate
                        break
            if audio_path is None:
                primary = _annotation_primary_source_wav(speaker)
                if primary:
                    try:
                        audio_path = _resolve_project_path(primary)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        if audio_path is None or not pathlib.Path(audio_path).is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "No audio file resolved for speaker {0}".format(speaker))

        cache_file = spectro_module.cache_path(_project_root(), speaker, start_sec, end_sec)
        force = str(params.get("force") or "").strip().lower() in {"1", "true", "yes"}

        try:
            spectro_module.generate_spectrogram_png(
                pathlib.Path(audio_path), start_sec, end_sec, cache_file, force=force,
            )
        except Exception as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "spectrogram render failed: {0}".format(exc))

        png_bytes = cache_file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png_bytes)))
        self.send_header("Cache-Control", "public, max-age=3600")
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(png_bytes)
        except BrokenPipeError:
            pass

    def _api_get_lexeme_search(self) -> None:
        """GET /api/lexeme/search — rank candidate time ranges for a concept.

        Query params:
            speaker       — required, the target speaker
            variants      — required, comma/space-separated orthographic forms
            concept_id    — optional, enables the cross-speaker signal + auto
                            augmentation with contact-lexeme variants
            language      — optional, phonemizer language code (default "ku")
            tiers         — optional, comma-separated subset of
                            ortho_words,ortho,stt,ipa (default all)
            limit         — optional, max candidates to return (default 10)
            max_distance  — optional float in (0, 1] — normalized Levenshtein
                            threshold, anything worse is dropped (default 0.55)

        Response JSON:
            {
              speaker, concept_id, variants, language,
              candidates: [{ start, end, tier, matched_text, matched_variant,
                             score, phonetic_score, cross_speaker_score,
                             confidence_weight, source_label }],
              signals_available: {
                 phonemizer: bool, cross_speaker_anchors: int,
                 contact_variants: [str]
              }
            }
        """
        try:
            from ai import lexeme_search as lex
        except Exception:
            try:
                from python.ai import lexeme_search as lex  # type: ignore[import-not-found]
            except Exception as exc:
                raise ApiError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "lexeme_search module unavailable: {0}".format(exc),
                )

        from urllib.parse import parse_qs

        query = urlparse(self.path).query
        params = {k: v[0] for k, v in parse_qs(query).items() if v}

        speaker_raw = str(params.get("speaker") or "").strip()
        if not speaker_raw:
            raise ApiError(HTTPStatus.BAD_REQUEST, "speaker is required")
        try:
            speaker = _normalize_speaker_id(speaker_raw)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        variants_raw = str(params.get("variants") or "").strip()
        user_variants = [v for v in re.split(r"[\s,;/]+", variants_raw) if v]
        if not user_variants:
            raise ApiError(HTTPStatus.BAD_REQUEST, "variants is required (comma or space separated)")

        concept_id = str(params.get("concept_id") or "").strip() or None
        language = str(params.get("language") or lex.DEFAULT_LANGUAGE).strip() or lex.DEFAULT_LANGUAGE

        tiers_raw = str(params.get("tiers") or "").strip()
        tiers_filter: Optional[list] = None
        if tiers_raw:
            tiers_filter = [t for t in re.split(r"[\s,;]+", tiers_raw) if t]

        try:
            limit = int(params.get("limit") or lex.DEFAULT_LIMIT)
        except (TypeError, ValueError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "limit must be an integer")
        if limit <= 0 or limit > 200:
            raise ApiError(HTTPStatus.BAD_REQUEST, "limit must be in [1, 200]")

        try:
            max_distance = float(params.get("max_distance") or lex.DEFAULT_MAX_DISTANCE)
        except (TypeError, ValueError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "max_distance must be a number in (0, 1]")
        if not (0 < max_distance <= 1):
            raise ApiError(HTTPStatus.BAD_REQUEST, "max_distance must be in (0, 1]")

        # Load the target speaker's annotation (must exist).
        try:
            target_path = _annotation_read_path_for_speaker(speaker)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))
        if not target_path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "No annotation record for speaker {0}".format(speaker))
        target_raw = _read_json_any_file(target_path)
        target_record = _normalize_annotation_record(target_raw, speaker)

        # Cross-speaker: load every OTHER annotation file — needed only when
        # the caller supplied a concept_id. Missing dir → empty list, not fatal.
        cross_records: list = []
        if concept_id:
            annotations_dir = _project_root() / "annotations"
            if annotations_dir.is_dir():
                for path in sorted(annotations_dir.iterdir()):
                    if not path.is_file():
                        continue
                    if path.suffix not in {".json"}:
                        continue
                    # Skip the target speaker's own file so we don't match ourselves.
                    stem = path.name.removesuffix(ANNOTATION_FILENAME_SUFFIX).removesuffix(
                        ANNOTATION_LEGACY_FILENAME_SUFFIX,
                    )
                    if stem == speaker:
                        continue
                    try:
                        raw = _read_json_any_file(path)
                        cross_records.append(_normalize_annotation_record(raw, stem))
                    except Exception:
                        # One bad file shouldn't take the whole search down.
                        continue

        # Contact-lexeme variants: auto-augment the user's variant list so
        # they don't have to know every documented form of the concept.
        contact_variants: list = []
        if concept_id:
            try:
                contact_variants = lex.load_contact_variants(concept_id, _sil_config_path())
            except Exception:
                contact_variants = []

        all_variants = list(user_variants)
        seen = {v for v in all_variants}
        for v in contact_variants:
            if v not in seen:
                all_variants.append(v)
                seen.add(v)

        candidates = lex.search(
            target_record,
            all_variants,
            concept_id=concept_id,
            cross_speaker_records=cross_records,
            language=language,
            limit=limit,
            max_distance=max_distance,
            tiers=tiers_filter,
        )

        phonemizer_available = bool(lex.phonemize_variant(user_variants[0], language=language))

        self._send_json(HTTPStatus.OK, {
            "speaker": speaker,
            "concept_id": concept_id,
            "variants": user_variants,
            "language": language,
            "candidates": candidates,
            "signals_available": {
                "phonemizer": phonemizer_available,
                "cross_speaker_anchors": sum(
                    1 for rec in cross_records
                    if concept_id and str(concept_id) in ((rec or {}).get("confirmed_anchors") or {})
                ),
                "contact_variants": contact_variants,
            },
        })

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
        config = _workspace_frontend_config(load_ai_config(_config_path()))
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
        """Emit a NEXUS character matrix compatible with BEAST2.

        One character per (concept, cognate group). For each speaker:
          1  — speaker is in this cognate group for the concept
          0  — speaker has a form for the concept but sits in a different group
          ?  — speaker has no form / unreviewed for the concept
        Manual overrides in ``manual_overrides.cognate_sets`` take precedence
        over the auto-computed ``cognate_sets`` block.
        """
        enrichments = _read_json_file(_enrichments_path(), _default_enrichments_payload())
        overrides = enrichments.get("manual_overrides") or {}
        override_sets = overrides.get("cognate_sets") if isinstance(overrides, dict) else None
        auto_sets = enrichments.get("cognate_sets") if isinstance(enrichments, dict) else None
        override_sets = override_sets if isinstance(override_sets, dict) else {}
        auto_sets = auto_sets if isinstance(auto_sets, dict) else {}

        # Speakers from project.json (falls back to any found in cognate sets).
        speakers_set: set = set()
        project_payload = _read_json_file(_project_json_path(), {})
        speakers_block = project_payload.get("speakers") if isinstance(project_payload, dict) else None
        if isinstance(speakers_block, dict):
            speakers_set.update(str(s) for s in speakers_block.keys() if str(s).strip())
        elif isinstance(speakers_block, list):
            speakers_set.update(str(s) for s in speakers_block if str(s).strip())

        # Determine which concepts have any cognate membership anywhere.
        concept_keys: List[str] = []
        concept_group_members: Dict[str, Dict[str, List[str]]] = {}
        union_keys: List[str] = []
        seen_keys: set = set()
        for key in list(override_sets.keys()) + list(auto_sets.keys()):
            if key not in seen_keys:
                seen_keys.add(key)
                union_keys.append(key)

        for key in union_keys:
            override_block = override_sets.get(key)
            auto_block = auto_sets.get(key)
            block = override_block if isinstance(override_block, dict) else auto_block
            if not isinstance(block, dict):
                continue
            groups: Dict[str, List[str]] = {}
            for group, members in block.items():
                if not isinstance(members, list):
                    continue
                cleaned = [str(m) for m in members if str(m).strip()]
                if cleaned:
                    groups[str(group)] = cleaned
                    speakers_set.update(cleaned)
            if groups:
                concept_group_members[key] = groups
                concept_keys.append(key)

        speakers = sorted(speakers_set)

        # Presence-of-form per (concept, speaker) — used to distinguish 0 from ?.
        # A speaker is considered "has form" if they appear in any cognate group
        # for the concept. (Future refinement: consult annotation tiers directly.)
        has_form: Dict[str, set] = {}
        for key in concept_keys:
            present: set = set()
            for members in concept_group_members[key].values():
                present.update(members)
            has_form[key] = present

        # Build characters in deterministic order.
        characters: List[Tuple[str, str, str]] = []  # (concept_key, group, label)
        for key in sorted(concept_keys, key=_concept_sort_key):
            for group in sorted(concept_group_members[key].keys()):
                label = "{0}_{1}".format(str(key).replace(" ", "_"), group)
                characters.append((key, group, label))

        # Build the per-speaker binary string.
        def row_for(speaker: str) -> str:
            chars: List[str] = []
            for key, group, _lbl in characters:
                members = concept_group_members[key].get(group, [])
                if speaker in members:
                    chars.append("1")
                elif speaker in has_form.get(key, set()):
                    chars.append("0")
                else:
                    chars.append("?")
            return "".join(chars)

        lines: List[str] = []
        lines.append("#NEXUS")
        lines.append("")
        lines.append("BEGIN TAXA;")
        lines.append("    DIMENSIONS NTAX={0};".format(len(speakers)))
        if speakers:
            lines.append("    TAXLABELS")
            for sp in speakers:
                lines.append("        {0}".format(sp))
            lines.append("    ;")
        lines.append("END;")
        lines.append("")
        lines.append("BEGIN CHARACTERS;")
        lines.append("    DIMENSIONS NCHAR={0};".format(len(characters)))
        lines.append("    FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS=\"01\";")
        if characters:
            lines.append("    CHARSTATELABELS")
            label_rows = []
            for idx, (_key, _group, label) in enumerate(characters, start=1):
                label_rows.append("        {0} {1}".format(idx, label))
            lines.append(",\n".join(label_rows))
            lines.append("    ;")
        lines.append("    MATRIX")
        for sp in speakers:
            lines.append("        {0}    {1}".format(sp, row_for(sp)))
        lines.append("    ;")
        lines.append("END;")
        lines.append("")

        nexus_text = "\n".join(lines).encode("utf-8")

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="parse-cognates.nex"')
        self.send_header("Content-Length", str(len(nexus_text)))
        self.end_headers()
        try:
            self.wfile.write(nexus_text)
        except BrokenPipeError:
            pass

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

    def _api_post_concepts_import(self) -> None:
        """Merge survey_item / custom_order from an uploaded CSV into concepts.csv.

        Upload format (CSV with header):
            - `id` or `concept_en` (at least one for matching)
            - `survey_item` (optional string)
            - `custom_order` (optional integer; blank/non-numeric clears the field)

        Matching: `id` first, then case-insensitive `concept_en`.
        Rows in the existing concepts.csv that aren't in the upload keep their
        existing `survey_item` / `custom_order`. Pass `?mode=replace` to clear
        those fields on non-matching rows instead.
        """
        import csv as _csv
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Type must be multipart/form-data")

        raw_length = self.headers.get("Content-Length", "")
        try:
            content_length = int(raw_length)
        except (ValueError, TypeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Length header is required")
        if content_length > ONBOARD_MAX_UPLOAD_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload exceeds limit")

        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(content_length),
        }
        form = cgi.FieldStorage(
            fp=self.rfile, headers=self.headers, environ=environ, keep_blank_values=True,
        )

        csv_item = form["csv"] if "csv" in form else None
        if csv_item is None or not getattr(csv_item, "filename", None):
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv file is required (field name: csv)")

        try:
            csv_text = csv_item.file.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv must be UTF-8: {0}".format(exc))

        mode_field = form.getfirst("mode", "") if "mode" in form else ""
        replace_mode = str(mode_field or "").strip().lower() == "replace"

        try:
            reader = _csv.DictReader(io.StringIO(csv_text))
            upload_rows = list(reader)
        except _csv.Error as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv parse error: {0}".format(exc))

        if not upload_rows:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv is empty")

        fieldnames = [str(n or "").strip().lower() for n in (reader.fieldnames or [])]
        if "id" not in fieldnames and "concept_en" not in fieldnames:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv must have an id or concept_en column")

        # Load existing
        concepts_path = _project_root() / "concepts.csv"
        existing: List[Dict[str, str]] = []
        if concepts_path.exists():
            with open(concepts_path, newline="", encoding="utf-8") as f:
                existing = list(_csv.DictReader(f))

        by_id: Dict[str, int] = {}
        by_label: Dict[str, int] = {}
        for idx, row in enumerate(existing):
            rid = _normalize_concept_id(row.get("id"))
            lbl = str(row.get("concept_en") or "").strip().lower()
            if rid:
                by_id[rid] = idx
            if lbl:
                by_label[lbl] = idx

        if replace_mode:
            for row in existing:
                row["survey_item"] = ""
                row["custom_order"] = ""

        matched = 0
        added = 0
        for up in upload_rows:
            up_id = _normalize_concept_id(up.get("id"))
            up_label = str(up.get("concept_en") or "").strip()
            target_idx: Optional[int] = None
            if up_id and up_id in by_id:
                target_idx = by_id[up_id]
            elif up_label and up_label.lower() in by_label:
                target_idx = by_label[up_label.lower()]

            survey_raw = str(up.get("survey_item") or "").strip() if "survey_item" in up else ""
            custom_raw = str(up.get("custom_order") or "").strip() if "custom_order" in up else ""

            if target_idx is None:
                if not up_label:
                    continue
                if not up_id:
                    # Auto-assign next numeric id so imports that only specify labels work.
                    existing_ids = {_normalize_concept_id(r.get("id")) for r in existing}
                    next_id = 1
                    while str(next_id) in existing_ids:
                        next_id += 1
                    up_id = str(next_id)
                row = {
                    "id": up_id,
                    "concept_en": up_label,
                    "survey_item": survey_raw,
                    "custom_order": custom_raw,
                }
                existing.append(row)
                by_id[up_id] = len(existing) - 1
                by_label[up_label.lower()] = len(existing) - 1
                added += 1
            else:
                row = existing[target_idx]
                if survey_raw:
                    row["survey_item"] = survey_raw
                if custom_raw:
                    row["custom_order"] = custom_raw
                matched += 1

        fieldnames_out = ["id", "concept_en", "survey_item", "custom_order"]
        concepts_path.parent.mkdir(parents=True, exist_ok=True)
        with open(concepts_path, "w", newline="", encoding="utf-8") as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames_out)
            writer.writeheader()
            for row in existing:
                writer.writerow({k: row.get(k, "") or "" for k in fieldnames_out})

        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "matched": matched,
                "added": added,
                "total": len(existing),
                "mode": "replace" if replace_mode else "merge",
            },
        )

    def _api_post_tags_import(self) -> None:
        """Import a custom concept list as a TAG with auto-assigned concepts.

        Multipart form fields:
            - `csv` (file, required): columns `id` and/or `concept_en`.
            - `tagName` (text, optional): defaults to the CSV filename stem.
            - `color` (text, optional): hex or named, default "#4461d4".

        Each CSV row is matched to an existing project concept by `id` first,
        else case-insensitive `concept_en`. Matched concept ids are added to
        the tag (merged — never removes existing assignments). Unmatched rows
        are reported as `missedLabels` so the caller can review.
        """
        import csv as _csv
        import re as _re

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Type must be multipart/form-data")

        raw_length = self.headers.get("Content-Length", "")
        try:
            content_length = int(raw_length)
        except (ValueError, TypeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Content-Length header is required")
        if content_length > ONBOARD_MAX_UPLOAD_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload exceeds limit")

        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(content_length),
        }
        form = cgi.FieldStorage(
            fp=self.rfile, headers=self.headers, environ=environ, keep_blank_values=True,
        )

        csv_item = form["csv"] if "csv" in form else None
        if csv_item is None or not getattr(csv_item, "filename", None):
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv file is required (field name: csv)")

        try:
            csv_text = csv_item.file.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv must be UTF-8: {0}".format(exc))

        csv_filename = os.path.basename(csv_item.filename or "tag.csv")
        tag_name_field = form.getfirst("tagName", "") if "tagName" in form else ""
        color_field = form.getfirst("color", "") if "color" in form else ""
        tag_name = str(tag_name_field or "").strip()
        if not tag_name:
            tag_name = pathlib.Path(csv_filename).stem or "Custom list"
        color = str(color_field or "").strip() or "#4461d4"

        try:
            reader = _csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
        except _csv.Error as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv parse error: {0}".format(exc))
        if not rows:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv is empty")

        fieldnames = [str(n or "").strip().lower() for n in (reader.fieldnames or [])]
        if "id" not in fieldnames and "concept_en" not in fieldnames:
            raise ApiError(HTTPStatus.BAD_REQUEST, "csv must have an id or concept_en column")

        # Load project concepts for matching
        concepts_path = _project_root() / "concepts.csv"
        project_concepts: List[Dict[str, str]] = []
        if concepts_path.exists():
            with open(concepts_path, newline="", encoding="utf-8") as f:
                project_concepts = list(_csv.DictReader(f))

        by_id: Dict[str, str] = {}
        by_label: Dict[str, str] = {}
        for c in project_concepts:
            cid = _normalize_concept_id(c.get("id"))
            lbl = str(c.get("concept_en") or "").strip()
            if cid:
                by_id[cid] = lbl
            if lbl:
                by_label[lbl.casefold()] = cid

        matched_ids: List[str] = []
        missed_labels: List[str] = []
        seen_ids: set = set()
        for row in rows:
            row_id = _normalize_concept_id(row.get("id"))
            row_label = str(row.get("concept_en") or "").strip()
            cid = ""
            if row_id and row_id in by_id:
                cid = row_id
            elif row_label and row_label.casefold() in by_label:
                cid = by_label[row_label.casefold()]
            if cid:
                if cid not in seen_ids:
                    matched_ids.append(cid)
                    seen_ids.add(cid)
            else:
                missed_labels.append(row_label or row_id or "")

        if not matched_ids:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "No rows matched any existing concept by id or concept_en. Import concepts first.",
            )

        # Upsert into parse-tags.json (additive merge)
        tag_id = _re.sub(r"[^a-z0-9]+", "-", tag_name.lower()).strip("-") or "tag"
        tags_path = _project_root() / "parse-tags.json"
        existing_tags: List[Dict[str, Any]] = []
        if tags_path.exists():
            try:
                with open(tags_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, list):
                    existing_tags = raw
            except (OSError, ValueError):
                existing_tags = []

        found = False
        for tag in existing_tags:
            if isinstance(tag, dict) and str(tag.get("id")) == tag_id:
                prev = set(tag.get("concepts") or [])
                prev.update(matched_ids)
                tag["concepts"] = sorted(prev, key=_concept_sort_key)
                tag["label"] = tag_name
                tag["color"] = color
                found = True
                break
        if not found:
            existing_tags.append({
                "id": tag_id,
                "label": tag_name,
                "color": color,
                "concepts": sorted(set(matched_ids), key=_concept_sort_key),
            })

        with open(tags_path, "w", encoding="utf-8") as f:
            json.dump(existing_tags, f, indent=2, ensure_ascii=False)

        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "tagId": tag_id,
                "tagName": tag_name,
                "color": color,
                "matchedCount": len(matched_ids),
                "missedCount": len(missed_labels),
                "missedLabels": missed_labels[:50],
                "totalTagsInFile": len(existing_tags),
            },
        )

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


class _BoundedThreadHTTPServer(http.server.HTTPServer):
    """HTTP server backed by a fixed-size thread pool.

    ThreadingHTTPServer spawns one OS thread per request. Under sustained
    CPU IPA loads with 2-second status polls this creates hundreds of
    threads and eventually hits a resource limit in WSL2. A bounded pool
    of 4 workers caps OS thread creation: the same threads are reused for
    every request, so the count never grows beyond max_workers.
    """

    def __init__(self, server_address, RequestHandlerClass, max_workers: int = 4):
        import concurrent.futures
        super().__init__(server_address, RequestHandlerClass)
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    def process_request(self, request, client_address):
        self._pool.submit(self._handle_in_pool, request, client_address)

    def _handle_in_pool(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)

    def server_close(self):
        super().server_close()
        self._pool.shutdown(wait=False)


def main() -> None:
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="PARSE HTTP server")
    parser.add_argument(
        "--compute-mode",
        choices=("thread", "subprocess", "persistent"),
        default=None,
        help=(
            "Backing runner for compute jobs. ``thread`` (default) runs in "
            "threading.Thread inside the server process. ``subprocess`` "
            "spawns a fresh Python process per job (recommended on "
            "Windows python.exe via WSL where threaded CUDA init wedges). "
            "``persistent`` starts one long-lived worker process that "
            "pre-loads wav2vec2 once and serves all compute jobs — fixes "
            "the root cause of the WSL2 stability issues that PRs #162-169 "
            "treated symptomatically. "
            "Overrides PARSE_COMPUTE_MODE env var when both are set."
        ),
    )
    args, _unknown = parser.parse_known_args()

    if args.compute_mode:
        global _COMPUTE_MODE_OVERRIDE
        _COMPUTE_MODE_OVERRIDE = args.compute_mode
        print(
            "[INFO] compute mode = {0} (from --compute-mode)".format(args.compute_mode),
            file=sys.stderr,
            flush=True,
        )

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
    httpd = _BoundedThreadHTTPServer(server_address, RangeRequestHandler)

    if _resolve_compute_mode() == "persistent":
        if not _start_persistent_worker():
            print(
                "[FATAL] --compute-mode=persistent requested but worker failed to start. "
                "See /tmp/parse-compute-worker.stderr.log for the cause.",
                file=sys.stderr, flush=True,
            )
            sys.exit(1)

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
