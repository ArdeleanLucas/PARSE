"""PARSE HTTP server with static range serving and API endpoints."""
import cgi
import copy
import http.server
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
# When launched as `python python/server.py`, downstream route modules still
# import `server`. Register this module under that name early so script-mode
# startup reuses the in-flight module instead of recursively re-importing it.
sys.modules.setdefault("server", sys.modules[__name__])
from ai.chat_orchestrator import ChatOrchestrator, ChatOrchestratorError, READ_ONLY_NOTICE
from ai.chat_tools import ParseChatTools
from ai.workflow_tools import WorkflowTools
from ai.provider import get_chat_config, get_llm_provider, get_ortho_provider, get_stt_provider, load_ai_config, resolve_context_window
from ai.ipa_transcribe import transcribe_slice as _acoustic_transcribe_slice
from app.http.auth_handlers import (
    AuthHandlerError as _app_AuthHandlerError,
    build_auth_key_response as _app_build_auth_key_response,
    build_auth_logout_response as _app_build_auth_logout_response,
    build_auth_poll_response as _app_build_auth_poll_response,
    build_auth_start_response as _app_build_auth_start_response,
    build_auth_status_response as _app_build_auth_status_response,
)
from app.http.external_api_handlers import (
    ExternalApiHandlerError as _app_ExternalApiHandlerError,
    build_mcp_exposure_response as _app_build_mcp_exposure_response,
    build_mcp_tool_response as _app_build_mcp_tool_response,
    build_mcp_tools_response as _app_build_mcp_tools_response,
    execute_mcp_http_tool as _app_execute_mcp_http_tool,
    match_builtin_docs_response as _app_match_builtin_docs_response,
    resolve_requested_catalog_mode as _app_resolve_requested_catalog_mode,
)
from app.http.job_observability_handlers import (
    JobObservabilityHandlerError as _app_JobObservabilityHandlerError,
    build_job_detail_response as _app_build_job_detail_response,
    build_job_error_logs_response as _app_build_job_error_logs_response,
    build_job_logs_response as _app_build_job_logs_response,
    build_jobs_active_response as _app_build_jobs_active_response,
    build_jobs_response as _app_build_jobs_response,
    build_worker_status_response as _app_build_worker_status_response,
)
from app.http.project_config_handlers import (
    ProjectConfigHandlerError as _app_ProjectConfigHandlerError,
    build_concepts_import_response as _app_build_concepts_import_response,
    build_get_config_response as _app_build_get_config_response,
    build_tags_import_response as _app_build_tags_import_response,
    build_update_config_response as _app_build_update_config_response,
)
from app.http.project_artifact_handlers import (
    ProjectArtifactHandlerError as _app_ProjectArtifactHandlerError,
    build_get_export_lingpy_response as _app_build_get_export_lingpy_response,
    build_get_export_nexus_response as _app_build_get_export_nexus_response,
    build_get_tags_response as _app_build_get_tags_response,
    build_post_tags_merge_response as _app_build_post_tags_merge_response,
)
from app.http.clef_http_handlers import (
    ClefHttpHandlerError as _app_ClefHttpHandlerError,
    build_get_clef_catalog_response as _app_build_get_clef_catalog_response,
    build_get_clef_config_response as _app_build_get_clef_config_response,
    build_get_clef_providers_response as _app_build_get_clef_providers_response,
    build_get_clef_sources_report_response as _app_build_get_clef_sources_report_response,
    build_get_contact_lexeme_coverage_response as _app_build_get_contact_lexeme_coverage_response,
    build_post_clef_clear_response as _app_build_post_clef_clear_response,
    build_post_clef_config_response as _app_build_post_clef_config_response,
    build_post_clef_form_selections_response as _app_build_post_clef_form_selections_response,
)
from app.http.compute_offset_handlers import (
    ComputeOffsetHandlerError as _app_ComputeOffsetHandlerError,
    build_post_compute_start_response as _app_build_post_compute_start_response,
    build_post_compute_status_response as _app_build_post_compute_status_response,
    build_post_offset_apply_response as _app_build_post_offset_apply_response,
    build_post_offset_detect_from_pair_response as _app_build_post_offset_detect_from_pair_response,
    build_post_offset_detect_response as _app_build_post_offset_detect_response,
)
from app.http.lexeme_note_handlers import (
    LexemeNoteHandlerError as _app_LexemeNoteHandlerError,
    build_post_lexeme_note_response as _app_build_post_lexeme_note_response,
    build_post_lexeme_notes_import_response as _app_build_post_lexeme_notes_import_response,
)
from app.http.media_search_handlers import (
    MediaSearchHandlerError as _app_MediaSearchHandlerError,
    build_get_lexeme_search_response as _app_build_get_lexeme_search_response,
    build_get_spectrogram_response as _app_build_get_spectrogram_response,
)
from app.http.speech_annotation_handlers import (
    SpeechAnnotationHandlerError as _app_SpeechAnnotationHandlerError,
    build_get_stt_segments_response as _app_build_get_stt_segments_response,
    build_post_normalize_response as _app_build_post_normalize_response,
    build_post_normalize_status_response as _app_build_post_normalize_status_response,
    build_post_stt_start_response as _app_build_post_stt_start_response,
    build_post_stt_status_response as _app_build_post_stt_status_response,
    build_post_suggest_response as _app_build_post_suggest_response,
)
from app.http.request_helpers import (
    JsonBodyError as _app_JsonBodyError,
    path_parts as _app_path_parts,
    read_json_body as _app_read_json_body,
    request_path as _app_request_path,
    request_query_params as _app_request_query_params,
)
from app.http.response_helpers import (
    send_json_error_response as _app_send_json_error_response,
    send_json_response as _app_send_json_response,
)
from app.http.static_paths import (
    dist_dir as _app_dist_dir,
    dist_index_path as _app_dist_index_path,
    has_built_frontend as _app_has_built_frontend,
    resolve_static_request_path as _app_resolve_static_request_path,
    static_request_parts as _app_static_request_parts,
)
from app.services.workspace_config import build_workspace_frontend_config as _app_build_workspace_frontend_config
from audio_pipeline_paths import build_normalized_output_path
from external_api.streaming import JobStreamingSidecar
# Route modules import `server` by name. When this file runs as a script its
# module name is `__main__`; register that in-flight module under `server` too
# so route helpers do not dual-load a second copy of server.py.
sys.modules.setdefault("server", sys.modules[__name__])
try:
    from compare import cognate_compute as cognate_compute_module
