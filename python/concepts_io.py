"""Transactional concepts.csv mutations for PARSE."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping, Sequence

from concept_source_item import read_concepts_csv_rows, write_concepts_csv_rows


class ConceptDeleteError(Exception):
    """Raised when concept deletion cannot be completed safely."""

    def __init__(self, status: HTTPStatus, message: str, *, blocking_speakers: Sequence[str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.blocking_speakers = list(blocking_speakers or [])


def _numeric_id(value: object) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _backup_timestamp(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%fZ")


def _delete_backup_path(concepts_path: Path, concept_id: str, now: datetime | None = None) -> Path:
    return concepts_path.with_name("concepts.csv.bak-{0}-pre-delete-{1}".format(_backup_timestamp(now), concept_id))


def _restore_from_backup(concepts_path: Path, backup_path: Path) -> None:
    concepts_path.write_bytes(backup_path.read_bytes())


def _speaker_name_from_annotation(path: Path, payload: Mapping[str, Any]) -> str:
    speaker = str(payload.get("speaker") or "").strip()
    if speaker:
        return speaker
    stem = path.stem
    return stem.removesuffix(".parse")


def _live_annotation_files(annotations_dir: Path) -> list[Path]:
    """Speaker annotation files to inspect, preferring the live ``.parse.json``
    over the legacy ``.json`` for the same speaker.

    The Compare pipeline (``compare_bundles._annotation_path``) and the exporters
    (``export_review_data._iter_annotation_files``) read ``{speaker}.parse.json``
    and treat the bare ``{speaker}.json`` as a stale fallback used only when no
    ``.parse.json`` exists. The delete guard must use the same view: globbing
    every ``*.json`` makes a concept the user already cleared from the live
    annotation still look "annotated" via a stale ``.json``, so the row can never
    be deleted. ``.tmp``/``.bak`` working files are skipped.
    """
    candidates = [
        path
        for path in sorted(annotations_dir.glob("*.json"))
        if not path.name.endswith(".tmp") and ".bak" not in path.name
    ]
    parse_speakers = {
        path.name[: -len(".parse.json")]
        for path in candidates
        if path.name.endswith(".parse.json")
    }
    selected: list[Path] = []
    for path in candidates:
        if path.name.endswith(".parse.json") or path.stem not in parse_speakers:
            selected.append(path)
    return selected


def _speakers_annotating(project_root: Path, concept_id: str) -> list[str]:
    """Return speaker ids whose concept tier references ``concept_id``."""

    target_id = str(concept_id)
    annotations_dir = Path(project_root) / "annotations"
    if not annotations_dir.is_dir():
        return []
    blocking: set[str] = set()
    for annotation_path in _live_annotation_files(annotations_dir):
        try:
            payload = json.loads(annotation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        tiers = payload.get("tiers")
        concept_tier = tiers.get("concept") if isinstance(tiers, Mapping) else None
        intervals = concept_tier.get("intervals") if isinstance(concept_tier, Mapping) else None
        if not isinstance(intervals, list):
            continue
        for interval in intervals:
            if isinstance(interval, Mapping) and str(interval.get("concept_id") or "").strip() == target_id:
                blocking.add(_speaker_name_from_annotation(annotation_path, payload))
                break
    return sorted(blocking)


def delete_concept_variant(
    project_root: Path,
    concept_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Delete one unannotated concepts.csv row with backup/rollback safety."""

    normalized_id = _numeric_id(concept_id)
    if not normalized_id:
        raise ConceptDeleteError(HTTPStatus.BAD_REQUEST, "conceptId must be numeric")

    concepts_path = Path(project_root) / "concepts.csv"
    try:
        rows = read_concepts_csv_rows(concepts_path)
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        raise ConceptDeleteError(HTTPStatus.INTERNAL_SERVER_ERROR, "failed to delete concept") from exc

    target_index: int | None = None
    for index, row in enumerate(rows):
        if _numeric_id(row.get("id")) == normalized_id:
            target_index = index
            break
    if target_index is None:
        raise ConceptDeleteError(HTTPStatus.NOT_FOUND, "concept not found")

    blocking_speakers = _speakers_annotating(Path(project_root), normalized_id)
    if blocking_speakers:
        raise ConceptDeleteError(
            HTTPStatus.CONFLICT,
            "canonical concept row is annotated by one or more speakers; cannot delete",
            blocking_speakers=blocking_speakers,
        )

    backup_path = _delete_backup_path(concepts_path, normalized_id, now)
    try:
        original_bytes = concepts_path.read_bytes()
        backup_path.write_bytes(original_bytes)
    except OSError as exc:
        raise ConceptDeleteError(HTTPStatus.INTERNAL_SERVER_ERROR, "failed to delete concept") from exc

    updated_rows = [dict(row) for index, row in enumerate(rows) if index != target_index]
    try:
        write_concepts_csv_rows(concepts_path, updated_rows, atomic=True)
    except OSError as exc:
        try:
            _restore_from_backup(concepts_path, backup_path)
        finally:
            raise ConceptDeleteError(HTTPStatus.INTERNAL_SERVER_ERROR, "failed to delete concept") from exc

    return {"ok": True, "deleted_id": normalized_id}
