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


# Tiers cleared alongside the concept interval when a recording is purged, and
# the time-match tolerance — both mirror the single-interval delete endpoint
# (server_routes/annotate._INTERVAL_DELETE_TIERS / _INTERVAL_DELETE_TOLERANCE_SEC)
# so a cascade delete removes exactly what deleting each recording by hand would.
_CASCADE_SIBLING_TIERS = ("ipa", "ortho", "ortho_words", "speaker")
_INTERVAL_MATCH_EPSILON = 0.001


def _interval_bounds(interval: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        return float(interval["start"]), float(interval["end"])
    except (KeyError, TypeError, ValueError):
        return None


def _matches_any_range(interval: object, ranges: Sequence[tuple[float, float]]) -> bool:
    if not isinstance(interval, Mapping):
        return False
    bounds = _interval_bounds(interval)
    if bounds is None:
        return False
    start, end = bounds
    return any(abs(start - rs) < _INTERVAL_MATCH_EPSILON and abs(end - re) < _INTERVAL_MATCH_EPSILON for rs, re in ranges)


def _purge_concept_intervals(payload: dict[str, Any], concept_id: str) -> int:
    """Remove every concept-tier interval tagged ``concept_id`` and the sibling
    intervals (ipa/ortho/…) at the same time range. Mutates ``payload`` in place
    and returns the number of concept intervals removed."""
    tiers = payload.get("tiers")
    if not isinstance(tiers, dict):
        return 0
    concept_tier = tiers.get("concept")
    intervals = concept_tier.get("intervals") if isinstance(concept_tier, dict) else None
    if not isinstance(intervals, list):
        return 0
    ranges: list[tuple[float, float]] = []
    kept: list[Any] = []
    for interval in intervals:
        if isinstance(interval, Mapping) and str(interval.get("concept_id") or "").strip() == concept_id:
            bounds = _interval_bounds(interval)
            if bounds is not None:
                ranges.append(bounds)
        else:
            kept.append(interval)
    removed = len(intervals) - len(kept)
    if removed <= 0:
        return 0
    concept_tier["intervals"] = kept
    for tier_name in _CASCADE_SIBLING_TIERS:
        tier = tiers.get(tier_name)
        sibling = tier.get("intervals") if isinstance(tier, dict) else None
        if not isinstance(sibling, list):
            continue
        tier["intervals"] = [iv for iv in sibling if not _matches_any_range(iv, ranges)]
    return removed


def _atomic_write_json(path: Path, payload: object) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _cascade_purge_annotations(project_root: Path, concept_id: str, *, now: datetime | None = None) -> dict[str, object]:
    """Strip ``concept_id`` recordings from every live annotation file (a backup
    is written before each rewrite). Returns the total intervals removed and the
    affected speakers."""
    annotations_dir = Path(project_root) / "annotations"
    if not annotations_dir.is_dir():
        return {"removed": 0, "speakers": []}
    removed_total = 0
    affected: set[str] = set()
    stamp = _backup_timestamp(now)
    for annotation_path in _live_annotation_files(annotations_dir):
        try:
            payload = json.loads(annotation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        removed = _purge_concept_intervals(payload, concept_id)
        if removed <= 0:
            continue
        backup = annotation_path.with_name("{0}.bak-{1}-pre-purge-{2}".format(annotation_path.name, stamp, concept_id))
        backup.write_bytes(annotation_path.read_bytes())
        _atomic_write_json(annotation_path, payload)
        removed_total += removed
        affected.add(_speaker_name_from_annotation(annotation_path, payload))
    return {"removed": removed_total, "speakers": sorted(affected)}


def delete_concept_variant(
    project_root: Path,
    concept_id: str,
    *,
    cascade: bool = False,
    now: datetime | None = None,
) -> dict[str, object]:
    """Delete one concepts.csv row with backup/rollback safety.

    By default a row that any speaker has annotated is protected (409). With
    ``cascade=True`` the blocking recordings are first purged from every live
    annotation file (each backed up) so the user can remove a garbage variant
    and its recordings in one action.
    """

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

    purge_summary: dict[str, object] = {}
    blocking_speakers = _speakers_annotating(Path(project_root), normalized_id)
    if blocking_speakers:
        if not cascade:
            raise ConceptDeleteError(
                HTTPStatus.CONFLICT,
                "canonical concept row is annotated by one or more speakers; cannot delete",
                blocking_speakers=blocking_speakers,
            )
        purge_summary = _cascade_purge_annotations(Path(project_root), normalized_id, now=now)

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

    result: dict[str, object] = {"ok": True, "deleted_id": normalized_id}
    if purge_summary:
        result["purged_intervals"] = purge_summary["removed"]
        result["purged_speakers"] = purge_summary["speakers"]
    return result