except Exception:
    cognate_compute_module = None
HOST = "0.0.0.0"
PORT = 8766
WS_PORT = 8767
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
    "ortho_words": 5,
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
_job_streaming_lock = threading.Lock()
_job_streaming_sidecar: Optional[JobStreamingSidecar] = None
_ROUTE_MODULE_NAMES = (
    "annotate",
    "compare",
    "jobs",
    "exports",
    "config",
    "clef", "locks", "chat", "media",
)
_ROUTE_BINDINGS_LOCK = threading.Lock()
_ROUTE_BINDINGS_INSTALLED = False

_chat_sessions: Dict[str, Dict[str, Any]] = {}
_chat_sessions_lock = threading.Lock()

_chat_runtime_lock = threading.Lock()
_chat_tools_runtime: Optional[ParseChatTools] = None
_chat_orchestrator_runtime: Optional[ChatOrchestrator] = None
_chat_runtime_signature: Optional[Tuple[Any, ...]] = None


def _reset_chat_runtime_after_auth_key_save() -> None:
    """Clear cached chat runtimes so a newly saved API key applies immediately."""
    global _chat_tools_runtime
    global _chat_orchestrator_runtime
    global _chat_runtime_signature

    with _chat_runtime_lock:
        _chat_tools_runtime = None
        _chat_orchestrator_runtime = None
        _chat_runtime_signature = None


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


