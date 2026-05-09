"""Helpers for PARSE config and CSV-import HTTP endpoints."""

from __future__ import annotations

import cgi
import io
import json
import os
import pathlib
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, BinaryIO, Callable, Dict, List

from concept_linking import build_canonical_gloss_index, normalize_cross_survey_gloss
from concept_source_item import normalize_concept_csv_row, row_value, write_concepts_csv_rows
from survey_overlap import (
    load_survey_overlap_state,
    normalize_survey_id,
    update_survey_overlap_state,
)

from .job_observability_handlers import JsonResponseSpec


@dataclass(frozen=True)
class ProjectConfigHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


ConfigLoader = Callable[[], Dict[str, Any]]
FrontendConfigBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]
ConfigWriter = Callable[[Dict[str, Any]], None]
DictMerger = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
ConceptIdNormalizer = Callable[[Any], str]
ConceptSortKey = Callable[[str], Any]



def build_get_config_response(
    *,
    load_config: ConfigLoader,
    workspace_frontend_config: FrontendConfigBuilder,
) -> JsonResponseSpec:
    config = workspace_frontend_config(load_config())
    return JsonResponseSpec(status=HTTPStatus.OK, payload={"config": config})



def build_update_config_response(
    body: Dict[str, Any],
    *,
    load_config: ConfigLoader,
    deep_merge_dicts: DictMerger,
    write_config: ConfigWriter,
) -> JsonResponseSpec:
    try:
        current = load_config()
        merged = deep_merge_dicts(current, body)
        write_config(merged)
        return JsonResponseSpec(status=HTTPStatus.OK, payload={"success": True, "config": merged})
    except ProjectConfigHandlerError:
        raise
    except Exception as exc:
        raise ProjectConfigHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc



def _parse_multipart_form(
    *,
    headers: Any,
    rfile: BinaryIO,
    upload_limit: int,
) -> cgi.FieldStorage:
    content_type = headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "Content-Type must be multipart/form-data")

    raw_length = headers.get("Content-Length", "")
    try:
        content_length = int(raw_length)
    except (ValueError, TypeError):
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "Content-Length header is required")
    if content_length > upload_limit:
        raise ProjectConfigHandlerError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload exceeds limit")

    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(content_length),
    }
    return cgi.FieldStorage(fp=rfile, headers=headers, environ=environ, keep_blank_values=True)



def _read_csv_text(form: cgi.FieldStorage) -> tuple[str, str]:
    csv_item = form["csv"] if "csv" in form else None
    if csv_item is None or not getattr(csv_item, "filename", None):
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv file is required (field name: csv)")

    try:
        csv_text = csv_item.file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv must be UTF-8: {0}".format(exc))

    return csv_text, str(csv_item.filename or "")


def _empty_survey_counter() -> Dict[str, int]:
    return {"linked_count": 0, "created_count": 0, "matched_count": 0}


def _bump_survey_counter(survey_counts: Dict[str, Dict[str, int]], survey_id: str, key: str) -> None:
    if not survey_id:
        return
    survey_counts.setdefault(survey_id, _empty_survey_counter())[key] += 1


