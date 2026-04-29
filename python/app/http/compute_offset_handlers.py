"""Helpers for PARSE compute and timestamp-offset HTTP endpoints."""

from __future__ import annotations

import math
import pathlib
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Dict, Mapping, Optional, Type, Union

from .job_observability_handlers import JsonResponseSpec


@dataclass(frozen=True)
class ComputeOffsetHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


JobCreator = Callable[[str, Dict[str, Any]], str]
ComputeLauncher = Callable[[str, str, Dict[str, Any]], None]
SpeakerNormalizer = Callable[[Any], str]
AnnotationPathResolver = Callable[[str], pathlib.Path]
JsonReader = Callable[[pathlib.Path], Dict[str, Any]]
AnnotationNormalizer = Callable[[Dict[str, Any], str], Dict[str, Any]]
AnnotationShifter = Callable[[Dict[str, Any], float], Union[tuple[int, int], tuple[int, int, int]]]
AnnotationToucher = Callable[[Dict[str, Any], bool], None]
JsonWriter = Callable[[pathlib.Path, Dict[str, Any]], None]
JobSnapshotGetter = Callable[[str], Optional[Dict[str, Any]]]
JobResponsePayloadBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]
ExceptionSpec = Union[Type[BaseException], tuple[Type[BaseException], ...], None]



def _job_started_response(job_id: str) -> JsonResponseSpec:
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": job_id, "status": "running"},
    )



def _normalize_speaker_or_raise(raw_speaker: Any, *, normalize_speaker_id: SpeakerNormalizer) -> str:
    try:
        return normalize_speaker_id(raw_speaker)
    except ValueError as exc:
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc



def _count_protected_lexemes(annotation: Dict[str, Any]) -> int:
    concept_tier = annotation.get("tiers", {}).get("concept") if isinstance(annotation, dict) else None
    if not isinstance(concept_tier, dict):
        return 0
    concept_intervals = concept_tier.get("intervals")
    if not isinstance(concept_intervals, list):
        return 0
    return sum(
        1
        for iv in concept_intervals
        if isinstance(iv, dict) and bool(iv.get("manuallyAdjusted"))
    )



def build_post_offset_detect_response(
    body: Mapping[str, Any],
    *,
    normalize_speaker_id: SpeakerNormalizer,
    create_job: JobCreator,
    launch_compute_runner: ComputeLauncher,
) -> JsonResponseSpec:
    speaker = _normalize_speaker_or_raise(body.get("speaker"), normalize_speaker_id=normalize_speaker_id)
    compute_payload: Dict[str, Any] = {
        "speaker": speaker,
        "nAnchors": body.get("nAnchors") or body.get("n_anchors"),
        "bucketSec": body.get("bucketSec") or body.get("bucket_sec"),
        "minMatchScore": body.get("minMatchScore") or body.get("min_match_score"),
        "distribution": body.get("distribution") or body.get("anchorDistribution"),
        "sttJobId": body.get("sttJobId") or body.get("stt_job_id"),
        "sttSegments": body.get("sttSegments") or body.get("stt_segments"),
    }
    job_id = create_job("compute:offset_detect", {"speaker": speaker})
    launch_compute_runner(job_id, "offset_detect", compute_payload)
    return _job_started_response(job_id)



def build_post_offset_detect_from_pair_response(
    body: Mapping[str, Any],
    *,
    normalize_speaker_id: SpeakerNormalizer,
    create_job: JobCreator,
    launch_compute_runner: ComputeLauncher,
) -> JsonResponseSpec:
    speaker = _normalize_speaker_or_raise(body.get("speaker"), normalize_speaker_id=normalize_speaker_id)

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
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "pairs must be a non-empty array")

    compute_payload: Dict[str, Any] = {"speaker": speaker, "pairs": raw_pairs}
    job_id = create_job("compute:offset_detect_from_pair", {"speaker": speaker})
    launch_compute_runner(job_id, "offset_detect_from_pair", compute_payload)
    return _job_started_response(job_id)