def _load_sil_config_safe(path: pathlib.Path) -> Dict[str, Any]:
    """Read the SIL contact-language config without exploding on a
    missing/corrupt file. Returns ``{}`` in the degraded case so callers
    (coverage endpoint, CLEF configure endpoint, compute path) can all
    share one shape."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_sil_config(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    return _app_dist_dir(project_root or _project_root())


def _dist_index_path(project_root: Optional[pathlib.Path] = None) -> pathlib.Path:
    return _app_dist_index_path(project_root or _project_root())


def _has_built_frontend(project_root: Optional[pathlib.Path] = None) -> bool:
    return _app_has_built_frontend(project_root or _project_root())


def _static_request_parts(raw_path: str) -> List[str]:
    return _app_static_request_parts(raw_path)


def _resolve_static_request_path(
    raw_path: str,
    project_root: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    return _app_resolve_static_request_path(raw_path, project_root or _project_root())


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

# because Windows python.exe launched via WSL interop does NOT inherit
# WSL-side env vars (confirmed 2026-04-23: ``PARSE_COMPUTE_MODE=subprocess
# python.exe server.py`` — inside the process, os.environ.get returns
# None for anything outside a small whitelist like HOME/PATH/USER).
# argv DOES propagate across the interop boundary, so the flag is the
# reliable way to pin the mode on that deployment.
_COMPUTE_MODE_OVERRIDE: Optional[str] = None

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
            on_stt_segment=_publish_stt_partial_segment,
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

_MUTATING_SPEAKER_JOB_TYPES = frozenset({"normalize", "stt", "onboard:speaker"})
_MUTATING_SPEAKER_COMPUTE_TYPES = frozenset(
    {"stt", "ortho", "ortho_only", "ipa", "ipa_only", "forced_align", "full_pipeline"}
)

def _get_chat_runtime() -> Tuple[ParseChatTools, ChatOrchestrator]:
    global _chat_tools_runtime
    global _chat_orchestrator_runtime
    global _chat_runtime_signature

    current_signature = (
        str(_project_root()),
        str(_config_path()),
        str(_chat_docs_root()),
        tuple(str(path) for path in _chat_external_read_roots()),
        str(_chat_memory_path()),
        id(ParseChatTools),
        id(ChatOrchestrator),
        id(_chat_start_stt_job),
        id(_chat_get_job_snapshot),
        id(_chat_list_jobs),
        id(_chat_get_job_logs),
        id(_chat_onboard_speaker),
        id(_chat_start_compute_job),
        id(_chat_pipeline_state),
    )

    with _chat_runtime_lock:
        if _chat_runtime_signature != current_signature:
            _chat_tools_runtime = None
            _chat_orchestrator_runtime = None
            _chat_runtime_signature = current_signature

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

def _resolve_http_port() -> int:
    for env_key in ("PARSE_PORT", "PARSE_API_PORT"):
        raw = str(os.environ.get(env_key) or "").strip()
        if not raw:
            continue
        try:
            port = int(raw)
        except (TypeError, ValueError):
            return PORT
        if 0 <= port <= 65535:
            return port
        return PORT
    return PORT


def _resolve_ws_port() -> int:
    raw = str(os.environ.get("PARSE_WS_PORT") or "").strip()
    if not raw:
        return WS_PORT
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return WS_PORT
    if 0 <= port <= 65535:
        return port
    return WS_PORT



def _job_stream_envelope(
    event_type: str,
    *,
    job_id: str,
    job_type: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "event": str(event_type),
        "jobId": str(job_id),
        "type": str(job_type),
        "ts": _utc_now_iso(),
        "payload": copy.deepcopy(payload),
    }



def _job_snapshot_stream_event(job_id: str) -> Optional[Dict[str, Any]]:
    job = _get_job_snapshot(job_id)
    if job is None:
        return None
    return _job_stream_envelope(
        "job.snapshot",
        job_id=str(job.get("jobId") or job_id),
        job_type=str(job.get("type") or ""),
        payload=_job_response_payload(job),
    )



def _job_streaming_sidecar_or_none() -> Optional[JobStreamingSidecar]:
    with _job_streaming_lock:
        return _job_streaming_sidecar



def _start_websocket_sidecar(host: Optional[str] = None, port: Optional[int] = None) -> JobStreamingSidecar:
    global _job_streaming_sidecar
    requested_host = str(host or HOST).strip() or HOST
    requested_port = _resolve_ws_port() if port is None else int(port)
    with _job_streaming_lock:
        sidecar = _job_streaming_sidecar
        if sidecar is not None:
            same_host = str(sidecar.host or "") == requested_host
            same_port = sidecar.port == requested_port if requested_port != 0 else True
            if sidecar.is_running() and same_host and same_port:
                return sidecar
            sidecar.stop()
        sidecar = JobStreamingSidecar(
            host=requested_host,
            port=requested_port,
            get_snapshot_event=_job_snapshot_stream_event,
        ).start()
        _job_streaming_sidecar = sidecar
        return sidecar



def _shutdown_websocket_sidecar() -> None:
    global _job_streaming_sidecar
    with _job_streaming_lock:
        sidecar = _job_streaming_sidecar
        _job_streaming_sidecar = None
    if sidecar is not None:
        sidecar.stop()



def _publish_job_stream_event(
    event_type: str,
    *,
    job_id: str,
    job_type: str,
    payload: Dict[str, Any],
) -> None:
    sidecar = _job_streaming_sidecar_or_none()
    if sidecar is None:
        return
    sidecar.publish(
        _job_stream_envelope(
            event_type,
            job_id=job_id,
            job_type=job_type,
            payload=payload,
        )
    )



def _publish_stt_partial_segment(job_id: str, segment: Dict[str, Any]) -> None:
    job = _get_job_snapshot(job_id)
    if job is None:
        return
    _publish_job_stream_event(
        "stt.segment",
        job_id=str(job.get("jobId") or job_id),
        job_type=str(job.get("type") or "stt"),
        payload={
            "provisional": True,
            "segment": copy.deepcopy(segment),
        },
    )

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

    # Honour wav2vec2.model/device/force_cpu from ai_config.json, or auto-detect
    # via resolve_device() which forces CPU on WSL to avoid GPU driver crashes.
    try:
        import json as _json
        _ai_cfg = _json.loads((_project_root() / "config" / "ai_config.json").read_text())
        _w2v = _ai_cfg.get("wav2vec2", {})
        _ipa_model = str(_w2v.get("model") or DEFAULT_MODEL_NAME)
        if _w2v.get("force_cpu"):
            _ipa_device: Optional[str] = "cpu"
        else:
            _ipa_device = _w2v.get("device") or None
    except Exception:
        _ipa_model = DEFAULT_MODEL_NAME
        _ipa_device = None

    t0 = _time.time()
    print(
        "[IPA] Loading wav2vec2 aligner model={0}…".format(_ipa_model),
        file=sys.stderr,
        flush=True,
    )

    from ai.forced_align import _is_wsl as _fa_is_wsl
    if _fa_is_wsl():
        import os as _os
        _os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "1")
        print("[COMPUTE] WSL detected → CUDA_LAUNCH_BLOCKING=1", file=sys.stderr, flush=True)

    try:
        _compute_checkpoint("ALIGNER.load_begin")
        _IPA_ALIGNER = Aligner.load(model_name=_ipa_model, device=_ipa_device)
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

_COVERAGE_FRACTION_THRESHOLD = 0.95
_COVERAGE_ABSOLUTE_TOLERANCE_SEC = 3.0

# Canonical step identifiers recognised by the full-pipeline sequencer.
PIPELINE_STEPS: Tuple[str, ...] = ("normalize", "stt", "ortho", "ipa")

_OFFSET_DETECT_TIMEOUT_SEC_DEFAULT = 600.0

class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with static range support and API routes."""

    def translate_path(self, path: str) -> str:
        return str(_resolve_static_request_path(path))

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_api_") or name in {"_parse_single_range", "_serve_range", "_send_416"}:
            _install_route_bindings()
            attr = getattr(type(self), name, None)
            if attr is not None:
                return attr.__get__(self, type(self))
        raise AttributeError("{0!r} object has no attribute {1!r}".format(type(self).__name__, name))

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
        return _app_request_path(self.path)

    def _request_query_params(self) -> Dict[str, List[str]]:
        return _app_request_query_params(self.path)

    def _request_base_url(self) -> str:
        host = str(self.headers.get("Host") or "127.0.0.1:{0}".format(PORT)).strip() or "127.0.0.1:{0}".format(PORT)
        return "http://{0}".format(host)

    def _is_api_path(self, raw_path: str) -> bool:
        return (urlparse(raw_path).path or "").startswith("/api/")

    def _path_parts(self, request_path: str) -> List[str]:
        return _app_path_parts(request_path)

    def _read_json_body(self, required: bool = True) -> Any:
        try:
            return _app_read_json_body(self.headers, self.rfile, required=required)
        except _app_JsonBodyError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    def _expect_object(self, payload: Any, label: str) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "{0} must be a JSON object".format(label))
        return payload

    def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        _app_send_json_response(self, status, payload)

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
        _app_send_json_error_response(self, status, message)

    def _handle_builtin_docs_get(self) -> bool:
        response = _app_match_builtin_docs_response(self._request_path(), base_url=self._request_base_url())
        if response is None:
            return False
        if response.send_as == "json":
            self._send_json(response.status, response.body)
            return True
        self._send_text(response.status, response.body, content_type=response.content_type or "text/plain; charset=utf-8")
        return True

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

        if request_path == "/api/clef/config":
            self._api_get_clef_config()
            return

        if request_path == "/api/clef/catalog":
            self._api_get_clef_catalog()
            return

        if request_path == "/api/clef/providers":
            self._api_get_clef_providers()
            return

        if request_path == "/api/clef/sources-report":
            self._api_get_clef_sources_report()
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
        if request_path == "/api/locks/cleanup": self._api_post_locks_cleanup(); return
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

        if request_path == "/api/clef/config":
            self._api_post_clef_config()
            return

        if request_path == "/api/clef/clear":
            self._api_post_clef_clear()
            return

        if request_path == "/api/clef/form-selections":
            self._api_post_clef_form_selections()
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
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "compute" and parts[3] == "cancel":
            self._api_post_compute_cancel(parts[2])
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

