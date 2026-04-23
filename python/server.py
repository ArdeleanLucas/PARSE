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
from urllib.parse import unquote, urlparse

from ai.chat_orchestrator import ChatOrchestrator, ChatOrchestratorError, READ_ONLY_NOTICE
from ai.chat_tools import ParseChatTools
from ai.provider import get_chat_config, get_llm_provider, get_ortho_provider, get_stt_provider, load_ai_config, resolve_context_window
from ai.ipa_transcribe import transcribe_slice as _acoustic_transcribe_slice
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


def _annotation_shift_intervals(record: Dict[str, Any], offset_sec: float) -> int:
    """Add ``offset_sec`` to every interval's start/end. Negative values clamp to 0.

    Mutates the record in place. Returns the count of intervals shifted.
    """
    if not isinstance(record, dict):
        return 0
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return 0

    shifted = 0
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
    return shifted


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


def _chat_pipeline_state(speaker: str) -> Dict[str, Any]:
    """Thin wrapper so ParseChatTools can reach the preflight probe."""
    return _pipeline_state_for_speaker(speaker)


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
    job_id = _create_job(
        "compute:{0}".format(normalized_type),
        {
            "computeType": normalized_type,
            "payload": body_obj,
            "origin": "chat_tool",
        },
    )
    thread = threading.Thread(
        target=_run_compute_job,
        args=(job_id, normalized_type, body_obj),
        daemon=True,
    )
    thread.start()
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


def _run_stt_job(job_id: str, speaker: str, source_wav: str, language: Optional[str]) -> None:
    try:
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
        # only `_set_job_complete` actually fills the bar.
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
        _set_job_complete(
            job_id,
            result,
            message="STT complete — {0} segments".format(len(segments)),
            segments_processed=len(segments),
            total_segments=len(segments),
        )
    except Exception as exc:
        _set_job_error(job_id, str(exc))


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
        return _IPA_ALIGNER

    import time as _time
    from ai.forced_align import Aligner, DEFAULT_MODEL_NAME

    t0 = _time.time()
    print(
        "[IPA] Loading wav2vec2 aligner model={0}…".format(DEFAULT_MODEL_NAME),
        file=sys.stderr,
        flush=True,
    )
    try:
        _IPA_ALIGNER = Aligner.load()
    except Exception as exc:
        elapsed = _time.time() - t0
        print(
            "[IPA][ERROR] Aligner.load() failed after {0:.1f}s: {1}".format(elapsed, exc),
            file=sys.stderr,
            flush=True,
        )
        raise

    elapsed = _time.time() - t0
    device = getattr(_IPA_ALIGNER, "device", "?")
    vocab_size = len(getattr(_IPA_ALIGNER, "vocab", {}) or {})
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
    # Diagnostics v2: trace every call-site that could silently crash
    # the process (CUDA / torch init). Prints are unbuffered + flushed
    # so we land in stderr even on native crashes.
    print("[IPA] enter _compute_speaker_ipa payload={0}".format(payload), file=sys.stderr, flush=True)

    speaker = _normalize_speaker_id(payload.get("speaker"))
    overwrite = bool(payload.get("overwrite", False))

    canonical_path = _project_root() / _annotation_record_relative_path(speaker)
    legacy_path = _project_root() / _annotation_legacy_record_relative_path(speaker)

    if canonical_path.is_file():
        annotation_path = canonical_path
    elif legacy_path.is_file():
        annotation_path = legacy_path
    else:
        raise RuntimeError("No annotation found for speaker {0!r}".format(speaker))

    print("[IPA] loaded annotation_path={0}".format(annotation_path), file=sys.stderr, flush=True)
    annotation = _read_json_file(annotation_path, {})
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
    print("[IPA] resolving audio path for speaker={0}…".format(speaker), file=sys.stderr, flush=True)
    audio_path = _pipeline_audio_path_for_speaker(speaker)
    print("[IPA] audio_path={0} — importing ai.forced_align".format(audio_path), file=sys.stderr, flush=True)
    from ai.forced_align import _load_audio_mono_16k
    print("[IPA] import ok — calling _load_audio_mono_16k()", file=sys.stderr, flush=True)
    import time as _t_load
    _t0 = _t_load.time()
    audio_tensor = _load_audio_mono_16k(audio_path)
    _load_elapsed = _t_load.time() - _t0
    try:
        _numel = int(audio_tensor.numel())
    except Exception:
        _numel = -1
    print(
        "[IPA] audio loaded in {0:.1f}s numel={1} (~{2:.1f}s of 16 kHz mono)".format(
            _load_elapsed, _numel, _numel / 16000.0 if _numel > 0 else 0.0
        ),
        file=sys.stderr,
        flush=True,
    )
    print("[IPA] calling _get_ipa_aligner()…", file=sys.stderr, flush=True)
    aligner = _get_ipa_aligner()
    print("[IPA] aligner ready — entering per-interval loop (n={0})".format(len(ortho_intervals)), file=sys.stderr, flush=True)

    filled = 0
    skipped = 0
    total = len(ortho_intervals)
    # Categorised skip counters so the job result can show *why* nothing
    # got filled. Aligned with the user-visible failure modes we traced
    # on Fail02 where filled=0 skipped=38 with no surfaced reason.
    skipped_empty_ortho = 0
    skipped_existing_ipa = 0
    skipped_zero_range = 0
    skipped_exception = 0
    skipped_empty_ipa = 0
    exception_samples: List[str] = []  # first 3 exceptions, full message

    for idx, ortho in enumerate(ortho_intervals):
        text = str(ortho.get("text") or "").strip()
        start_sec = float(ortho.get("start", 0.0) or 0.0)
        end_sec = float(ortho.get("end", start_sec) or start_sec)
        key = _key(ortho)
        existing = ipa_by_key.get(key)
        existing_text = str((existing or {}).get("text") or "").strip()

        # Ortho text is still the gate: intervals with no ortho aren't
        # worth transcribing (typically silence/noise segments that the
        # user hasn't labelled).
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

        try:
            new_ipa = _acoustic_transcribe_slice(audio_tensor, start_sec, end_sec, aligner)
        except Exception as exc:
            skipped += 1
            skipped_exception += 1
            if len(exception_samples) < 3:
                exception_samples.append(
                    "interval[{0}] {1:.2f}-{2:.2f}: {3}: {4}".format(
                        idx, start_sec, end_sec, type(exc).__name__, exc
                    )
                )
            continue

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


