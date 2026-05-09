"""HTTP handlers for tag-filtered concept queries and lexeme rerun.

Both routes share resolution logic (tag vocabulary lookup + speaker
expansion + concept-tier filtering) provided by
``app.services.tag_resolver``.

The handlers are pure: every dependency on the rest of the server (audio
path resolution, annotation reading, the per-interval rerun runners) is
injected as a callable. This mirrors the pattern in
``app.http.lexeme_rerun_handlers``.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.services.tag_resolver import (
    ConceptHit,
    ResolvedTags,
    SpeakerExpansionError,
    expand_speakers,
    resolve_tag_labels,
    select_concepts_by_tag,
)

from .job_observability_handlers import JsonResponseSpec
from .lexeme_rerun_handlers import LexemeRerunHandlerError

logger = logging.getLogger(__name__)


_PAD_VALUES = (0.0, 0.2, 0.5)
_VALID_FIELDS = ("ipa", "ortho", "both")


@dataclass(frozen=True)
class TagFilteredHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


def _coerce_match(body: Mapping[str, Any]) -> str:
    raw = body.get("match", "any")
    value = str(raw).strip().lower() if raw is not None else "any"
    if value not in ("any", "all"):
        raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, "match must be 'any' or 'all'")
    return value


def _coerce_tag_labels(body: Mapping[str, Any]) -> list[str]:
    raw = body.get("tagLabels")
    if not isinstance(raw, list) or not raw:
        raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, "tagLabels must be a non-empty list of strings")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, "tagLabels must contain only strings")
        out.append(item)
    return out


def _coerce_pad(body: Mapping[str, Any]) -> float:
    raw = body.get("pad", 0.2)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, "pad must be one of 0.0, 0.2, 0.5") from exc
    if not math.isfinite(value) or value not in _PAD_VALUES:
        raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, "pad must be one of 0.0, 0.2, 0.5")
    return value


def _coerce_field(body: Mapping[str, Any]) -> str:
    raw = body.get("field")
    if not isinstance(raw, str):
        raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, "field must be one of ipa, ortho, both")
    value = raw.strip().lower()
    if value not in _VALID_FIELDS:
        raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, "field must be one of ipa, ortho, both")
    return value


def _expand(body: Mapping[str, Any], project_root: Path) -> list[str]:
    raw = body.get("speakers")
    try:
        return expand_speakers(raw, project_root)
    except SpeakerExpansionError as exc:
        # Distinguish "speakers shape" (400) from "unknown named speaker" (404).
        if isinstance(raw, list):
            raise TagFilteredHandlerError(HTTPStatus.NOT_FOUND, str(exc)) from exc
        raise TagFilteredHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc


def _format_label_list(labels: Sequence[str]) -> str:
    return ", ".join("'{0}'".format(label) for label in labels)


def _format_ambiguous(ambiguous: Mapping[str, Sequence[str]]) -> str:
    parts = []
    for label, candidates in ambiguous.items():
        parts.append("'{0}' -> [{1}]".format(label, ", ".join(candidates)))
    return "; ".join(parts)


def _enforce_all_match_label_strictness(match: str, resolved: ResolvedTags) -> None:
    """When ``match='all'``, every requested label must resolve to exactly one tag.

    Unknown or ambiguous labels under AND semantics would silently degrade to
    "intersection over the resolved subset," which is not what the caller asked
    for. Surface a 400 listing the offending labels so the FE/MCP can fix the
    request before retrying.
    """
    if match != "all":
        return
    problems: list[str] = []
    if resolved.unknown:
        problems.append("unknown tagLabels: {0}".format(_format_label_list(resolved.unknown)))
    if resolved.ambiguous:
        problems.append(
            "ambiguous tagLabels (resolve by id or rename in the vocab): {0}".format(
                _format_ambiguous(resolved.ambiguous)
            )
        )
    if problems:
        raise TagFilteredHandlerError(
            HTTPStatus.BAD_REQUEST,
            "match='all' requires every tagLabel to resolve to exactly one tag; {0}".format(
                "; ".join(problems)
            ),
        )


def _id_to_label(vocab: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in vocab:
        if not isinstance(entry, Mapping):
            continue
        tag_id = entry.get("id")
        label = entry.get("label")
        if isinstance(tag_id, str) and isinstance(label, str):
            out[tag_id] = label
    return out


def _hit_to_payload(hit: ConceptHit, id_to_label: Mapping[str, str]) -> dict[str, Any]:
    labels = [id_to_label.get(tid, tid) for tid in hit.tags]
    return {
        "conceptId": hit.conceptId,
        "name": hit.name,
        "start": hit.start,
        "end": hit.end,
        "tags": labels,
    }


SpeakerNormalizer = Callable[[Any], str]
AnnotationPathResolver = Callable[[str], Path]
JsonAnyReader = Callable[[Path], Any]
AnnotationNormalizer = Callable[[Any, str], dict[str, Any]]
AudioPathResolver = Callable[[str], Path]
IntervalRunner = Callable[..., str]
TagsVocabLoader = Callable[[], Sequence[Mapping[str, Any]]]
PerIntervalHandler = Callable[..., Any]


def _resolve_per_speaker(
    speakers: list[str],
    tag_ids: list[str],
    match: str,
    *,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    id_to_label: Mapping[str, str],
) -> tuple[dict[str, dict[str, Any]], list[ConceptHit], dict[str, list[ConceptHit]]]:
    """Walk speakers once; emit JSON-serializable perSpeaker plus internal hits keyed by speaker.

    The internal map preserves ConceptHit objects for downstream rerun looping
    so we don't reparse the JSON twice.
    """
    per_speaker: dict[str, dict[str, Any]] = {}
    all_hits: list[ConceptHit] = []
    by_speaker: dict[str, list[ConceptHit]] = {}
    for speaker in speakers:
        annotation_path = annotation_read_path_for_speaker(speaker)
        record: Mapping[str, Any] = {}
        if annotation_path.is_file():
            payload = read_json_any_file(annotation_path)
            try:
                normalized = normalize_annotation_record(payload, speaker)
            except Exception:
                normalized = None
            if isinstance(normalized, dict):
                record = normalized
        hits = select_concepts_by_tag(record, tag_ids, match=match) if record else []
        by_speaker[speaker] = hits
        all_hits.extend(hits)
        per_speaker[speaker] = {
            "conceptCount": len(hits),
            "concepts": [_hit_to_payload(hit, id_to_label) for hit in hits],
        }
    return per_speaker, all_hits, by_speaker


def build_post_concepts_by_tag_response(
    body: Mapping[str, Any],
    *,
    project_root: Path,
    load_tags_vocab: TagsVocabLoader,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
) -> JsonResponseSpec:
    """Resolve a tag query into per-speaker concept hits without mutating state."""
    labels = _coerce_tag_labels(body)
    match = _coerce_match(body)
    speakers = _expand(body, project_root)

    vocab = list(load_tags_vocab())
    resolved = resolve_tag_labels(labels, vocab)
    _enforce_all_match_label_strictness(match, resolved)
    id_to_label = _id_to_label(vocab)
    tag_ids = list(resolved.ids_by_label.values())

    per_speaker, all_hits, _by_speaker = _resolve_per_speaker(
        speakers,
        tag_ids,
        match,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
        id_to_label=id_to_label,
    )

    payload = {
        "totalConcepts": len(all_hits),
        "perSpeaker": per_speaker,
        "unknownTags": list(resolved.unknown),
        "ambiguousTags": dict(resolved.ambiguous),
    }
    return JsonResponseSpec(status=HTTPStatus.OK, payload=payload)


def _per_concept_rerun(
    speaker: str,
    hit: ConceptHit,
    field: str,
    pad: float,
    *,
    project_root: Path,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    resolve_audio_path_for_speaker: AudioPathResolver,
    run_ipa_interval: IntervalRunner,
    run_ortho_interval: IntervalRunner,
    build_post_run_ipa_response: PerIntervalHandler,
    build_post_run_ortho_response: PerIntervalHandler,
    locks_dir: Path | None,
) -> list[dict[str, Any]]:
    """Run ORTH then IPA (or one of them) for a single concept hit.

    Each per-tier call goes through the existing per-interval handler, which
    handles speaker locking, error mapping, and the actual model invocation.
    """
    fields_to_run = []
    if field in ("ortho", "both"):
        fields_to_run.append("ortho")
    if field in ("ipa", "both"):
        fields_to_run.append("ipa")

    common = {
        "speaker": speaker,
        "concept_key": hit.conceptId,
        "start": hit.start,
        "end": hit.end,
        "pad": pad,
    }
    out: list[dict[str, Any]] = []
    for tier_field in fields_to_run:
        kwargs: dict[str, Any] = {
            "project_root": project_root,
            "normalize_speaker_id": normalize_speaker_id,
            "annotation_read_path_for_speaker": annotation_read_path_for_speaker,
            "read_json_any_file": read_json_any_file,
            "normalize_annotation_record": normalize_annotation_record,
            "resolve_audio_path_for_speaker": resolve_audio_path_for_speaker,
            "locks_dir": locks_dir,
        }
        if tier_field == "ortho":
            kwargs["run_ortho_interval"] = run_ortho_interval
            handler = build_post_run_ortho_response
        else:
            kwargs["run_ipa_interval"] = run_ipa_interval
            handler = build_post_run_ipa_response

        result_entry: dict[str, Any] = {
            "speaker": speaker,
            "conceptId": hit.conceptId,
            "field": tier_field,
        }
        try:
            response = handler(common, **kwargs)
            result_entry["status"] = "ok"
            payload = getattr(response, "payload", None)
            if isinstance(payload, dict):
                value = payload.get(tier_field)
                if isinstance(value, str):
                    result_entry["text"] = value
        except LexemeRerunHandlerError as exc:
            # Preserve the per-interval handler's HTTP status so the caller can
            # distinguish "concept not found" (404) from "speaker locked" (409)
            # from "runner died" (500) without having to parse error strings.
            result_entry["status"] = "error"
            result_entry["statusCode"] = int(exc.status)
            result_entry["error"] = exc.message
        except Exception as exc:
            result_entry["status"] = "error"
            result_entry["statusCode"] = int(HTTPStatus.INTERNAL_SERVER_ERROR)
            result_entry["error"] = str(exc)
        out.append(result_entry)
    return out


def build_post_lexemes_rerun_by_tag_response(
    body: Mapping[str, Any],
    *,
    project_root: Path,
    load_tags_vocab: TagsVocabLoader,
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    resolve_audio_path_for_speaker: AudioPathResolver,
    run_ipa_interval: IntervalRunner,
    run_ortho_interval: IntervalRunner,
    build_post_run_ipa_response: PerIntervalHandler,
    build_post_run_ortho_response: PerIntervalHandler,
    locks_dir: Path | None = None,
) -> JsonResponseSpec:
    """Resolve a tag query and run ORTH/IPA per matched concept, sequentially."""
    labels = _coerce_tag_labels(body)
    match = _coerce_match(body)
    field = _coerce_field(body)
    pad = _coerce_pad(body)
    speakers = _expand(body, project_root)

    vocab = list(load_tags_vocab())
    resolved = resolve_tag_labels(labels, vocab)
    # match='all' must 400 on unknown/ambiguous before any rerun spends GPU.
    _enforce_all_match_label_strictness(match, resolved)
    # Any ambiguous label is a 409 for rerun even under match='any', because
    # silently disambiguating would consume GPU and overwrite annotations on a
    # concept set the caller never explicitly approved. The error message lists
    # the candidate ids so the caller can resubmit by id once that contract
    # ships in a future iteration.
    if resolved.ambiguous:
        raise TagFilteredHandlerError(
            HTTPStatus.CONFLICT,
            "rerun-by-tag refuses to disambiguate; ambiguous tagLabels: {0}".format(
                _format_ambiguous(resolved.ambiguous)
            ),
        )
    id_to_label = _id_to_label(vocab)
    tag_ids = list(resolved.ids_by_label.values())

    per_speaker, all_hits, by_speaker = _resolve_per_speaker(
        speakers,
        tag_ids,
        match,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
        id_to_label=id_to_label,
    )

    results: list[dict[str, Any]] = []
    for speaker in speakers:
        for hit in by_speaker.get(speaker, []):
            results.extend(
                _per_concept_rerun(
                    speaker,
                    hit,
                    field,
                    pad,
                    project_root=project_root,
                    normalize_speaker_id=normalize_speaker_id,
                    annotation_read_path_for_speaker=annotation_read_path_for_speaker,
                    read_json_any_file=read_json_any_file,
                    normalize_annotation_record=normalize_annotation_record,
                    resolve_audio_path_for_speaker=resolve_audio_path_for_speaker,
                    run_ipa_interval=run_ipa_interval,
                    run_ortho_interval=run_ortho_interval,
                    build_post_run_ipa_response=build_post_run_ipa_response,
                    build_post_run_ortho_response=build_post_run_ortho_response,
                    locks_dir=locks_dir,
                )
            )

    payload = {
        "jobId": None,
        "resolved": {
            "totalConcepts": len(all_hits),
            "perSpeaker": per_speaker,
            "unknownTags": list(resolved.unknown),
            "ambiguousTags": dict(resolved.ambiguous),
        },
        "total": len(results),
        "results": results,
    }
    return JsonResponseSpec(status=HTTPStatus.OK, payload=payload)


__all__ = [
    "TagFilteredHandlerError",
    "build_post_concepts_by_tag_response",
    "build_post_lexemes_rerun_by_tag_response",
]
