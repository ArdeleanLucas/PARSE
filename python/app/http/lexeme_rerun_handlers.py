"""Job-tracked lexeme interval ORTH/IPA rerun HTTP helpers.

Requests accept ``pad`` values ``0.0``, ``0.2`` (default), or ``0.5``.
The pad widens the acoustic window passed to the ORTH/IPA runner while the
JSON response reports the original user-selected interval bounds.
"""

from __future__ import annotations

import csv
import logging
import math
import time
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from ai.provider import confidence_wire_fields
from ai.speaker_locks import SpeakerLockError, acquire_speaker_lock as _acquire_speaker_lock, release_speaker_lock as _release_speaker_lock
from ai.ipa_transcribe import MIN_TRANSCRIBE_SLICE_SEC
from concept_registry import concept_label_key, load_concept_registry
from concept_source_item import row_value

from .job_observability_handlers import JsonResponseSpec

logger = logging.getLogger(__name__)

MAX_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True)
class LexemeRerunHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class LexemeRerunSubprocessError(Exception):
    code: str
    exit_code: int | None
    message: str
    stderr_tail: str | None = None

    def __str__(self) -> str:
        return self.message


class LexemeRerunComputeError(RuntimeError):
    def __init__(self, message: str, *, error_code: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = dict(details or {})


SpeakerNormalizer = Callable[[Any], str]
AnnotationPathResolver = Callable[[str], Path]
JsonAnyReader = Callable[[Path], Any]
AnnotationNormalizer = Callable[[Any, str], dict[str, Any]]
AudioPathResolver = Callable[[str], Path]
IntervalRunner = Callable[..., Any]
LockAcquire = Callable[[str, Path], Path]
LockRelease = Callable[[str, Path], None]
JobCreator = Callable[[str, dict[str, Any]], str]
ComputeLauncher = Callable[[str, str, dict[str, Any]], None]
ExceptionSpec = type[BaseException] | tuple[type[BaseException], ...] | None


@dataclass(frozen=True)
class _RerunRequest:
    speaker: str
    concept_key: str
    start: float
    end: float
    language: Optional[str]
    pad: float


@dataclass(frozen=True)
class _RerunPlan:
    tier_key: str
    speaker: str
    concept_key: str
    start: float
    end: float
    language: Optional[str]
    pad: float

    @property
    def padded_start(self) -> float:
        return max(0.0, self.start - self.pad)

    @property
    def padded_end(self) -> float:
        return self.end + self.pad


def _request_string(body: Mapping[str, Any], *names: str) -> str:
    for name in names:
        raw = body.get(name)
        if raw is not None:
            return str(raw).strip()
    return ""


def _coerce_interval_float(body: Mapping[str, Any], key: str) -> float:
    if key not in body:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "interval {0} is required".format(key))
    try:
        value = float(body.get(key))
    except (TypeError, ValueError) as exc:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "interval {0} must be a finite number".format(key)) from exc
    if not math.isfinite(value):
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "interval {0} must be a finite number".format(key))
    return value


def _coerce_pad(body: Mapping[str, Any]) -> float:
    raw = body.get("pad", 0.2)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "pad must be one of 0.0, 0.2, 0.5") from exc
    if not math.isfinite(value) or value not in {0.0, 0.2, 0.5}:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "pad must be one of 0.0, 0.2, 0.5")
    return value


def _language_from_body_or_record(body: Mapping[str, Any], record: Mapping[str, Any]) -> Optional[str]:
    raw_language = body.get("language")
    # Undocumented escape hatch — frontend doesn't send this; metadata fallback is the canonical source.
    if raw_language is not None:
        language = str(raw_language).strip()
        return language or None
    metadata = record.get("metadata")
    if isinstance(metadata, Mapping):
        language = str(metadata.get("language_code") or "").strip()
        if language and language != "und":
            return language
    return None


