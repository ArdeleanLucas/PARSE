"""Transactional concepts.csv mutations for PARSE."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping, Sequence

from concept_source_item import read_concepts_csv_rows, write_concepts_csv_rows

_AB_SUFFIX_RE = re.compile(r"\([AB]\)\s*$")


class ConceptDuplicateError(Exception):
    """Raised when concept duplication cannot be completed safely."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _numeric_id(value: object) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _has_ab_suffix(label: str) -> bool:
    return bool(_AB_SUFFIX_RE.search(str(label or "").strip()))


def _backup_timestamp(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%fZ")


def _backup_path(concepts_path: Path, concept_id: str, now: datetime | None = None) -> Path:
    return concepts_path.with_name("concepts.csv.bak-{0}-pre-duplicate-{1}".format(_backup_timestamp(now), concept_id))


def _max_numeric_id(rows: Sequence[Mapping[str, Any]]) -> int:
    max_id = 0
    for row in rows:
        cid = _numeric_id(row.get("id"))
        if cid:
            max_id = max(max_id, int(cid))
    return max_id


def _restore_from_backup(concepts_path: Path, backup_path: Path) -> None:
    concepts_path.write_bytes(backup_path.read_bytes())


def _has_existing_b_sibling(rows: Sequence[Mapping[str, Any]], *, target_index: int, source_item: str) -> bool:
    for index, row in enumerate(rows):
        if index == target_index:
            continue
        label = str(row.get("concept_en") or "").strip()
        if str(row.get("source_item") or "").strip() == source_item and label.endswith("(B)"):
            return True
    return False


def duplicate_concept_ab_pair(
    project_root: Path,
    concept_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, str]]:
    """Split one concepts.csv row into an `(A)` primary and appended `(B)` sibling."""

    normalized_id = _numeric_id(concept_id)
    if not normalized_id:
        raise ConceptDuplicateError(HTTPStatus.BAD_REQUEST, "conceptId must be numeric")

    concepts_path = Path(project_root) / "concepts.csv"
    try:
        rows = read_concepts_csv_rows(concepts_path)
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        raise ConceptDuplicateError(HTTPStatus.INTERNAL_SERVER_ERROR, "failed to duplicate concept") from exc

    target_index: int | None = None
    for index, row in enumerate(rows):
        if _numeric_id(row.get("id")) == normalized_id and str(row.get("concept_en") or "").strip():
            target_index = index
            break
    if target_index is None:
        raise ConceptDuplicateError(HTTPStatus.NOT_FOUND, "concept not found")

    target = dict(rows[target_index])
    label = str(target.get("concept_en") or "").strip()
    source_item = str(target.get("source_item") or "").strip()
    if _has_ab_suffix(label):
        raise ConceptDuplicateError(HTTPStatus.CONFLICT, "concept already part of an A/B pair")
    if _has_existing_b_sibling(rows, target_index=target_index, source_item=source_item):
        raise ConceptDuplicateError(HTTPStatus.CONFLICT, "concept already part of an A/B pair")

    backup_path = _backup_path(concepts_path, normalized_id, now)
    try:
        original_bytes = concepts_path.read_bytes()
        backup_path.write_bytes(original_bytes)
    except OSError as exc:
        raise ConceptDuplicateError(HTTPStatus.INTERNAL_SERVER_ERROR, "failed to duplicate concept") from exc

    primary = dict(target)
    primary["id"] = normalized_id
    primary["concept_en"] = "{0} (A)".format(label)
    sibling = {
        "id": str(_max_numeric_id(rows) + 1),
        "concept_en": "{0} (B)".format(label),
        "source_item": source_item,
        "source_survey": str(target.get("source_survey") or "").strip(),
        "custom_order": "",
    }

    updated_rows = [dict(row) for row in rows]
    updated_rows[target_index] = primary
    updated_rows.append(sibling)

    try:
        write_concepts_csv_rows(concepts_path, updated_rows, atomic=True)
    except Exception as exc:
        try:
            _restore_from_backup(concepts_path, backup_path)
        finally:
            raise ConceptDuplicateError(HTTPStatus.INTERNAL_SERVER_ERROR, "failed to duplicate concept") from exc

    return {"primary": primary, "sibling": sibling}