def _install_route_bindings() -> None:
    global _ROUTE_BINDINGS_INSTALLED
    if _ROUTE_BINDINGS_INSTALLED:
        return
    with _ROUTE_BINDINGS_LOCK:
        if _ROUTE_BINDINGS_INSTALLED:
            return
        import importlib

        for module_name in _ROUTE_MODULE_NAMES:
            module = importlib.import_module("server_routes.{0}".format(module_name))
            for export_name in getattr(module, "__all__", ()):
                export = getattr(module, export_name)
                globals()[export_name] = export
                if export_name.startswith("_api_"):
                    setattr(RangeRequestHandler, export_name, export)

        RangeRequestHandler._parse_single_range = _parse_single_range
        RangeRequestHandler._serve_range = _serve_range
        RangeRequestHandler._send_416 = _send_416
        _ROUTE_BINDINGS_INSTALLED = True


def _require_route_export(name: str) -> Any:
    _install_route_bindings(); export = globals().get(name)
    if export is not None and (getattr(export, "__module__", None), getattr(export, "__name__", None)) != (__name__, name): return export
    for module in (sys.modules.get("server_routes.{0}".format(module_name)) for module_name in _ROUTE_MODULE_NAMES):
        if module is not None and name in getattr(module, "__all__", ()): export = getattr(module, name); globals()[name] = export; name.startswith("_api_") and setattr(RangeRequestHandler, name, export); return export
    raise AttributeError("module {0!r} has no attribute {1!r}".format(__name__, name))