def _parse_request(body: Mapping[str, Any], *, normalize_speaker_id: SpeakerNormalizer, record: Mapping[str, Any]) -> _RerunRequest:
    speaker_raw = _request_string(body, "speaker")
    concept_key = _request_string(body, "concept_key", "conceptKey")
    if not speaker_raw or not concept_key:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "speaker and concept_key are required")
    try:
        speaker = normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    start = _coerce_interval_float(body, "start")
    end = _coerce_interval_float(body, "end")
    if start < 0.0:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "interval start must be >= 0")
    if end <= start:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "interval end must be greater than start")
    if (end - start) > MAX_INTERVAL_SECONDS:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "interval duration must be <= 60.0 seconds")
    duration_sec = end - start
    if duration_sec < MIN_TRANSCRIBE_SLICE_SEC:
        raise LexemeRerunHandlerError(
            HTTPStatus.BAD_REQUEST,
            "interval_too_short: duration_ms={0:.1f} minimum_ms=80.0".format(duration_sec * 1000.0),
        )

    return _RerunRequest(
        speaker=speaker,
        concept_key=concept_key,
        start=start,
        end=end,
        language=_language_from_body_or_record(body, record),
        pad=_coerce_pad(body),
    )


def _concept_key_exists(project_root: Path, concept_key: str) -> bool:
    key = str(concept_key or "").strip()
    if not key:
        return False
    label_key = concept_label_key(key)

    registry = load_concept_registry(Path(project_root))
    for row in registry.raw_rows:
        if _row_matches_concept_key(row, key, label_key):
            return True

    # Fallback for rows ConceptRegistry filters out (e.g. empty concept_en).
    concepts_path = Path(project_root) / "concepts.csv"
    if not concepts_path.exists():
        return False
    try:
        with concepts_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if _row_matches_concept_key(row, key, label_key):
                    return True
    except (OSError, UnicodeDecodeError, csv.Error):
        return False
    return False


def _row_matches_concept_key(row: Mapping[str, Any], key: str, label_key: str) -> bool:
    exact_candidates = (
        row_value(row, "id"),
        row_value(row, "source_item", "survey_item"),
        row_value(row, "concept_key", "key"),
    )
    if any(candidate == key for candidate in exact_candidates if candidate):
        return True
    label = row_value(row, "concept_en", "label")
    return bool(label and concept_label_key(label) == label_key)


def _load_record(
    speaker: str,
    *,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
) -> dict[str, Any]:
    annotation_path = annotation_read_path_for_speaker(speaker)
    if not annotation_path.is_file():
        raise LexemeRerunHandlerError(HTTPStatus.NOT_FOUND, "speaker not found")
    payload = read_json_any_file(annotation_path)
    if not isinstance(payload, dict):
        raise LexemeRerunHandlerError(HTTPStatus.NOT_FOUND, "speaker not found")
    try:
        normalized = normalize_annotation_record(payload, speaker)
    except Exception as exc:
        raise LexemeRerunHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc
    if not isinstance(normalized, dict):
        raise LexemeRerunHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "annotation record is not a JSON object")
    return normalized


def _build_lexeme_rerun_plan(
    body: Mapping[str, Any],
    *,
    tier_key: str,
    project_root: Path,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
) -> _RerunPlan:
    # Speaker validation needs the normalized speaker first, but interval/language
    # parsing also depends on the read-only annotation metadata. Do this in two
    # deliberate phases so missing-speaker returns 404 instead of provider errors.
    speaker_raw = _request_string(body, "speaker")
    concept_key_raw = _request_string(body, "concept_key", "conceptKey")
    if not speaker_raw or not concept_key_raw:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, "speaker and concept_key are required")
    try:
        speaker = normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise LexemeRerunHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    record = _load_record(
        speaker,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
    )
    request = _parse_request(body, normalize_speaker_id=normalize_speaker_id, record=record)
    if not _concept_key_exists(project_root, request.concept_key):
        raise LexemeRerunHandlerError(HTTPStatus.NOT_FOUND, "concept not found")
    return _RerunPlan(
        tier_key=tier_key,
        speaker=request.speaker,
        concept_key=request.concept_key,
        start=request.start,
        end=request.end,
        language=request.language,
        pad=request.pad,
    )


