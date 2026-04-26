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
            existing = list(_csv.DictReader(handle))

    by_id: Dict[str, int] = {}
    by_label: Dict[str, int] = {}
    for idx, row in enumerate(existing):
        rid = normalize_concept_id(row.get("id"))
        lbl = str(row.get("concept_en") or "").strip().lower()
        if rid:
            by_id[rid] = idx
        if lbl:
            by_label[lbl] = idx

    if replace_mode:
        for row in existing:
            row["survey_item"] = ""
            row["custom_order"] = ""

    matched = 0
    added = 0
    for up in upload_rows:
        up_id = normalize_concept_id(up.get("id"))
        up_label = str(up.get("concept_en") or "").strip()
        target_idx = None
        if up_id and up_id in by_id:
            target_idx = by_id[up_id]
        elif up_label and up_label.lower() in by_label:
            target_idx = by_label[up_label.lower()]

        survey_raw = str(up.get("survey_item") or "").strip() if "survey_item" in up else ""
        custom_raw = str(up.get("custom_order") or "").strip() if "custom_order" in up else ""

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
                "survey_item": survey_raw,
                "custom_order": custom_raw,
            }
            existing.append(row)
            by_id[up_id] = len(existing) - 1
            by_label[up_label.lower()] = len(existing) - 1
            added += 1
        else:
            row = existing[target_idx]
            if survey_raw:
                row["survey_item"] = survey_raw
            if custom_raw:
                row["custom_order"] = custom_raw
            matched += 1

    fieldnames_out = ["id", "concept_en", "survey_item", "custom_order"]
    concepts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(concepts_path, "w", newline="", encoding="utf-8") as handle:
        writer = _csv.DictWriter(handle, fieldnames=fieldnames_out)
        writer.writeheader()
        for row in existing:
            writer.writerow({key: row.get(key, "") or "" for key in fieldnames_out})

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "ok": True,
            "matched": matched,
            "added": added,
            "total": len(existing),
            "mode": "replace" if replace_mode else "merge",
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
