"""Helpers for PARSE lexeme-note HTTP endpoints."""

from __future__ import annotations

import cgi
import pathlib
import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, BinaryIO, Callable, Dict

from concept_source_item import row_value

from .job_observability_handlers import JsonResponseSpec


@dataclass(frozen=True)
class LexemeNoteHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


SpeakerNormalizer = Callable[[Any], str]
ConceptNormalizer = Callable[[Any], str]
AnnotationPathResolver = Callable[[str], pathlib.Path]
JsonAnyReader = Callable[[pathlib.Path], Any]
AnnotationNormalizer = Callable[[Any, str], Dict[str, Any]]
JsonReader = Callable[[pathlib.Path, Dict[str, Any]], Dict[str, Any]]
DefaultPayloadFactory = Callable[[], Dict[str, Any]]
JsonWriter = Callable[[pathlib.Path, Dict[str, Any]], None]
UtcNowProvider = Callable[[], str]



def _notes_block(payload: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    notes = payload.get("lexeme_notes")
    if not isinstance(notes, dict):
        notes = {}
        payload["lexeme_notes"] = notes
    return notes



def _speaker_notes_block(notes: Dict[str, Any], speaker: str) -> Dict[str, Dict[str, Any]]:
    speaker_block = notes.get(speaker)
    if not isinstance(speaker_block, dict):
        speaker_block = {}
        notes[speaker] = speaker_block
    return speaker_block



def build_post_lexeme_note_response(
    body: Dict[str, Any],
    *,
    normalize_speaker_id: SpeakerNormalizer,
    normalize_concept_id: ConceptNormalizer,
    read_json_file: JsonReader,
    default_enrichments_payload: DefaultPayloadFactory,
    write_json_file: JsonWriter,
    enrichments_path: pathlib.Path,
    utc_now_iso: UtcNowProvider,
) -> JsonResponseSpec:
    speaker_raw = str(body.get("speaker") or "").strip()
    concept_id = normalize_concept_id(body.get("concept_id"))
    if not speaker_raw or not concept_id:
        raise LexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, "speaker and concept_id are required")

    try:
        speaker = normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise LexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    payload = read_json_file(enrichments_path, default_enrichments_payload())
    notes = _notes_block(payload)
    speaker_block = _speaker_notes_block(notes, speaker)

    if body.get("delete") is True:
        speaker_block.pop(concept_id, None)
        if not speaker_block:
            notes.pop(speaker, None)
    else:
        entry = speaker_block.get(concept_id)
        if not isinstance(entry, dict):
            entry = {}
        if "user_note" in body:
            entry["user_note"] = str(body.get("user_note") or "")
        if "import_note" in body:
            entry["import_note"] = str(body.get("import_note") or "")
        entry["updated_at"] = utc_now_iso()
        speaker_block[concept_id] = entry

    write_json_file(enrichments_path, payload)
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "success": True,
            "lexeme_notes": payload.get("lexeme_notes") or {},
        },
    )



def _parse_multipart_form(*, headers: Any, rfile: BinaryIO, upload_limit: int) -> cgi.FieldStorage:
    content_type = headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise LexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, "Content-Type must be multipart/form-data")

    raw_length = headers.get("Content-Length", "")
    try:
        content_length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise LexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, "Content-Length header is required") from exc
    if content_length > upload_limit:
        raise LexemeNoteHandlerError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload exceeds limit")

    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(content_length),
    }
    return cgi.FieldStorage(fp=rfile, headers=headers, environ=environ, keep_blank_values=True)



def _load_concept_metadata(project_root: pathlib.Path, normalize_concept_id: ConceptNormalizer) -> tuple[Dict[str, str], Dict[str, str]]:
    concept_labels: Dict[str, str] = {}
    survey_to_id: Dict[str, str] = {}
    try:
        import csv as _csv

        concepts_path = project_root / "concepts.csv"
        if concepts_path.exists():
            with open(concepts_path, newline="", encoding="utf-8") as handle:
                for row in _csv.DictReader(handle):
                    concept_id = normalize_concept_id(row.get("id"))
                    label = str(row.get("concept_en") or "").strip()
                    survey = row_value(row, "source_item", "survey_item")
                    if concept_id and label:
                        concept_labels[concept_id] = label
                    if concept_id and survey:
                        match = re.match(r"^(?:[A-Za-z]+_)?([0-9]+(?:\.[0-9]+)?)", survey)
                        key = match.group(1) if match else survey
                        survey_to_id.setdefault(key, concept_id)
                        concept_labels.setdefault(key, label)
    except Exception:
        return {}, {}

    return concept_labels, survey_to_id