def build_concepts_import_response(
    *,
    headers: Any,
    rfile: BinaryIO,
    project_root: pathlib.Path,
    normalize_concept_id: ConceptIdNormalizer,
    upload_limit: int,
) -> JsonResponseSpec:
    import csv as _csv

    form = _parse_multipart_form(headers=headers, rfile=rfile, upload_limit=upload_limit)
    csv_text, _csv_filename = _read_csv_text(form)

    mode_field = form.getfirst("mode", "") if "mode" in form else ""
    replace_mode = str(mode_field or "").strip().lower() == "replace"

    try:
        reader = _csv.DictReader(io.StringIO(csv_text))
        upload_rows = list(reader)
    except _csv.Error as exc:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv parse error: {0}".format(exc))

    if not upload_rows:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv is empty")

    fieldnames = [str(n or "").strip().lower() for n in (reader.fieldnames or [])]
    if "id" not in fieldnames and "concept_en" not in fieldnames:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv must have an id or concept_en column")

    concepts_path = project_root / "concepts.csv"
    existing: List[Dict[str, str]] = []
    if concepts_path.exists():
        with open(concepts_path, newline="", encoding="utf-8") as handle:
            existing = [normalize_concept_csv_row(row) for row in _csv.DictReader(handle)]

    by_id: Dict[str, int] = {}
    by_label: Dict[str, int] = {}
    for idx, row in enumerate(existing):
        rid = normalize_concept_id(row.get("id"))
        lbl = str(row.get("concept_en") or "").strip().lower()
        if rid:
            by_id[rid] = idx
        if lbl:
            by_label[lbl] = idx

    canonical_index = build_canonical_gloss_index(existing)

    if replace_mode:
        for row in existing:
            row["source_item"] = ""
            row["source_survey"] = ""
            row["custom_order"] = ""

    matched = 0
    added = 0
    linked = 0
    survey_counts: Dict[str, Dict[str, int]] = {}
    ambiguous: List[Dict[str, Any]] = []
    sidecar_links_to_add: Dict[str, Dict[str, str]] = {}

    for up in upload_rows:
        up_id = normalize_concept_id(up.get("id"))
        up_label = str(up.get("concept_en") or "").strip()
        source_item_raw = row_value(up, "source_item", "survey_item")
        source_survey_raw = row_value(up, "source_survey")
        survey_norm = normalize_survey_id(source_survey_raw)
        custom_raw = row_value(up, "custom_order")

        target_idx: int | None = None
        link_only = False
        if up_id and up_id in by_id:
            target_idx = by_id[up_id]
        elif up_label and up_label.lower() in by_label:
            target_idx = by_label[up_label.lower()]
        else:
            canonical_key = normalize_cross_survey_gloss(up_label)
            candidates = canonical_index.get(canonical_key, []) if canonical_key else []
            if len(candidates) == 1 and survey_norm and source_item_raw:
                target_cid = candidates[0]
                target_idx = by_id.get(target_cid)
                if target_idx is None:
                    for idx, row in enumerate(existing):
                        if normalize_concept_id(row.get("id")) == target_cid:
                            target_idx = idx
                            by_id[target_cid] = idx
                            break
                if target_idx is not None:
                    link_only = True
            elif len(candidates) > 1:
                ambiguous.append(
                    {
                        "label": up_label,
                        "source_survey": survey_norm,
                        "source_item": source_item_raw,
                        "candidate_concept_ids": list(candidates),
                    }
                )

        if target_idx is None:
            if not up_label:
                continue
            if not up_id:
                existing_ids = {normalize_concept_id(row.get("id")) for row in existing}
                next_id = 1
                while str(next_id) in existing_ids:
                    next_id += 1
                up_id = str(next_id)
            row = {
                "id": up_id,
                "concept_en": up_label,
                "source_item": source_item_raw,
                "source_survey": source_survey_raw,
                "custom_order": custom_raw,
            }
            existing.append(row)
            new_idx = len(existing) - 1
            by_id[up_id] = new_idx
            by_label[up_label.lower()] = new_idx
            canonical_key = normalize_cross_survey_gloss(up_label)
            if canonical_key:
                bucket = canonical_index.setdefault(canonical_key, [])
                if up_id not in bucket:
                    bucket.append(up_id)
            added += 1
            _bump_survey_counter(survey_counts, survey_norm, "created_count")
            continue

        target_row = existing[target_idx]
        target_cid = normalize_concept_id(target_row.get("id"))
        if link_only:
            sidecar_links_to_add.setdefault(target_cid, {})[survey_norm] = source_item_raw
            linked += 1
            _bump_survey_counter(survey_counts, survey_norm, "linked_count")
            continue

        legacy_survey_norm = normalize_survey_id(target_row.get("source_survey"))
        legacy_item = str(target_row.get("source_item") or "").strip()
        # Cross-survey case: an exact id/label match found a row whose legacy
        # source_survey differs from the upload's survey. Preserve the legacy
        # link in concepts.csv and add the new survey via the sidecar so we
        # don't silently overwrite the original.
        if (
            survey_norm
            and source_item_raw
            and legacy_survey_norm
            and legacy_item
            and legacy_survey_norm != survey_norm
        ):
            sidecar_links_to_add.setdefault(target_cid, {})[survey_norm] = source_item_raw
            if custom_raw:
                target_row["custom_order"] = custom_raw
            linked += 1
            _bump_survey_counter(survey_counts, survey_norm, "linked_count")
            continue

        if source_item_raw:
            target_row["source_item"] = source_item_raw
        if source_survey_raw:
            target_row["source_survey"] = source_survey_raw
        if custom_raw:
            target_row["custom_order"] = custom_raw
        matched += 1
        _bump_survey_counter(survey_counts, survey_norm, "matched_count")

    write_concepts_csv_rows(concepts_path, existing)

    if sidecar_links_to_add:
        update_survey_overlap_state(project_root, {"concept_survey_links": sidecar_links_to_add})

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "ok": True,
            "matched": matched,
            "added": added,
            "linked": linked,
            "total": len(existing),
            "mode": "replace" if replace_mode else "merge",
            "survey_counts": survey_counts,
            "ambiguous": ambiguous,
            "fuzzy_preview": [],
        },
    )



