"""Helpers for PARSE spectrogram and lexeme-search HTTP endpoints."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Dict, Mapping, Optional

from .job_observability_handlers import JsonResponseSpec
from .request_helpers import request_query_params


@dataclass(frozen=True)
class BinaryResponseSpec:
    status: HTTPStatus
    body: bytes
    headers: Dict[str, str]


@dataclass(frozen=True)
class MediaSearchHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


SpeakerNormalizer = Callable[[Any], str]
ProjectPathResolver = Callable[[str], pathlib.Path]
PrimarySourceResolver = Callable[[str], str]
AnnotationPathResolver = Callable[[str], pathlib.Path]
JsonAnyReader = Callable[[pathlib.Path], Any]
AnnotationNormalizer = Callable[[Any, str], Dict[str, Any]]
SilConfigPathResolver = Callable[[], pathlib.Path]



def _first_query_values(raw_path: str) -> Dict[str, str]:
    return {key: values[0] for key, values in request_query_params(raw_path).items() if values}



def build_get_spectrogram_response(
    raw_path: str,
    *,
    spectro_module: Any,
    normalize_speaker_id: SpeakerNormalizer,
    resolve_project_path: ProjectPathResolver,
    project_root: pathlib.Path,
    annotation_primary_source_wav: PrimarySourceResolver,
    cors_headers: Mapping[str, str],
) -> BinaryResponseSpec:
    params = _first_query_values(raw_path)

    speaker_raw = str(params.get("speaker") or "").strip()
    if not speaker_raw:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "speaker is required")
    try:
        speaker = normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    try:
        start_sec = float(params.get("start") or 0.0)
        end_sec = float(params.get("end") or 0.0)
    except ValueError as exc:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "start and end must be numbers") from exc
    if end_sec <= start_sec:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "end must be greater than start")

    audio_hint = str(params.get("audio") or "").strip()
    audio_path: Optional[pathlib.Path] = None
    if audio_hint:
        try:
            audio_path = resolve_project_path(audio_hint)
        except ValueError as exc:
            raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    else:
        working_candidate = project_root / "audio" / "working" / speaker
        if working_candidate.is_dir():
            for candidate in sorted(working_candidate.iterdir()):
                if candidate.is_file() and candidate.suffix.lower() in {".wav", ".flac"}:
                    audio_path = candidate
                    break
        if audio_path is None:
            primary = annotation_primary_source_wav(speaker)
            if primary:
                try:
                    audio_path = resolve_project_path(primary)
                except ValueError as exc:
                    raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    if audio_path is None or not pathlib.Path(audio_path).is_file():
        raise MediaSearchHandlerError(HTTPStatus.NOT_FOUND, "No audio file resolved for speaker {0}".format(speaker))

    cache_file = spectro_module.cache_path(project_root, speaker, start_sec, end_sec)
    force = str(params.get("force") or "").strip().lower() in {"1", "true", "yes"}
    try:
        spectro_module.generate_spectrogram_png(pathlib.Path(audio_path), start_sec, end_sec, cache_file, force=force)
    except Exception as exc:
        raise MediaSearchHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "spectrogram render failed: {0}".format(exc)) from exc

    png_bytes = cache_file.read_bytes()
    headers = {
        "Content-Type": "image/png",
        "Content-Length": str(len(png_bytes)),
        "Cache-Control": "public, max-age=3600",
    }
    for key, value in cors_headers.items():
        headers[key] = value

    return BinaryResponseSpec(status=HTTPStatus.OK, body=png_bytes, headers=headers)



def build_get_lexeme_search_response(
    raw_path: str,
    *,
    lex_module: Any,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    project_root: pathlib.Path,
    annotation_filename_suffix: str,
    annotation_legacy_filename_suffix: str,
    sil_config_path: SilConfigPathResolver,
) -> JsonResponseSpec:
    params = _first_query_values(raw_path)

    speaker_raw = str(params.get("speaker") or "").strip()
    if not speaker_raw:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "speaker is required")
    try:
        speaker = normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    variants_raw = str(params.get("variants") or "").strip()
    user_variants = [variant for variant in re.split(r"[\s,;/]+", variants_raw) if variant]
    if not user_variants:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "variants is required (comma or space separated)")

    concept_id = str(params.get("concept_id") or "").strip() or None
    language = str(params.get("language") or lex_module.DEFAULT_LANGUAGE).strip() or lex_module.DEFAULT_LANGUAGE

    tiers_raw = str(params.get("tiers") or "").strip()
    tiers_filter: Optional[list[str]] = None
    if tiers_raw:
        tiers_filter = [tier for tier in re.split(r"[\s,;]+", tiers_raw) if tier]

    try:
        limit = int(params.get("limit") or lex_module.DEFAULT_LIMIT)
    except (TypeError, ValueError) as exc:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "limit must be an integer") from exc
    if limit <= 0 or limit > 200:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "limit must be in [1, 200]")

    try:
        max_distance = float(params.get("max_distance") or lex_module.DEFAULT_MAX_DISTANCE)
    except (TypeError, ValueError) as exc:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "max_distance must be a number in (0, 1]") from exc
    if not (0 < max_distance <= 1):
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "max_distance must be in (0, 1]")

    try:
        target_path = annotation_read_path_for_speaker(speaker)
    except ValueError as exc:
        raise MediaSearchHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    if not target_path.is_file():
        raise MediaSearchHandlerError(HTTPStatus.NOT_FOUND, "No annotation record for speaker {0}".format(speaker))
    target_record = normalize_annotation_record(read_json_any_file(target_path), speaker)

    cross_records: list[Dict[str, Any]] = []
    if concept_id:
        annotations_dir = project_root / "annotations"
        if annotations_dir.is_dir():
            for path in sorted(annotations_dir.iterdir()):
                if not path.is_file():
                    continue
                if path.suffix not in {".json"}:
                    continue
                stem = path.name.removesuffix(annotation_filename_suffix).removesuffix(annotation_legacy_filename_suffix)
                if stem == speaker:
                    continue
                try:
                    cross_records.append(normalize_annotation_record(read_json_any_file(path), stem))
                except Exception:
                    continue

    contact_variants: list[str] = []
    if concept_id:
        try:
            contact_variants = lex_module.load_contact_variants(concept_id, sil_config_path())
        except Exception:
            contact_variants = []

    all_variants = list(user_variants)
    seen = set(all_variants)
    for variant in contact_variants:
        if variant not in seen:
            all_variants.append(variant)
            seen.add(variant)

    candidates = lex_module.search(
        target_record,
        all_variants,
        concept_id=concept_id,
        cross_speaker_records=cross_records,
        language=language,
        limit=limit,
        max_distance=max_distance,
        tiers=tiers_filter,
    )
    phonemizer_available = bool(lex_module.phonemize_variant(user_variants[0], language=language))

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "speaker": speaker,
            "concept_id": concept_id,
            "variants": user_variants,
            "language": language,
            "candidates": candidates,
            "signals_available": {
                "phonemizer": phonemizer_available,
                "cross_speaker_anchors": sum(
                    1
                    for record in cross_records
                    if concept_id and str(concept_id) in ((record or {}).get("confirmed_anchors") or {})
                ),
                "contact_variants": contact_variants,
            },
        },
    )
