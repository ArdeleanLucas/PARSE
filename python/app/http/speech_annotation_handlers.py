"""Helpers for PARSE speech-job and suggestion HTTP endpoints."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Mapping, Optional, Type, Union

from .job_observability_handlers import JsonResponseSpec


@dataclass(frozen=True)
class SpeechAnnotationHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


SpeakerNormalizer = Callable[[Any], str]
SttCachePathResolver = Callable[[str], pathlib.Path]
PrimarySourceResolver = Callable[[str], str]
JobCreator = Callable[[str, Dict[str, Any]], str]
NormalizeLauncher = Callable[[str, str, str], None]
ComputeLauncher = Callable[[str, str, Dict[str, Any]], None]
JobSnapshotGetter = Callable[[str], Optional[Dict[str, Any]]]
JobResponsePayloadBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]
SuggestionProviderFactory = Callable[[], Any]
CachedSuggestionsLoader = Callable[[str, List[str]], List[Dict[str, Any]]]
ConceptIdListCoercer = Callable[[Any], List[str]]
ExceptionSpec = Union[Type[BaseException], tuple[Type[BaseException], ...], None]



def build_get_stt_segments_response(
    speaker_part: str,
    *,
    normalize_speaker_id: SpeakerNormalizer,
    stt_cache_path: SttCachePathResolver,
) -> JsonResponseSpec:
    try:
        speaker = normalize_speaker_id(speaker_part)
    except ValueError as exc:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    cache_path = stt_cache_path(speaker)
    if not cache_path.exists():
        return JsonResponseSpec(
            status=HTTPStatus.OK,
            payload={"speaker": speaker, "segments": []},
        )

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise SpeechAnnotationHandlerError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Failed to read STT cache: {0}".format(exc),
        ) from exc

    if not isinstance(data, dict):
        data = {"speaker": speaker, "segments": []}
    data.setdefault("speaker", speaker)
    segments = data.get("segments") if isinstance(data.get("segments"), list) else []
    data["segments"] = segments
    return JsonResponseSpec(status=HTTPStatus.OK, payload=data)



def build_post_normalize_response(
    body: Mapping[str, Any],
    *,
    callback_url: Optional[str],
    normalize_speaker_id: SpeakerNormalizer,
    annotation_primary_source_wav: PrimarySourceResolver,
    create_job: JobCreator,
    launch_normalize_job: NormalizeLauncher,
    job_conflict_error_cls: ExceptionSpec,
) -> JsonResponseSpec:
    speaker_raw = str(body.get("speaker") or "").strip()
    if not speaker_raw:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "speaker is required")

    try:
        speaker = normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    source_wav = str(body.get("sourceWav") or body.get("source_wav") or "").strip()
    if not source_wav:
        source_wav = annotation_primary_source_wav(speaker)
    if not source_wav:
        raise SpeechAnnotationHandlerError(
            HTTPStatus.BAD_REQUEST,
            "No source audio found for speaker '{0}'. Provide sourceWav explicitly.".format(speaker),
        )

    try:
        job_id = create_job(
            "normalize",
            {
                "speaker": speaker,
                "sourceWav": source_wav,
                "callbackUrl": callback_url,
            },
        )
    except Exception as exc:
        if job_conflict_error_cls and isinstance(exc, job_conflict_error_cls):
            raise SpeechAnnotationHandlerError(HTTPStatus.CONFLICT, str(exc)) from exc
        raise

    launch_normalize_job(job_id, speaker, source_wav)
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"job_id": job_id, "jobId": job_id, "status": "running"},
    )



def build_post_normalize_status_response(
    body: Mapping[str, Any],
    *,
    get_job_snapshot: JobSnapshotGetter,
    job_response_payload: JobResponsePayloadBuilder,
) -> JsonResponseSpec:
    job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
    if not job_id:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "job_id is required")

    job = get_job_snapshot(job_id)
    if job is None:
        raise SpeechAnnotationHandlerError(HTTPStatus.NOT_FOUND, "Unknown job_id")
    if str(job.get("type") or "") != "normalize":
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "job_id is not a normalize job")

    return JsonResponseSpec(status=HTTPStatus.OK, payload=job_response_payload(job))



def build_post_stt_start_response(
    body: Mapping[str, Any],
    *,
    callback_url: Optional[str],
    create_job: JobCreator,
    launch_compute_runner: ComputeLauncher,
    job_conflict_error_cls: ExceptionSpec,
) -> JsonResponseSpec:
    speaker = str(body.get("speaker") or "").strip()
    source_wav = str(body.get("sourceWav") or body.get("source_wav") or "").strip()

    language_raw = body.get("language")
    language = str(language_raw).strip() if language_raw is not None else None
    if language == "":
        language = None

    if not speaker:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "speaker is required")
    if not source_wav:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "sourceWav is required")

    try:
        job_id = create_job(
            "stt",
            {
                "speaker": speaker,
                "sourceWav": source_wav,
                "language": language,
                "callbackUrl": callback_url,
            },
        )
    except Exception as exc:
        if job_conflict_error_cls and isinstance(exc, job_conflict_error_cls):
            raise SpeechAnnotationHandlerError(HTTPStatus.CONFLICT, str(exc)) from exc
        raise

    launch_compute_runner(job_id, "stt", {"speaker": speaker, "sourceWav": source_wav, "language": language})
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": job_id, "status": "running"},
    )



def build_post_stt_status_response(
    body: Mapping[str, Any],
    *,
    get_job_snapshot: JobSnapshotGetter,
    job_response_payload: JobResponsePayloadBuilder,
) -> JsonResponseSpec:
    job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
    if not job_id:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "jobId is required")

    job = get_job_snapshot(job_id)
    if job is None:
        raise SpeechAnnotationHandlerError(HTTPStatus.NOT_FOUND, "Unknown jobId")
    if str(job.get("type") or "") != "stt":
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "jobId is not an STT job")

    return JsonResponseSpec(status=HTTPStatus.OK, payload=job_response_payload(job))



def build_post_suggest_response(
    body: Mapping[str, Any],
    *,
    get_llm_provider: SuggestionProviderFactory,
    load_cached_suggestions: CachedSuggestionsLoader,
    coerce_concept_id_list: ConceptIdListCoercer,
) -> JsonResponseSpec:
    speaker = str(body.get("speaker") or "").strip()
    if not speaker:
        raise SpeechAnnotationHandlerError(HTTPStatus.BAD_REQUEST, "speaker is required")

    concept_ids = coerce_concept_id_list(body.get("conceptIds") or body.get("concept_ids") or [])
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
        suggestions = load_cached_suggestions(speaker, concept_ids)

    return JsonResponseSpec(status=HTTPStatus.OK, payload={"suggestions": suggestions})