def _subprocess_error_payload(exc: LexemeRerunSubprocessError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "code": exc.code,
        "exit_code": exc.exit_code,
        "message": exc.message,
    }
    if exc.stderr_tail:
        payload["stderr_tail"] = exc.stderr_tail
    return payload


def _run_lexeme_rerun_plan_sync(
    plan: _RerunPlan,
    *,
    project_root: Path,
    resolve_audio_path_for_speaker: AudioPathResolver,
    runner: IntervalRunner,
    locks_dir: Path | None = None,
    acquire_speaker_lock: LockAcquire = _acquire_speaker_lock,
    release_speaker_lock: LockRelease = _release_speaker_lock,
    subprocess_errors_as_response: bool = True,
) -> JsonResponseSpec:
    resolved_locks_dir = Path(locks_dir) if locks_dir is not None else Path(project_root) / ".parse-locks"
    lock_file: Path | None = None
    try:
        lock_file = acquire_speaker_lock(plan.speaker, resolved_locks_dir)
    except SpeakerLockError as exc:
        if subprocess_errors_as_response:
            raise LexemeRerunHandlerError(HTTPStatus.CONFLICT, "speaker locked") from exc
        raise LexemeRerunComputeError("speaker locked", error_code="speaker_locked") from exc

    started = time.monotonic()
    try:
        audio_path = resolve_audio_path_for_speaker(plan.speaker)
        runner_result = runner(audio_path=audio_path, start=plan.padded_start, end=plan.padded_end, language=plan.language)
    except LexemeRerunSubprocessError as exc:
        if not subprocess_errors_as_response:
            details = _subprocess_error_payload(exc)
            raise LexemeRerunComputeError(exc.message, error_code="lexeme_rerun_subprocess", details=details) from exc
        return JsonResponseSpec(status=HTTPStatus.SERVICE_UNAVAILABLE, payload=_subprocess_error_payload(exc))
    except LexemeRerunHandlerError:
        raise
    except Exception as exc:
        logger.error("lexeme %s rerun failed: %s", plan.tier_key, exc)
        raise LexemeRerunHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc
    finally:
        if lock_file is not None:
            try:
                release_speaker_lock(plan.speaker, resolved_locks_dir)
            except Exception:
                logger.warning("failed to release lexeme rerun speaker lock for %s", plan.speaker, exc_info=True)

    if isinstance(runner_result, Mapping):
        text_raw = runner_result.get("text") or runner_result.get(plan.tier_key) or runner_result.get("transcript") or ""
        confidence_raw = runner_result.get("confidence")
    else:
        text_raw = runner_result
        confidence_raw = None

    payload: dict[str, Any] = {
        plan.tier_key: str(text_raw or "").strip(),
        "interval": {"start": plan.start, "end": plan.end},
        "source": "rerun",
        "jobId": None,
    }
    if confidence_raw is not None:
        payload.update(confidence_wire_fields(confidence_raw))

    elapsed_ms = (time.monotonic() - started) * 1000.0
    logger.info("lexeme %s rerun completed in %.1f ms", plan.tier_key, elapsed_ms)
    return JsonResponseSpec(status=HTTPStatus.OK, payload=payload)


def _build_lexeme_rerun_job_response(
    plan: _RerunPlan,
    *,
    create_job: JobCreator | None,
    launch_compute_runner: ComputeLauncher | None,
    job_conflict_error_cls: ExceptionSpec = None,
) -> JsonResponseSpec:
    if create_job is None or launch_compute_runner is None:
        raise LexemeRerunHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "async lexeme rerun job dependencies are not configured")
    compute_type = "lexeme_rerun_{0}".format(plan.tier_key)
    metadata: dict[str, Any] = {
        "computeType": compute_type,
        "speaker": plan.speaker,
        "concept_key": plan.concept_key,
        "tier": plan.tier_key,
        "interval": {"start": plan.start, "end": plan.end},
        "pad": plan.pad,
    }
    payload = {
        "speaker": plan.speaker,
        "concept_key": plan.concept_key,
        "start": plan.start,
        "end": plan.end,
        "language": plan.language,
        "pad": plan.pad,
    }
    try:
        job_id = create_job("compute:{0}".format(compute_type), metadata)
    except Exception as exc:
        if job_conflict_error_cls is not None and isinstance(exc, job_conflict_error_cls):
            raise LexemeRerunHandlerError(HTTPStatus.CONFLICT, str(exc)) from exc
        raise
    launch_compute_runner(job_id, compute_type, payload)
    return JsonResponseSpec(status=HTTPStatus.ACCEPTED, payload={"jobId": job_id})