def build_tags_import_response(
    *,
    headers: Any,
    rfile: BinaryIO,
    project_root: pathlib.Path,
    normalize_concept_id: ConceptIdNormalizer,
    concept_sort_key: ConceptSortKey,
    upload_limit: int,
) -> JsonResponseSpec:
    import csv as _csv
    import re as _re

    form = _parse_multipart_form(headers=headers, rfile=rfile, upload_limit=upload_limit)
    csv_text, csv_filename = _read_csv_text(form)

    tag_name_field = form.getfirst("tagName", "") if "tagName" in form else ""
    color_field = form.getfirst("color", "") if "color" in form else ""
    tag_name = str(tag_name_field or "").strip()
    if not tag_name:
        tag_name = pathlib.Path(os.path.basename(csv_filename or "tag.csv")).stem or "Custom list"
    color = str(color_field or "").strip() or "#4461d4"

    try:
        reader = _csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
    except _csv.Error as exc:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv parse error: {0}".format(exc))
    if not rows:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv is empty")

    fieldnames = [str(n or "").strip().lower() for n in (reader.fieldnames or [])]
    if "id" not in fieldnames and "concept_en" not in fieldnames:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv must have an id or concept_en column")

    concepts_path = project_root / "concepts.csv"
    project_concepts: List[Dict[str, str]] = []
    if concepts_path.exists():
        with open(concepts_path, newline="", encoding="utf-8") as handle:
            project_concepts = list(_csv.DictReader(handle))

    by_id: Dict[str, str] = {}
    by_label: Dict[str, str] = {}
    for concept in project_concepts:
        cid = normalize_concept_id(concept.get("id"))
        lbl = str(concept.get("concept_en") or "").strip()
        if cid:
            by_id[cid] = lbl
        if lbl:
            by_label[lbl.casefold()] = cid

    matched_ids: List[str] = []
    missed_labels: List[str] = []
    seen_ids: set[str] = set()
    for row in rows:
        row_id = normalize_concept_id(row.get("id"))
        row_label = str(row.get("concept_en") or "").strip()
        cid = ""
        if row_id and row_id in by_id:
            cid = row_id
        elif row_label and row_label.casefold() in by_label:
            cid = by_label[row_label.casefold()]
        if cid:
            if cid not in seen_ids:
                matched_ids.append(cid)
                seen_ids.add(cid)
        else:
            missed_labels.append(row_label or row_id or "")

    if not matched_ids:
        raise ProjectConfigHandlerError(
            HTTPStatus.BAD_REQUEST,
            "No rows matched any existing concept by id or concept_en. Import concepts first.",
        )

    tag_id = _re.sub(r"[^a-z0-9]+", "-", tag_name.lower()).strip("-") or "tag"
    tags_path = project_root / "parse-tags.json"
    existing_tags: List[Dict[str, Any]] = []
    if tags_path.exists():
        try:
            with open(tags_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, list):
                existing_tags = raw
        except (OSError, ValueError):
            existing_tags = []

    found = False
    for tag in existing_tags:
        if isinstance(tag, dict) and str(tag.get("id")) == tag_id:
            prev = set(tag.get("concepts") or [])
            prev.update(matched_ids)
            tag["concepts"] = sorted(prev, key=concept_sort_key)
            tag["label"] = tag_name
            tag["color"] = color
            found = True
            break
    if not found:
        existing_tags.append(
            {
                "id": tag_id,
                "label": tag_name,
                "color": color,
                "concepts": sorted(set(matched_ids), key=concept_sort_key),
            }
        )

    with open(tags_path, "w", encoding="utf-8") as handle:
        json.dump(existing_tags, handle, indent=2, ensure_ascii=False)

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "ok": True,
            "tagId": tag_id,
            "tagName": tag_name,
            "color": color,
            "matchedCount": len(matched_ids),
            "missedCount": len(missed_labels),
            "missedLabels": missed_labels[:50],
            "totalTagsInFile": len(existing_tags),
        },
    )


# ---------------------------------------------------------------------------
# Manual concept survey-link endpoints (PR #319 §4b)
# ---------------------------------------------------------------------------


def _read_json_body(rfile: BinaryIO, headers: Any, *, upload_limit: int) -> Dict[str, Any]:
    raw_length = headers.get("Content-Length", "")
    try:
        content_length = int(raw_length)
    except (ValueError, TypeError):
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "Content-Length header is required")
    if content_length > upload_limit:
        raise ProjectConfigHandlerError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Body exceeds limit")
    body = rfile.read(content_length) if content_length else b""
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "invalid JSON body: {0}".format(exc))
    if not isinstance(payload, dict):
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "request body must be a JSON object")
    return payload


