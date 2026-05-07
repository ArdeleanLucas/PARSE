"""Synchronous lexeme interval ORTH/IPA rerun HTTP helpers."""

from __future__ import annotations

import csv
import logging
import math
import time
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from ai.speaker_locks import SpeakerLockError, acquire_speaker_lock as _acquire_speaker_lock, release_speaker_lock as _release_speaker_lock
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


SpeakerNormalizer = Callable[[Any], str]
AnnotationPathResolver = Callable[[str], Path]
JsonAnyReader = Callable[[Path], Any]
AnnotationNormalizer = Callable[[Any, str], dict[str, Any]]
AudioPathResolver = Callable[[str], Path]
IntervalRunner = Callable[..., str]
LockAcquire = Callable[[str, Path], Path]
LockRelease = Callable[[str, Path], None]


@dataclass(frozen=True)
class _RerunRequest:
    speaker: str
    concept_key: str
    start: float
    end: float
    language: Optional[str]


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


def _language_from_body_or_record(body: Mapping[str, Any], record: Mapping[str, Any]) -> Optional[str]:
    raw_language = body.get("language")
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

    return _RerunRequest(
        speaker=speaker,
        concept_key=concept_key,
        start=start,
        end=end,
        language=_language_from_body_or_record(body, record),
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
) -> JsonResponseSpec:
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

    resolved_locks_dir = Path(locks_dir) if locks_dir is not None else Path(project_root) / ".parse-locks"
    lock_file: Path | None = None
    try:
        lock_file = acquire_speaker_lock(request.speaker, resolved_locks_dir)
    except SpeakerLockError as exc:
        raise LexemeRerunHandlerError(HTTPStatus.CONFLICT, "speaker locked") from exc

    started = time.monotonic()
    try:
        audio_path = resolve_audio_path_for_speaker(request.speaker)
        text = runner(audio_path=audio_path, start=request.start, end=request.end, language=request.language)
    except LexemeRerunHandlerError:
        raise
    except Exception as exc:
        logger.error("lexeme %s rerun failed: %s", tier_key, exc)
        raise LexemeRerunHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc
    finally:
        if lock_file is not None:
            try:
                release_speaker_lock(request.speaker, resolved_locks_dir)
            except Exception:
                logger.warning("failed to release lexeme rerun speaker lock for %s", request.speaker)

    elapsed_ms = (time.monotonic() - started) * 1000.0
    logger.info("lexeme %s rerun completed in %.1f ms", tier_key, elapsed_ms)
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            tier_key: str(text or "").strip(),
            "interval": {"start": request.start, "end": request.end},
            "source": "rerun",
        },
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
    )