def _build_post_run_response(
    body: Mapping[str, Any],
    *,
    tier_key: str,
    project_root: Path,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    resolve_audio_path_for_speaker: AudioPathResolver,
    runner: IntervalRunner,
    locks_dir: Path | None = None,
    acquire_speaker_lock: LockAcquire = _acquire_speaker_lock,
    release_speaker_lock: LockRelease = _release_speaker_lock,
    create_job: JobCreator | None = None,
    launch_compute_runner: ComputeLauncher | None = None,
    job_conflict_error_cls: ExceptionSpec = None,
) -> JsonResponseSpec:
    plan = _build_lexeme_rerun_plan(
        body,
        tier_key=tier_key,
        project_root=project_root,
        normalize_speaker_id=normalize_speaker_id,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
    )
    if body.get("async") is False:
        return _run_lexeme_rerun_plan_sync(
            plan,
            project_root=project_root,
            resolve_audio_path_for_speaker=resolve_audio_path_for_speaker,
            runner=runner,
            locks_dir=locks_dir,
            acquire_speaker_lock=acquire_speaker_lock,
            release_speaker_lock=release_speaker_lock,
        )
    return _build_lexeme_rerun_job_response(
        plan,
        create_job=create_job,
        launch_compute_runner=launch_compute_runner,
        job_conflict_error_cls=job_conflict_error_cls,
    )

def build_post_run_ortho_response(
    body: Mapping[str, Any],
    *,
    project_root: Path,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    resolve_audio_path_for_speaker: AudioPathResolver,
    run_ortho_interval: IntervalRunner,
    locks_dir: Path | None = None,
    acquire_speaker_lock: LockAcquire = _acquire_speaker_lock,
    release_speaker_lock: LockRelease = _release_speaker_lock,
    create_job: JobCreator | None = None,
    launch_compute_runner: ComputeLauncher | None = None,
    job_conflict_error_cls: ExceptionSpec = None,
) -> JsonResponseSpec:
    return _build_post_run_response(
        body,
        tier_key="ortho",
        project_root=project_root,
        normalize_speaker_id=normalize_speaker_id,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
        resolve_audio_path_for_speaker=resolve_audio_path_for_speaker,
        runner=run_ortho_interval,
        locks_dir=locks_dir,
        acquire_speaker_lock=acquire_speaker_lock,
        release_speaker_lock=release_speaker_lock,
        create_job=create_job,
        launch_compute_runner=launch_compute_runner,
        job_conflict_error_cls=job_conflict_error_cls,
    )


def build_post_run_ipa_response(
    body: Mapping[str, Any],
    *,
    project_root: Path,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    resolve_audio_path_for_speaker: AudioPathResolver,
    run_ipa_interval: IntervalRunner,
    locks_dir: Path | None = None,
    acquire_speaker_lock: LockAcquire = _acquire_speaker_lock,
    release_speaker_lock: LockRelease = _release_speaker_lock,
    create_job: JobCreator | None = None,
    launch_compute_runner: ComputeLauncher | None = None,
    job_conflict_error_cls: ExceptionSpec = None,
) -> JsonResponseSpec:
    return _build_post_run_response(
        body,
        tier_key="ipa",
        project_root=project_root,
        normalize_speaker_id=normalize_speaker_id,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
        resolve_audio_path_for_speaker=resolve_audio_path_for_speaker,
        runner=run_ipa_interval,
        locks_dir=locks_dir,
        acquire_speaker_lock=acquire_speaker_lock,
        release_speaker_lock=release_speaker_lock,
        create_job=create_job,
        launch_compute_runner=launch_compute_runner,
        job_conflict_error_cls=job_conflict_error_cls,
    )