def _set_job_progress(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_set_job_progress")(*args, **kwargs)


def _set_job_complete(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_set_job_complete")(*args, **kwargs)


def _set_job_error(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_set_job_error")(*args, **kwargs)


def _chat_docs_root(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_docs_root")(*args, **kwargs)


def _chat_external_read_roots(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_external_read_roots")(*args, **kwargs)


def _chat_memory_path(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_memory_path")(*args, **kwargs)


def _chat_start_stt_job(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_start_stt_job")(*args, **kwargs)


def _chat_get_job_snapshot(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_get_job_snapshot")(*args, **kwargs)


def _chat_list_jobs(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_list_jobs")(*args, **kwargs)


def _chat_get_job_logs(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_get_job_logs")(*args, **kwargs)


def _chat_onboard_speaker(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_onboard_speaker")(*args, **kwargs)


def _chat_start_compute_job(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_start_compute_job")(*args, **kwargs)


def _chat_pipeline_state(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_chat_pipeline_state")(*args, **kwargs)


def _get_job_snapshot(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_get_job_snapshot")(*args, **kwargs)


def _job_response_payload(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_job_response_payload")(*args, **kwargs)


def _cleanup_old_jobs(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_cleanup_old_jobs")(*args, **kwargs)


def _cleanup_old_chat_sessions(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_cleanup_old_chat_sessions")(*args, **kwargs)


def _resolve_compute_mode(*args: Any, **kwargs: Any) -> Any:
    return _require_route_export("_resolve_compute_mode")(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name.startswith("_") and not name.startswith("__"):
        return _require_route_export(name)
    raise AttributeError("module {0!r} has no attribute {1!r}".format(__name__, name))

def _get_local_ips() -> List[str]:
    ips: List[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.25)
            sock.connect(("8.8.8.8", 80))
            ips.append(sock.getsockname()[0])
    except OSError:
        pass
    return ips


def _startup_banner_lines(
    serve_dir: pathlib.Path,
    local_ips: Sequence[str],
) -> List[str]:
    http_port = _resolve_http_port()
    ws_port = _resolve_ws_port()
    lines = [
        "",
        "=" * 60,
        "  PARSE - HTTP Server",
        "=" * 60,
        "  Serving: {0}".format(serve_dir),
        "  Port   : {0}".format(http_port),
        "  WS Port: {0}".format(ws_port),
        "",
        "  React dev UI (current workflow; requires `npm run dev`):",
        "    Annotate: http://localhost:5173/",
        "    Compare : http://localhost:5173/compare",
    ]
    if _has_built_frontend(serve_dir):
        lines.extend([
            "",
            "  Built UI (served by this Python server after `npm run build`):",
            "    PARSE   : http://localhost:{0}/".format(http_port),
            "    Compare : http://localhost:{0}/compare".format(http_port),
        ])
        for ip in local_ips:
            lines.append("    PARSE   : http://{0}:{1}/".format(ip, http_port))
            lines.append("    Compare : http://{0}:{1}/compare".format(ip, http_port))
    else:
        lines.extend([
            "",
            "  Built UI (served by this Python server after `npm run build`):",
            "    dist/index.html not found — run `npm run build` to serve the frontend here.",
        ])
    lines.extend([
        "",
        "  WebSocket job streaming:",
        "    ws://localhost:{0}/ws/jobs/{{jobId}}".format(ws_port),
        "",
        "  Features: Range requests [x]  CORS [x]  Threaded [x]  API [x]  WS streaming [x]",
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
        self._pool = None
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
        pool = getattr(self, "_pool", None)
        if pool is not None:
            pool.shutdown(wait=False)


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

    os.chdir(serve_dir); _require_route_export("_cleanup_stale_locks_on_startup")()

    _install_route_bindings()

    http_port = _resolve_http_port()
    server_address = (HOST, http_port)
    httpd = _BoundedThreadHTTPServer(server_address, RangeRequestHandler)

    try:
        _start_websocket_sidecar(host=HOST, port=_resolve_ws_port())
    except Exception as exc:
        print(
            "[WARN] WebSocket streaming disabled: {0}".format(exc),
            file=sys.stderr,
            flush=True,
        )

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
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass
        _shutdown_websocket_sidecar()
        _shutdown_persistent_worker()


if __name__ == "__main__":
    main()