def _load_concept_row(project_root: pathlib.Path, concept_id: str) -> Dict[str, str] | None:
    import csv as _csv

    concepts_path = project_root / "concepts.csv"
    if not concepts_path.exists():
        return None
    target = str(concept_id or "").strip()
    if not target:
        return None
    with open(concepts_path, newline="", encoding="utf-8") as handle:
        for raw in _csv.DictReader(handle):
            row = normalize_concept_csv_row(raw)
            if str(row.get("id") or "").strip() == target:
                return row
    return None


def _build_concept_entry(row: Dict[str, str], state: Dict[str, Any]) -> Dict[str, Any]:
    from survey_overlap import concept_survey_links_for_row

    cid = str(row.get("id") or "").strip()
    label = str(row.get("concept_en") or "").strip()
    entry: Dict[str, Any] = {"id": cid, "label": label}
    source_item = row_value(row, "source_item", "survey_item")
    if source_item:
        entry["source_item"] = source_item
    source_survey = row_value(row, "source_survey")
    if source_survey:
        entry["source_survey"] = source_survey
    custom_order_raw = str(row.get("custom_order") or "").strip()
    if custom_order_raw:
        try:
            entry["custom_order"] = int(custom_order_raw)
        except ValueError:
            try:
                entry["custom_order"] = float(custom_order_raw)
            except ValueError:
                pass
    links = concept_survey_links_for_row(row, state)
    if links:
        entry["surveys"] = links
    return entry


def build_concept_survey_link_post_response(
    *,
    headers: Any,
    rfile: BinaryIO,
    project_root: pathlib.Path,
    concept_id: str,
    upload_limit: int,
) -> JsonResponseSpec:
    payload = _read_json_body(rfile, headers, upload_limit=upload_limit)
    survey_id = normalize_survey_id(payload.get("survey_id"))
    source_item = str(payload.get("source_item") or "").strip()
    if not survey_id:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "survey_id is required")
    if not source_item:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "source_item is required")

    row = _load_concept_row(project_root, concept_id)
    if row is None:
        raise ProjectConfigHandlerError(HTTPStatus.NOT_FOUND, "concept not found")

    state = update_survey_overlap_state(
        project_root,
        {"concept_survey_links": {str(row["id"]): {survey_id: source_item}}},
    )
    return JsonResponseSpec(status=HTTPStatus.OK, payload=_build_concept_entry(row, state))


def build_concept_survey_link_delete_response(
    *,
    headers: Any,
    rfile: BinaryIO,
    project_root: pathlib.Path,
    concept_id: str,
    upload_limit: int,
) -> JsonResponseSpec:
    payload = _read_json_body(rfile, headers, upload_limit=upload_limit)
    survey_id = normalize_survey_id(payload.get("survey_id"))
    source_item_raw = payload.get("source_item")
    source_item = str(source_item_raw or "").strip() if source_item_raw is not None else ""
    if not survey_id:
        raise ProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "survey_id is required")

    row = _load_concept_row(project_root, concept_id)
    if row is None:
        raise ProjectConfigHandlerError(HTTPStatus.NOT_FOUND, "concept not found")
    cid = str(row["id"]).strip()

    legacy_survey = normalize_survey_id(row_value(row, "source_survey"))
    legacy_item = row_value(row, "source_item", "survey_item")
    if legacy_survey == survey_id and legacy_item and (not source_item or source_item == legacy_item):
        raise ProjectConfigHandlerError(
            HTTPStatus.CONFLICT,
            "legacy concepts.csv link cannot be removed via this endpoint; edit and reimport the CSV",
        )

    current = load_survey_overlap_state(project_root)
    sidecar_links = dict(current["concept_survey_links"].get(cid, {}))
    stored = sidecar_links.get(survey_id)
    if stored is None:
        return JsonResponseSpec(status=HTTPStatus.OK, payload=_build_concept_entry(row, current))
    if source_item and stored != source_item:
        raise ProjectConfigHandlerError(
            HTTPStatus.CONFLICT,
            "stored source_item does not match the requested value",
        )

    sidecar_links.pop(survey_id, None)
    new_links_section = {
        other_cid: dict(other_links)
        for other_cid, other_links in current["concept_survey_links"].items()
        if other_cid != cid
    }
    if sidecar_links:
        new_links_section[cid] = sidecar_links
    current["concept_survey_links"] = new_links_section
    state = update_survey_overlap_state(
        project_root,
        {"reset_concept_survey_links": True, "concept_survey_links": new_links_section},
    )
    return JsonResponseSpec(status=HTTPStatus.OK, payload=_build_concept_entry(row, state))
