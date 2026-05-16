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

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
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

from app.services.lexeme_rerun_loop import per_concept_rerun as _shared_per_concept_rerun

from .job_observability_handlers import JsonResponseSpec
from .lexeme_rerun_handlers import LexemeRerunHandlerError

logger = logging.getLogger(__name__)


# Mirror python/server.py:156 ANNOTATION_MATCH_EPSILON without importing server into this pure handler.
_ANNOTATION_MATCH_EPSILON = 0.0005
_PAD_VALUES = (0.0, 0.2, 0.5)
_VALID_FIELDS = ("ipa", "ortho", "both")


@dataclass(frozen=True)
class TagFilteredHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class LexemesRerunByTagPlan:
    labels: list[str]
    match: str
    field: str
    pad: float
    speakers: list[str]
    resolved: ResolvedTags
    per_speaker: dict[str, dict[str, Any]]
    all_hits: list[ConceptHit]
    by_speaker: dict[str, list[ConceptHit]]


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
IntervalRunner = Callable[..., Any]
TagsVocabLoader = Callable[[], Sequence[Mapping[str, Any]]]
PerIntervalHandler = Callable[..., Any]
JobCreator = Callable[[str, dict[str, Any]], str]
ComputeLauncher = Callable[[str, str, dict[str, Any]], None]
ProgressCallback = Callable[[int, int, str, ConceptHit, str], None]
AnnotationWriter = Callable[[str, Path, dict[str, Any]], None]
AnnotationMetadataToucher = Callable[[dict[str, Any], bool], None]
OrthoWordsAligner = Callable[[Path, list[dict[str, Any]]], list[dict[str, Any]]]
LexemeWordPicker = Callable[[float, float, Sequence[Mapping[str, Any]]], Mapping[str, Any] | None]


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

    Delegates to ``app.services.lexeme_rerun_loop.per_concept_rerun`` so
    Lane A and the chat-tool MCP wrapper share one source of truth for
    the per-tier dispatch + statusCode propagation.
    """
    return _shared_per_concept_rerun(
        speaker,
        hit,
        field,
        pad,
        project_root=project_root,
        locks_dir=locks_dir,
        normalize_speaker_id=normalize_speaker_id,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
        resolve_audio_path_for_speaker=resolve_audio_path_for_speaker,
        run_ortho_interval=run_ortho_interval,
        run_ipa_interval=run_ipa_interval,
        build_post_run_ortho_response=build_post_run_ortho_response,
        build_post_run_ipa_response=build_post_run_ipa_response,
        lexeme_rerun_handler_error=LexemeRerunHandlerError,
    )


def build_lexemes_rerun_by_tag_plan(
    body: Mapping[str, Any],
    *,
    project_root: Path,
    load_tags_vocab: TagsVocabLoader,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
) -> LexemesRerunByTagPlan:
    """Validate and resolve a rerun-by-tag request without spending GPU."""
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
    return LexemesRerunByTagPlan(
        labels=labels,
        match=match,
        field=field,
        pad=pad,
        speakers=speakers,
        resolved=resolved,
        per_speaker=per_speaker,
        all_hits=all_hits,
        by_speaker=by_speaker,
    )


def _lexemes_rerun_by_tag_result_payload(
    plan: LexemesRerunByTagPlan,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {
        "ok": sum(1 for row in results if row.get("status") == "ok"),
        "skipped": sum(1 for row in results if row.get("status") in {"skip", "skipped"}),
        "error": sum(1 for row in results if row.get("status") == "error"),
    }
    return {
        "resolved": {
            "totalConcepts": len(plan.all_hits),
            "perSpeaker": plan.per_speaker,
            "unknownTags": list(plan.resolved.unknown),
            "ambiguousTags": dict(plan.resolved.ambiguous),
        },
        "total": len(results),
        "results": results,
        "summary": summary,
        "run_mode": "tagged-only",
    }


def _interval_overlaps_any_window(interval: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]) -> bool:
    try:
        start_sec = float(interval.get("start", 0.0) or 0.0)
        end_sec = float(interval.get("end", start_sec) or start_sec)
    except (TypeError, ValueError):
        return False
    for window in windows:
        try:
            win_start = float(window.get("start", 0.0) or 0.0)
            win_end = float(window.get("end", win_start) or win_start)
        except (TypeError, ValueError):
            continue
        if start_sec < win_end and end_sec > win_start:
            return True
    return False


def _merge_intervals_for_windows(
    existing: Sequence[Mapping[str, Any]],
    replacements: Sequence[Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    kept = [
        dict(row)
        for row in existing
        if isinstance(row, Mapping) and not _interval_overlaps_any_window(row, windows)
    ]
    combined = kept + [dict(row) for row in replacements if isinstance(row, Mapping)]
    combined.sort(
        key=lambda iv: (
            float(iv.get("start", 0.0) or 0.0),
            float(iv.get("end", 0.0) or 0.0),
        )
    )
    return combined


def _persist_speaker_rerun_writes(
    speaker: str,
    hits: Sequence[ConceptHit],
    speaker_results: Sequence[Mapping[str, Any]],
    *,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    annotation_touch_metadata: AnnotationMetadataToucher,
    annotation_writer: AnnotationWriter,
    resolve_audio_path_for_speaker: AudioPathResolver,
    align_ortho_words: OrthoWordsAligner | None = None,
    pick_lexeme_word: LexemeWordPicker | None = None,
) -> None:
    """Merge ok rerun rows into ``tiers.ortho`` / ``tiers.ipa`` and write to disk.

    Regression fix for the tagged-only batch rerun (2026-05-10): the loop
    previously returned text that no caller persisted, so disk-side
    annotation files never reflected ``ok`` rows.
    """
    by_window = {
        (round(float(hit.start), 6), round(float(hit.end), 6)): hit for hit in hits
    }
    if not by_window:
        return

    rows_by_field: dict[str, list[dict[str, Any]]] = {"ortho": [], "ipa": []}
    for row in speaker_results:
        if row.get("status") != "ok":
            continue
        field = row.get("field")
        if field not in rows_by_field:
            continue
        text = row.get("text")
        if not isinstance(text, str):
            continue
        concept_id = row.get("conceptId")
        hit = next((h for h in hits if h.conceptId == concept_id), None)
        if hit is None:
            continue
        rows_by_field[field].append(
            {"start": float(hit.start), "end": float(hit.end), "text": text}
        )

    if not any(rows_by_field.values()):
        return

    annotation_path = annotation_read_path_for_speaker(speaker)
    if not annotation_path.is_file():
        return
    payload = read_json_any_file(annotation_path)
    try:
        record = normalize_annotation_record(payload, speaker)
    except Exception:  # pragma: no cover - prod normalizer logs internally
        return
    if not isinstance(record, dict):
        return

    tiers = record.get("tiers") if isinstance(record.get("tiers"), dict) else {}
    record["tiers"] = tiers
    changed = False
    for field, new_rows in rows_by_field.items():
        if not new_rows:
            continue
        field_windows = [
            {"start": float(row["start"]), "end": float(row["end"])}
            for row in new_rows
        ]
        tier = tiers.get(field) if isinstance(tiers.get(field), dict) else None
        if tier is None:
            tier = {"type": "interval", "display_order": 2 if field == "ortho" else 1, "intervals": []}
        existing = [iv for iv in tier.get("intervals") or [] if isinstance(iv, dict)]
        tier["intervals"] = _merge_intervals_for_windows(existing, new_rows, field_windows)
        tiers[field] = tier
        changed = True

    ortho_rows = rows_by_field["ortho"]
    if align_ortho_words is not None and ortho_rows:
        ortho_windows = [
            {"start": float(row["start"]), "end": float(row["end"])}
            for row in ortho_rows
        ]
        try:
            audio_path = resolve_audio_path_for_speaker(speaker)
            aligned_words = align_ortho_words(audio_path, [dict(row) for row in ortho_rows])
        except Exception:
            logger.exception("tagged-only rerun: failed to rebuild ortho_words for speaker %s", speaker)
        else:
            word_tier = tiers.get("ortho_words") if isinstance(tiers.get("ortho_words"), dict) else None
            if word_tier is None:
                word_tier = {"type": "interval", "display_order": 4, "intervals": []}
            existing_words = [iv for iv in word_tier.get("intervals") or [] if isinstance(iv, dict)]
            word_tier["intervals"] = _merge_intervals_for_windows(existing_words, aligned_words, ortho_windows)
            tiers["ortho_words"] = word_tier
            if pick_lexeme_word is not None:
                ortho_tier = tiers.get("ortho") if isinstance(tiers.get("ortho"), dict) else None
                ortho_intervals = ortho_tier.get("intervals") if isinstance(ortho_tier, dict) else []
                for row in ortho_rows:
                    picked = pick_lexeme_word(float(row["start"]), float(row["end"]), aligned_words)
                    picked_text = picked.get("text") if isinstance(picked, Mapping) else None
                    if not isinstance(picked_text, str) or not picked_text.strip():
                        continue
                    for interval in ortho_intervals or []:
                        if not isinstance(interval, Mapping):
                            continue
                        try:
                            same_start = abs(float(interval.get("start", 0.0) or 0.0) - float(row["start"])) <= _ANNOTATION_MATCH_EPSILON
                            same_end = abs(float(interval.get("end", 0.0) or 0.0) - float(row["end"])) <= _ANNOTATION_MATCH_EPSILON
                        except (TypeError, ValueError):
                            continue
                        if same_start and same_end:
                            interval["text"] = picked_text.strip()
                            break
            changed = True

    if not changed:
        return

    annotation_touch_metadata(record, True)
    annotation_writer(speaker, annotation_path, record)


def _default_annotation_touch_metadata(record: dict[str, Any], preserve_created: bool) -> None:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    record["metadata"] = metadata
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not preserve_created or not str(metadata.get("created") or "").strip():
        metadata["created"] = now_iso
    metadata["modified"] = now_iso


def _default_annotation_writer(_speaker: str, path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_lexemes_rerun_by_tag_loop(
    plan: LexemesRerunByTagPlan,
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
    locks_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
    annotation_writer: AnnotationWriter | None = None,
    annotation_touch_metadata: AnnotationMetadataToucher | None = None,
    align_ortho_words: OrthoWordsAligner | None = None,
    pick_lexeme_word: LexemeWordPicker | None = None,
) -> dict[str, Any]:
    writer = annotation_writer or _default_annotation_writer
    touch_metadata = annotation_touch_metadata or _default_annotation_touch_metadata
    results: list[dict[str, Any]] = []
    total_concepts = sum(len(plan.by_speaker.get(speaker, [])) for speaker in plan.speakers)
    completed = 0
    for speaker in plan.speakers:
        speaker_hits = plan.by_speaker.get(speaker, [])
        speaker_start_idx = len(results)
        for hit in speaker_hits:
            results.extend(
                _per_concept_rerun(
                    speaker,
                    hit,
                    plan.field,
                    plan.pad,
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
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total_concepts, speaker, hit, plan.field)
        speaker_results = results[speaker_start_idx:]
        if speaker_hits and speaker_results:
            try:
                _persist_speaker_rerun_writes(
                    speaker,
                    speaker_hits,
                    speaker_results,
                    annotation_read_path_for_speaker=annotation_read_path_for_speaker,
                    read_json_any_file=read_json_any_file,
                    normalize_annotation_record=normalize_annotation_record,
                    annotation_touch_metadata=touch_metadata,
                    annotation_writer=writer,
                    resolve_audio_path_for_speaker=resolve_audio_path_for_speaker,
                    align_ortho_words=align_ortho_words,
                    pick_lexeme_word=pick_lexeme_word,
                )
            except Exception:  # pragma: no cover - persistence must not abort the loop
                logger.exception(
                    "tagged-only rerun: failed to persist annotation writes for speaker %s",
                    speaker,
                )
    return _lexemes_rerun_by_tag_result_payload(plan, results)


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
    create_job: JobCreator | None = None,
    launch_compute_runner: ComputeLauncher | None = None,
    job_conflict_error_cls: type[Exception] | tuple[type[Exception], ...] | None = None,
    annotation_writer: AnnotationWriter | None = None,
    annotation_touch_metadata: AnnotationMetadataToucher | None = None,
    align_ortho_words: OrthoWordsAligner | None = None,
    pick_lexeme_word: LexemeWordPicker | None = None,
) -> JsonResponseSpec:
    """Validate a tag rerun and start a tracked compute job by default.

    Backwards compatibility: callers can send ``{"async": false}`` to keep
    the old blocking 200 response temporarily while integrations migrate.
    """
    plan = build_lexemes_rerun_by_tag_plan(
        body,
        project_root=project_root,
        load_tags_vocab=load_tags_vocab,
        annotation_read_path_for_speaker=annotation_read_path_for_speaker,
        read_json_any_file=read_json_any_file,
        normalize_annotation_record=normalize_annotation_record,
    )

    if body.get("async") is False:
        payload = run_lexemes_rerun_by_tag_loop(
            plan,
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
            annotation_writer=annotation_writer,
            annotation_touch_metadata=annotation_touch_metadata,
            align_ortho_words=align_ortho_words,
            pick_lexeme_word=pick_lexeme_word,
        )
        # Deprecated compatibility shape: legacy clients used ``jobId: null``
        # to distinguish the old synchronous endpoint from compute jobs.
        return JsonResponseSpec(status=HTTPStatus.OK, payload={"jobId": None, **payload})

    if create_job is None or launch_compute_runner is None:
        raise TagFilteredHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "async rerun job dependencies are not configured")
    metadata = {
        "computeType": "lexemes_rerun_by_tag",
        "speakers": list(plan.speakers),
        "tagLabels": list(plan.labels),
        "match": plan.match,
        "field": plan.field,
        "totalConcepts": len(plan.all_hits),
    }
    if len(plan.speakers) == 1:
        metadata["speaker"] = plan.speakers[0]
    try:
        job_id = create_job("compute:lexemes_rerun_by_tag", metadata)
    except Exception as exc:
        if job_conflict_error_cls is not None and isinstance(exc, job_conflict_error_cls):
            raise TagFilteredHandlerError(HTTPStatus.CONFLICT, str(exc)) from exc
        raise
    launch_compute_runner(job_id, "lexemes_rerun_by_tag", dict(body))
    return JsonResponseSpec(status=HTTPStatus.ACCEPTED, payload={"jobId": job_id})


__all__ = [
    "LexemesRerunByTagPlan",
    "OrthoWordsAligner",
    "TagFilteredHandlerError",
    "build_lexemes_rerun_by_tag_plan",
    "build_post_concepts_by_tag_response",
    "build_post_lexemes_rerun_by_tag_response",
    "run_lexemes_rerun_by_tag_loop",
]