def _concept_intervals(annotation: Dict[str, Any], normalize_concept_id: ConceptNormalizer) -> list[Dict[str, Any]]:
    tiers = annotation.get("tiers") or {}
    concept_tier = tiers.get("concept") if isinstance(tiers, dict) else None
    intervals: list[Dict[str, Any]] = []
    if not isinstance(concept_tier, dict):
        return intervals

    for interval in concept_tier.get("intervals") or []:
        if not isinstance(interval, dict):
            continue
        concept_id = normalize_concept_id(interval.get("text"))
        if not concept_id:
            continue
        try:
            start = float(interval.get("start") or 0.0)
            end = float(interval.get("end") or 0.0)
        except (TypeError, ValueError):
            continue
        intervals.append({"concept_id": concept_id, "start": start, "end": end})
    return intervals



def build_post_lexeme_notes_import_response(
    *,
    headers: Any,
    rfile: BinaryIO,
    project_root: pathlib.Path,
    upload_limit: int,
    normalize_speaker_id: SpeakerNormalizer,
    normalize_concept_id: ConceptNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    read_json_file: JsonReader,
    default_enrichments_payload: DefaultPayloadFactory,
    write_json_file: JsonWriter,
    enrichments_path: pathlib.Path,
    utc_now_iso: UtcNowProvider,
) -> JsonResponseSpec:
    from lexeme_notes import match_rows_to_lexemes, parse_audition_csv

    form = _parse_multipart_form(headers=headers, rfile=rfile, upload_limit=upload_limit)

    speaker_field = form.getfirst("speaker_id", "") if "speaker_id" in form else ""
    if isinstance(speaker_field, bytes):
        speaker_field = speaker_field.decode("utf-8", errors="replace")
    try:
        speaker = normalize_speaker_id(str(speaker_field or "").strip())
    except ValueError as exc:
        raise LexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

    csv_item = form["csv"] if "csv" in form else None
    if csv_item is None or not getattr(csv_item, "filename", None):
        raise LexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, "csv file is required (field name: csv)")
    try:
        csv_text = csv_item.file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, "csv must be UTF-8: {0}".format(exc)) from exc

    rows = parse_audition_csv(csv_text)
    if not rows:
        return JsonResponseSpec(
            status=HTTPStatus.OK,
            payload={"success": True, "imported": 0, "matched": 0, "total_rows": 0},
        )

    annotation_path = annotation_read_path_for_speaker(speaker)
    annotation_payload = read_json_any_file(annotation_path)
    normalized_annotation = normalize_annotation_record(annotation_payload, speaker)
    intervals = _concept_intervals(normalized_annotation, normalize_concept_id)
    concept_labels, survey_to_id = _load_concept_metadata(project_root, normalize_concept_id)

    matches = match_rows_to_lexemes(rows, intervals, concept_labels=concept_labels)
    label_to_id = {label.lower(): concept_id for concept_id, label in concept_labels.items() if concept_id.isdigit()}
    for row, match in zip(rows, matches):
        csv_id = normalize_concept_id(row.concept_id)
        if csv_id in survey_to_id:
            match["concept_id"] = survey_to_id[csv_id]
            continue
        current = normalize_concept_id(match.get("concept_id"))
        if current.isdigit():
            continue
        if current.lower() in label_to_id:
            match["concept_id"] = label_to_id[current.lower()]

    payload = read_json_file(enrichments_path, default_enrichments_payload())
    notes = _notes_block(payload)
    speaker_block = _speaker_notes_block(notes, speaker)

    imported = 0
    for match in matches:
        note_text = str(match.get("note") or "").strip()
        if not note_text:
            continue
        concept_id = normalize_concept_id(match.get("concept_id"))
        if not concept_id:
            continue
        entry = speaker_block.get(concept_id)
        if not isinstance(entry, dict):
            entry = {}
        entry["import_note"] = note_text
        entry["import_raw"] = str(match.get("raw_name") or "")
        entry["updated_at"] = utc_now_iso()
        speaker_block[concept_id] = entry
        imported += 1

    write_json_file(enrichments_path, payload)
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "success": True,
            "speaker": speaker,
            "total_rows": len(rows),
            "imported": imported,
            "matched": sum(1 for match in matches if match.get("was_matched")),
            "lexeme_notes": payload.get("lexeme_notes") or {},
        },
    )