def _compute_speaker_ortho(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an orthographic transcript for a speaker using the razhan model.

    Runs the ORTH provider (faster-whisper with razhan/whisper-base-sdh)
    full-file against the speaker's working WAV (normalized copy preferred,
    raw source as fallback) and writes razhan's own segments to the
    ``ortho`` tier of the annotation.

    Payload: ``{"speaker": "Fail02", "overwrite": false}``.

    Overwrite semantics differ from IPA: razhan's segmentation isn't stable
    across runs, so we can't pair segments by ``(start, end)`` the way IPA
    does. Rule: if the ortho tier already has any non-empty text intervals,
    the caller must set ``overwrite=True`` to replace the whole tier;
    otherwise the run is a no-op and returns ``skipped=True``. Empty tiers
    are always populated.
    """
    speaker = _normalize_speaker_id(payload.get("speaker"))
    overwrite = bool(payload.get("overwrite", False))
    language = payload.get("language")
    language_str = str(language).strip() if isinstance(language, str) and language.strip() else None

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
        clamped = min(float(progress) if progress is not None else 0.0, 98.0)
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
        ortho_tier = {"type": "interval", "display_order": 2, "intervals": []}
    ortho_tier["intervals"] = new_intervals
    tiers["ortho"] = ortho_tier
    annotation["tiers"] = tiers
    _annotation_touch_metadata(annotation, preserve_created=True)

    _write_json_file(annotation_path, annotation)
    if canonical_path != annotation_path:
        _write_json_file(canonical_path, annotation)
    if legacy_path != annotation_path:
        _write_json_file(legacy_path, annotation)

    _set_job_progress(job_id, 99.0, message="ORTH written ({0} intervals)".format(len(new_intervals)))

    return {
        "speaker": speaker,
        "filled": len(new_intervals),
        "skipped": False,
        "replaced_existing": has_existing_text,
        "audio_path": str(audio_path),
        "total": len(new_intervals),
    }


# Canonical step identifiers recognised by the full-pipeline sequencer.
PIPELINE_STEPS: Tuple[str, ...] = ("normalize", "stt", "ortho", "ipa")


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
                _run_stt_job(job_id, speaker, str(audio_path), language_str)
                snapshot = _get_job_snapshot(job_id) or {}
                if str(snapshot.get("status") or "") == "error":
                    raise RuntimeError(
                        "stt step failed: {0}".format(snapshot.get("error") or "unknown error")
                    )
                sub_result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
                results["stt"] = {
                    "status": "ok",
                    "segments": len(sub_result.get("segments") or []) if isinstance(sub_result, dict) else 0,
                    "done": True,
                }
                _reset_job_to_running(job_id)
                steps_run.append(step)

            elif step == "ortho":
                sub_result = _compute_speaker_ortho(
                    job_id,
                    {
                        "speaker": speaker,
                        "overwrite": overwrites.get("ortho", False),
                        "language": language_str,
                    },
                )
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


def _run_compute_job(job_id: str, compute_type: str, payload: Dict[str, Any]) -> None:
    # Diagnostics v2: emit on every entry so we can tell if the compute
    # thread is even starting — previous Fail02 runs died between the
    # HTTP POST accepting and the first downstream log line.
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

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "stt-segments":
            self._api_get_stt_segments(parts[2])
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "pipeline" and parts[2] == "state":
            self._api_get_pipeline_state(parts[3])
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "chat" and parts[2] == "session":
            self._api_get_chat_session(parts[3])
            return

        if request_path == "/api/jobs/active":
            self._api_get_jobs_active()
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

        if request_path == "/api/spectrogram":
            self._api_get_spectrogram()
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

    def _api_post_offset_detect(self) -> None:
        """Synchronously detect a constant timestamp offset for a speaker.

        Compares anchors taken from the speaker's annotation tiers against STT
        segments (passed inline via ``sttSegments``, pulled from a completed
        STT job by ``sttJobId``, or auto-discovered as the speaker's most
        recent complete STT job). Returns the median offset and a confidence —
        does not mutate any files.
        """
        body = self._expect_object(self._read_json_body(), "Request body")

        try:
            speaker = _normalize_speaker_id(body.get("speaker"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

        try:
            n_anchors = max(2, min(50, int(body.get("nAnchors") or body.get("n_anchors") or 12)))
        except (TypeError, ValueError):
            n_anchors = 12

        try:
            bucket_sec = max(0.1, float(body.get("bucketSec") or body.get("bucket_sec") or 1.0))
        except (TypeError, ValueError):
            bucket_sec = 1.0

        try:
            min_match_score = max(
                0.0,
                min(1.0, float(body.get("minMatchScore") or body.get("min_match_score") or 0.56)),
            )
        except (TypeError, ValueError):
            min_match_score = 0.56

        annotation_path = _annotation_read_path_for_speaker(speaker)
        annotation = _normalize_annotation_record(_read_json_any_file(annotation_path), speaker)
        intervals = _annotation_offset_anchor_intervals(annotation)
        if not intervals:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "Speaker '{0}' has no annotated intervals to use as offset anchors".format(speaker),
            )

        stt_segments_payload = body.get("sttSegments") or body.get("stt_segments")
        stt_job_id = str(body.get("sttJobId") or body.get("stt_job_id") or "").strip()

        if stt_segments_payload is None and stt_job_id:
            job = _get_job_snapshot(stt_job_id)
            if job is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "Unknown sttJobId")
            if str(job.get("type") or "") != "stt":
                raise ApiError(HTTPStatus.BAD_REQUEST, "sttJobId is not an STT job")
            if str(job.get("status") or "") != "complete":
                raise ApiError(HTTPStatus.BAD_REQUEST, "STT job has not completed")
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
            stt_segments_payload = result.get("segments")

        if stt_segments_payload is None:
            stt_segments_payload = _latest_stt_segments_for_speaker(speaker)

        if not stt_segments_payload:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "No STT segments available. Run STT first or pass sttJobId / sttSegments.",
            )

        from compare import (
            anchors_from_intervals as _anchors_from_intervals,
            detect_offset_detailed as _detect_offset_detailed,
            load_rules_from_file as _load_rules,
            segments_from_raw as _segments_from_raw,
        )

        rules_path = _project_root() / "config" / "phonetic_rules.json"
        try:
            rules = _load_rules(rules_path) if rules_path.exists() else []
        except Exception:
            rules = []

        distribution_raw = str(body.get("distribution") or body.get("anchorDistribution") or "quantile").strip().lower()
        if distribution_raw not in {"quantile", "earliest"}:
            distribution_raw = "quantile"

        anchors = _anchors_from_intervals(intervals, n_anchors, distribution=distribution_raw)
        if not anchors:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "No usable anchors with both timestamp and text in annotation",
            )
        segments = _segments_from_raw(stt_segments_payload)
        if not segments:
            raise ApiError(HTTPStatus.BAD_REQUEST, "STT input contained no usable segments")

        try:
            detailed = _detect_offset_detailed(
                anchors=anchors,
                segments=segments,
                rules=rules,
                bucket_sec=bucket_sec,
                min_match_score=min_match_score,
            )
        except ValueError as exc:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))

        self._send_json(
            HTTPStatus.OK,
            _offset_detect_payload(
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
            ),
        )

    def _api_post_offset_detect_from_pair(self) -> None:
        """Compute the offset from one or more trusted (csv_time, audio_time) pairs.

        Two body shapes are accepted:

        * **Single pair (legacy)**:
            ``{speaker, audioTimeSec, csvTimeSec? | conceptId?}``
        * **Multiple pairs (preferred)**:
            ``{speaker, pairs: [{audioTimeSec, csvTimeSec? | conceptId?}, ...]}``

        With multiple pairs the offset is the median of per-pair offsets and
        the response carries the MAD spread plus a warning if any single
        pair disagrees with the consensus by more than ``2 s``. No STT, no
        statistics-on-text — every input is a user-supplied ground truth.
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

        # Lazy-load the annotation only if at least one pair needs concept lookup.
        annotation_cache: Optional[Dict[str, Any]] = None

        def _annotation() -> Dict[str, Any]:
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
                raise ApiError(HTTPStatus.BAD_REQUEST, "Each pair must be a JSON object")

            audio_raw = raw.get("audioTimeSec")
            if audio_raw is None:
                audio_raw = raw.get("audio_time_sec")
            try:
                audio_time = float(audio_raw)
            except (TypeError, ValueError):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Each pair needs a numeric audioTimeSec")
            if not math.isfinite(audio_time) or audio_time < 0:
                raise ApiError(HTTPStatus.BAD_REQUEST, "audioTimeSec must be finite and non-negative")

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
                    raise ApiError(HTTPStatus.BAD_REQUEST, "csvTimeSec must be a number when provided")
                if not math.isfinite(anchor_csv_time) or anchor_csv_time < 0:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "csvTimeSec must be finite and non-negative")
                anchor_label = "csvTimeSec={0:.3f}s".format(anchor_csv_time)
            elif concept_raw is not None and str(concept_raw).strip():
                concept_id = str(concept_raw).strip()
                interval = _annotation_find_concept_interval(_annotation(), concept_id)
                if interval is None:
                    raise ApiError(
                        HTTPStatus.BAD_REQUEST,
                        "No annotation interval found for concept '{0}'".format(concept_id),
                    )
                anchor_csv_time = float(interval["start"])
                anchor_label = "concept '{0}' @ {1:.3f}s".format(concept_id, anchor_csv_time)
            else:
                raise ApiError(
                    HTTPStatus.BAD_REQUEST,
                    "Each pair needs either csvTimeSec or conceptId",
                )

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

        # Median offset across pairs; MAD for the headline spread number;
        # max-deviation drives confidence so a single outlier among many
        # consistent pairs is visible (MAD alone hides it). Both numbers
        # show up in the response — UI flags any pair whose offset
        # diverges from the consensus by more than `spread_warn_sec`.
        import statistics as _statistics

        median_offset = round(_statistics.median(offsets), 3)
        if len(offsets) >= 2:
            deviations = [abs(o - median_offset) for o in offsets]
            spread = round(_statistics.median(deviations), 3)
            max_deviation = max(deviations)
            # Linear drop: identical pairs → 0.99; one pair off by 30 s
            # → 0.49 (clamped to 0.5). Big enough penalty to amber the
            # Apply button via the existing _offset_detect_payload logic.
            confidence = max(0.5, min(0.99, 0.99 - (max_deviation / 60.0)))
        else:
            spread = 0.0
            confidence = 0.99

        self._send_json(
            HTTPStatus.OK,
            _offset_detect_payload(
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
            ),
        )

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

        shifted_count = _annotation_shift_intervals(annotation, offset_sec)
        if shifted_count == 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "No intervals were shifted")

        _annotation_touch_metadata(annotation, preserve_created=True)
        write_path = _annotation_record_path_for_speaker(speaker)
        _write_json_file(write_path, annotation)

        self._send_json(
            HTTPStatus.OK,
            {
                "speaker": speaker,
                "appliedOffsetSec": offset_sec,
                "shiftedIntervals": shifted_count,
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

    def _api_get_jobs_active(self) -> None:
        """Return a list of currently-running jobs so the UI can rehydrate
        progress after a page reload. See ``_list_active_jobs_snapshots``."""
        self._send_json(HTTPStatus.OK, {"jobs": _list_active_jobs_snapshots()})

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