def build_post_offset_apply_response(
    body: Mapping[str, Any],
    *,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonReader,
    normalize_annotation_record: AnnotationNormalizer,
    annotation_shift_intervals: AnnotationShifter,
    annotation_touch_metadata: AnnotationToucher,
    annotation_record_path_for_speaker: AnnotationPathResolver,
    write_json_file: JsonWriter,
) -> JsonResponseSpec:
    speaker = _normalize_speaker_or_raise(body.get("speaker"), normalize_speaker_id=normalize_speaker_id)

    offset_raw = body.get("offsetSec")
    if offset_raw is None:
        offset_raw = body.get("offset_sec")
    if offset_raw is None:
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "offsetSec is required")

    try:
        offset_sec = float(offset_raw)
    except (TypeError, ValueError) as exc:
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "offsetSec must be a number") from exc
    if not math.isfinite(offset_sec):
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "offsetSec must be a finite number")
    if abs(offset_sec) < 1e-6:
        raise ComputeOffsetHandlerError(
            HTTPStatus.BAD_REQUEST,
            "offsetSec is effectively zero — nothing to apply",
        )

    annotation_path = annotation_read_path_for_speaker(speaker)
    annotation = normalize_annotation_record(read_json_any_file(annotation_path), speaker)
    shift_result = annotation_shift_intervals(annotation, offset_sec)
    shifted_count = int(shift_result[0]) if len(shift_result) >= 1 else 0
    protected_count = int(shift_result[1]) if len(shift_result) >= 2 else 0
    shifted_concepts = int(shift_result[2]) if len(shift_result) >= 3 else 0
    if shifted_count == 0 and protected_count == 0:
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "No intervals were shifted")

    protected_lexemes = _count_protected_lexemes(annotation)
    if shifted_count > 0:
        annotation_touch_metadata(annotation, True)
        write_path = annotation_record_path_for_speaker(speaker)
        write_json_file(write_path, annotation)

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "speaker": speaker,
            "appliedOffsetSec": offset_sec,
            "shiftedIntervals": shifted_count,
            "shiftedConcepts": shifted_concepts,
            "protectedIntervals": protected_count,
            "protectedLexemes": protected_lexemes,
        },
    )



def build_post_compute_start_response(
    compute_type: str,
    body: Mapping[str, Any],
    *,
    callback_url: Optional[str],
    create_job: JobCreator,
    launch_compute_runner: ComputeLauncher,
    job_conflict_error_cls: ExceptionSpec,
) -> JsonResponseSpec:
    normalized_type = str(compute_type or "").strip().lower()
    if not normalized_type or normalized_type == "status":
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "Compute type is required")

    speaker = str(body.get("speaker") or "").strip() or None
    job_metadata: Dict[str, Any] = {
        "computeType": normalized_type,
        "payload": dict(body),
        "callbackUrl": callback_url,
    }
    if speaker:
        job_metadata["speaker"] = speaker

    try:
        job_id = create_job("compute:{0}".format(normalized_type), job_metadata)
    except Exception as exc:
        if job_conflict_error_cls and isinstance(exc, job_conflict_error_cls):
            raise ComputeOffsetHandlerError(HTTPStatus.CONFLICT, str(exc)) from exc
        raise

    launch_compute_runner(job_id, normalized_type, dict(body))
    return _job_started_response(job_id)



def build_post_compute_status_response(
    compute_type: Optional[str],
    body: Mapping[str, Any],
    *,
    get_job_snapshot: JobSnapshotGetter,
    job_response_payload: JobResponsePayloadBuilder,
) -> JsonResponseSpec:
    job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
    if not job_id:
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "jobId is required")

    job = get_job_snapshot(job_id)
    if job is None:
        raise ComputeOffsetHandlerError(HTTPStatus.NOT_FOUND, "Unknown jobId")

    job_type = str(job.get("type") or "")
    if not job_type.startswith("compute:"):
        raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "jobId is not a compute job")

    if compute_type:
        expected_type = str(compute_type).strip().lower()
        if job_type != "compute:{0}".format(expected_type):
            raise ComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "jobId does not match compute type")

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload=job_response_payload(job),
    )
