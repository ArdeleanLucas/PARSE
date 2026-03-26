"""PARSE HTTP server with static range serving and API endpoints."""

import copy
import http.server
import json
import os
import pathlib
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from ai.provider import get_ipa_provider, get_llm_provider, get_stt_provider, load_ai_config

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

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


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
    result: Dict[str, Any],
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
    payload: Dict[str, Any] = {
        "jobId": str(job.get("jobId") or ""),
        "status": status,
        "progress": _clamp_progress(job.get("progress", 0.0)),
        "result": job.get("result"),
    }

    if job.get("type"):
        payload["type"] = job.get("type")
    if job.get("message"):
        payload["message"] = job.get("message")
    if job.get("error"):
        payload["error"] = str(job.get("error"))

    payload["segmentsProcessed"] = int(job.get("segmentsProcessed", 0) or 0)
    payload["totalSegments"] = int(job.get("totalSegments", 0) or 0)

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


def _run_compute_job(job_id: str, compute_type: str, payload: Dict[str, Any]) -> None:
    try:
        normalized_type = str(compute_type or "").strip().lower()
        _set_job_progress(job_id, 5.0, message="Starting compute job")

        if normalized_type in {"cognates", "similarity"}:
            result = _compute_cognates(job_id, payload)
        else:
            raise RuntimeError("Unsupported compute type: {0}".format(normalized_type))

        _set_job_complete(job_id, result, message="Compute complete")
    except Exception as exc:
        _set_job_error(job_id, str(exc))


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with static range support and PARSE JSON API routes."""

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
        if request_path == "/api/enrichments":
            self._api_get_enrichments()
            return

        if request_path == "/api/config":
            self._api_get_config()
            return

        raise ApiError(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def _dispatch_api_post(self, request_path: str) -> None:
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

        if request_path == "/api/enrichments":
            self._api_post_enrichments()
            return

        if request_path == "/api/config":
            self._api_update_config()
            return

        parts = self._path_parts(request_path)

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

    def _api_get_enrichments(self) -> None:
        payload = _read_json_file(_enrichments_path(), _default_enrichments_payload())
        self._send_json(HTTPStatus.OK, payload)

    def _api_post_enrichments(self) -> None:
        body = self._read_json_body(required=True)
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Enrichments payload must be a JSON object")

        enrichments_payload = body.get("enrichments") if isinstance(body.get("enrichments"), dict) else body
        _write_json_file(_enrichments_path(), enrichments_payload)
        self._send_json(HTTPStatus.OK, {"success": True})

    def _api_get_config(self) -> None:
        config = load_ai_config(_config_path())
        self._send_json(HTTPStatus.OK, config)

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


def main() -> None:
    serve_dir = pathlib.Path.cwd()
    os.chdir(serve_dir)

    server_address = (HOST, PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, RangeRequestHandler)
    local_ips = _get_local_ips()

    print("=" * 60)
    print("  PARSE — HTTP Server")
    print("=" * 60)
    print("  Serving: {0}".format(serve_dir))
    print("  Port   : {0}".format(PORT))
    print()
    print("  URLs:")
    print("    http://localhost:{0}/parse.html".format(PORT))
    print("    http://localhost:{0}/compare.html".format(PORT))
    for ip in local_ips:
        print("    http://{0}:{1}/parse.html".format(ip, PORT))
        print("    http://{0}:{1}/compare.html".format(ip, PORT))
    print()
    print("  Features: Range requests ✓  CORS ✓  Threaded ✓  API ✓")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
