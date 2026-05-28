"""Concept-suffix pollution migration core for PARSE workspaces.

The migration canonicalizes polluted concept rows that share
``(source_survey, source_item, base_label)`` by choosing the lowest numeric
concept id as canonical, then rewrites annotation and tag references to that id.
It is intentionally isolated from server routes and allocators: importing this
module has no side effects, and writes happen only through ``run_migration`` or
its explicit helper functions.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from concept_canonical import canonicalize_label, strip_cue_prefix, variant_stem, variant_suffix
from concept_registry import concept_label_key

_BACKUP_SUFFIX = "pre-suffix-canonicalization"
_CONCEPT_ID_KEYS = {"concept_id", "conceptId"}


@dataclass
class MigrationResult:
    merge_map: dict[str, str] = field(default_factory=dict)
    rows_before: int = 0
    rows_after: int = 0
    annotations_rewritten: int = 0
    intervals_rekeyed: int = 0
    text_fields_stripped: int = 0
    concept_tags_rekeyed: int = 0
    parse_tags_rekeyed: int = 0
    backups_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    already_canonical: bool = False
    post_migration_violations: list[str] = field(default_factory=list)
    cross_survey_link_violations: list[str] = field(default_factory=list)
    text_vs_concept_en_inconsistencies: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors and not self.post_migration_violations and not self.cross_survey_link_violations

    def summary(self) -> str:
        if self.already_canonical:
            lines = [
                f"Migration {'DRY-RUN' if self.dry_run else 'COMPLETE'} — already canonical",
                f"  concepts.csv rows: {self.rows_before} → {self.rows_after}",
                "  merge_map entries: 0",
            ]
        else:
            lines = [
                f"Migration {'DRY-RUN' if self.dry_run else 'COMPLETE'}",
                f"  concepts.csv rows: {self.rows_before} → {self.rows_after}",
                f"  merge_map entries: {len(self.merge_map)}",
            ]
        if self.merge_map:
            lines.append("  merge_map:")
            for old_id, new_id in sorted(self.merge_map.items(), key=lambda item: _concept_sort_key(item[0])):
                lines.append(f"    {old_id} -> {new_id}")
        lines.extend(
            [
                f"  annotation files rewritten: {self.annotations_rewritten}",
                f"  intervals re-keyed: {self.intervals_rekeyed}",
                f"  interval text fields stripped: {self.text_fields_stripped}",
                f"  speaker concept_tags re-keyed: {self.concept_tags_rekeyed}",
                f"  parse-tags.json entries re-keyed: {self.parse_tags_rekeyed}",
                f"  backups: {len(self.backups_created)}",
            ]
        )
        if self.post_migration_violations:
            lines.append("POST-MIGRATION VIOLATIONS:")
            lines.extend(f"  - {violation}" for violation in self.post_migration_violations)
        if self.cross_survey_link_violations:
            lines.append("CROSS-SURVEY LINK VIOLATIONS:")
            lines.extend(f"  - {violation}" for violation in self.cross_survey_link_violations)
        if self.text_vs_concept_en_inconsistencies:
            lines.append("TEXT VS CONCEPT_EN INCONSISTENCIES:")
            lines.extend(f"  - {violation}" for violation in self.text_vs_concept_en_inconsistencies)
        if self.errors:
            lines.append("ERRORS:")
            lines.extend(f"  - {error}" for error in self.errors)
        return "\n".join(lines)


def build_merge_map(rows: list[dict[str, str]]) -> dict[str, str]:
    """Return non-canonical concept-id rewrites for polluted CSV rows.

    Rows are grouped by ``(source_survey, source_item, base_label)`` where
    ``base_label`` strips leaked Audition cue prefixes and render-time variant
    suffixes. Each duplicate group keeps the lowest numeric id.
    """

    groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        concept_id = _normalize_concept_id(row.get("id"))
        if not concept_id:
            continue
        source_survey = _clean(row.get("source_survey"))
        source_item = _clean(row.get("source_item"))
        base_label_key = _base_label_key(row.get("concept_en"))
        if not source_survey or not source_item or not base_label_key:
            continue
        groups.setdefault((source_survey, source_item, base_label_key), []).append(row)

    merge_map: dict[str, str] = {}
    for members in groups.values():
        valid_members = [(int(_normalize_concept_id(row.get("id"))), row) for row in members if _normalize_concept_id(row.get("id"))]
        if len(valid_members) <= 1:
            continue
        canonical_id = str(min(concept_id for concept_id, _row in valid_members))
        for concept_id, _row in valid_members:
            old_id = str(concept_id)
            if old_id != canonical_id:
                merge_map[old_id] = canonical_id
    return dict(sorted(merge_map.items(), key=lambda item: _concept_sort_key(item[0])))


def rewrite_concepts_csv(workspace: Path, merge_map: dict[str, str], dry_run: bool) -> tuple[int, int, str | None]:
    """Rewrite ``concepts.csv`` by dropping merged rows and canonicalizing labels."""

    concepts_path = Path(workspace) / "concepts.csv"
    rows, fieldnames = _read_concepts_csv(concepts_path)
    if not rows:
        return 0, 0, None

    canonical_rows = _canonical_concept_rows(rows, merge_map, fieldnames)
    rows_after = len(canonical_rows)
    backup_path: str | None = None
    if not dry_run and merge_map:
        backup_path = _backup_file(concepts_path)
        _atomic_write_text(concepts_path, _render_concepts_csv(canonical_rows, fieldnames))
    return len(rows), rows_after, backup_path


def rewrite_annotation_file(
    path: Path,
    merge_map: dict[str, str],
    concept_canonical_by_id: dict[str, str],
    dry_run: bool,
) -> dict[str, int | str | None]:
    """Rewrite one ``annotations/*.parse.json`` file.

    The function re-keys concept ids recursively for ``concept_id`` and
    ``conceptId`` fields, strips exact render-time suffix text in concept-tier
    intervals, and merges speaker-local ``concept_tags`` memberships.
    """

    record = json.loads(Path(path).read_text(encoding="utf-8"))
    stats = {"rekeyed": 0, "stripped": 0, "tags_rekeyed": 0, "backup": None}
    if not isinstance(record, dict):
        return stats

    stats["rekeyed"] = _rewrite_concept_id_fields(record, merge_map)
    stripped = _strip_concept_interval_text(record, concept_canonical_by_id)
    stats["stripped"] = stripped
    tags_rekeyed = _rewrite_concept_tags(record, merge_map)
    stats["tags_rekeyed"] = tags_rekeyed

    if not dry_run and (stats["rekeyed"] or stripped or tags_rekeyed):
        backup_path = _backup_file(Path(path))
        _atomic_write_text(Path(path), json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        stats["backup"] = backup_path
    return stats


def rewrite_parse_tags(workspace: Path, merge_map: dict[str, str], dry_run: bool) -> tuple[int, str | None]:
    """Rewrite root ``parse-tags.json`` concept references."""

    path = Path(workspace) / "parse-tags.json"
    if not path.exists():
        return 0, None
    tags = json.loads(path.read_text(encoding="utf-8"))
    rekeyed = 0
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            old_concepts = tag.get("concepts")
            if not isinstance(old_concepts, list):
                continue
            new_concepts = _dedupe_sort_concepts(_rewrite_concept_value(concept_id, merge_map) for concept_id in old_concepts)
            if new_concepts != [str(concept_id) for concept_id in old_concepts]:
                rekeyed += 1
                tag["concepts"] = new_concepts
    backup_path: str | None = None
    if not dry_run and rekeyed:
        backup_path = _backup_file(path)
        _atomic_write_text(path, json.dumps(tags, ensure_ascii=False, indent=2) + "\n")
    return rekeyed, backup_path


def run_migration(workspace: Path, *, dry_run: bool = False) -> MigrationResult:
    """Run the suffix-pollution migration on ``workspace``."""

    result = MigrationResult(dry_run=dry_run)
    workspace = Path(workspace)
    try:
        concepts_path = workspace / "concepts.csv"
        rows, fieldnames = _read_concepts_csv(concepts_path)
        result.rows_before = len(rows)
        result.merge_map = build_merge_map(rows)
        canonical_rows = _canonical_concept_rows(rows, result.merge_map, fieldnames)
        result.rows_after = len(canonical_rows)
        concept_canonical_by_id = {row["id"]: canonicalize_label(row.get("concept_en") or "") for row in canonical_rows}

        if not result.merge_map:
            result.already_canonical = _rows_already_canonical(workspace, rows)
            if result.already_canonical:
                result.post_migration_violations = verify_post_migration(workspace)
                result.cross_survey_link_violations = validate_cross_survey_links(workspace)
                result.text_vs_concept_en_inconsistencies = audit_text_vs_concept_en(workspace)
            elif not dry_run:
                result.post_migration_violations = verify_post_migration(workspace)
                result.cross_survey_link_violations = validate_cross_survey_links(workspace)
                result.text_vs_concept_en_inconsistencies = audit_text_vs_concept_en(workspace)
            return result

        _rows_before, _rows_after, concepts_backup = rewrite_concepts_csv(workspace, result.merge_map, dry_run)
        if concepts_backup:
            result.backups_created.append(concepts_backup)

        annotations_dir = workspace / "annotations"
        if annotations_dir.is_dir():
            for annotation_path in sorted(annotations_dir.glob("*.parse.json")):
                stats = rewrite_annotation_file(annotation_path, result.merge_map, concept_canonical_by_id, dry_run)
                rekeyed = int(stats["rekeyed"] or 0)
                stripped = int(stats["stripped"] or 0)
                tags_rekeyed = int(stats["tags_rekeyed"] or 0)
                if rekeyed or stripped or tags_rekeyed:
                    result.annotations_rewritten += 1
                result.intervals_rekeyed += rekeyed
                result.text_fields_stripped += stripped
                result.concept_tags_rekeyed += tags_rekeyed
                backup = stats.get("backup")
                if isinstance(backup, str):
                    result.backups_created.append(backup)

        parse_tags_rekeyed, parse_tags_backup = rewrite_parse_tags(workspace, result.merge_map, dry_run)
        result.parse_tags_rekeyed = parse_tags_rekeyed
        if parse_tags_backup:
            result.backups_created.append(parse_tags_backup)

        if not dry_run:
            result.post_migration_violations = verify_post_migration(workspace)
            result.cross_survey_link_violations = validate_cross_survey_links(workspace)
            result.text_vs_concept_en_inconsistencies = audit_text_vs_concept_en(workspace)
    except (OSError, csv.Error, json.JSONDecodeError, ValueError) as exc:
        result.errors.append(str(exc))
    return result


def is_already_canonical(workspace: Path) -> bool:
    """Return True when the workspace has no suffix-pollution work left."""

    workspace = Path(workspace)
    rows, _fieldnames = _read_concepts_csv(workspace / "concepts.csv")
    if build_merge_map(rows):
        return False
    return _rows_already_canonical(workspace, rows)


def verify_post_migration(workspace: Path) -> list[str]:
    """Return hard invariant violations after suffix-pollution migration."""

    workspace = Path(workspace)
    violations: list[str] = []
    rows, _fieldnames = _read_concepts_csv(workspace / "concepts.csv")
    valid_ids = {_normalize_concept_id(row.get("id")) for row in rows if _normalize_concept_id(row.get("id"))}

    for row in rows:
        concept_id = _normalize_concept_id(row.get("id")) or _clean(row.get("id"))
        concept_en = _clean(row.get("concept_en"))
        if variant_suffix(concept_en):
            violations.append(f"concept_en has (X) suffix: id={concept_id} concept_en={concept_en!r}")
        if strip_cue_prefix(concept_en) != concept_en:
            violations.append(f"concept_en has leading cue prefix: id={concept_id} concept_en={concept_en!r}")

    annotations_dir = workspace / "annotations"
    if annotations_dir.is_dir():
        for annotation_path in sorted(annotations_dir.glob("*.parse.json")):
            record = json.loads(annotation_path.read_text(encoding="utf-8"))
            for cid in _iter_concept_id_values(record):
                if cid and cid not in valid_ids:
                    violations.append(f"orphan concept_id in {annotation_path.name}: {cid}")
            concept_tags = record.get("concept_tags") if isinstance(record, dict) else None
            if isinstance(concept_tags, dict):
                for cid in concept_tags:
                    normalized = _normalize_concept_id(cid)
                    if normalized and normalized not in valid_ids:
                        violations.append(f"orphan concept_id in {annotation_path.name} concept_tags: {normalized}")

    tags_path = workspace / "parse-tags.json"
    if tags_path.exists():
        tags = json.loads(tags_path.read_text(encoding="utf-8"))
        if isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, dict):
                    continue
                for cid in _as_list(tag.get("concepts")):
                    normalized = _normalize_concept_id(cid)
                    if normalized and normalized not in valid_ids:
                        violations.append(f"orphan concept_id in parse-tags.json tag={tag.get('id')}: {normalized}")

    return violations


def validate_cross_survey_links(workspace: Path) -> list[str]:
    """Validate that sidecar cross-survey links target matching labels."""

    workspace = Path(workspace)
    sidecar_path = workspace / "survey-overlap.json"
    if not sidecar_path.exists():
        return []
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    links = payload.get("concept_survey_links") if isinstance(payload, dict) else None
    if not isinstance(links, dict):
        return []

    rows, _fieldnames = _read_concepts_csv(workspace / "concepts.csv")
    by_id = {_normalize_concept_id(row.get("id")): row for row in rows if _normalize_concept_id(row.get("id"))}
    by_survey_item: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        survey = _clean(row.get("source_survey")).casefold()
        item = _clean(row.get("source_item"))
        if survey and item:
            by_survey_item.setdefault((survey, item), []).append(row)

    violations: list[str] = []
    for source_id, targets in links.items():
        normalized_source = _normalize_concept_id(source_id)
        source_row = by_id.get(normalized_source)
        if not source_row:
            violations.append(f"link source id {source_id} not in concepts.csv")
            continue
        if not isinstance(targets, dict):
            violations.append(f"link source id {source_id} has non-object targets")
            continue
        source_label = concept_label_key(canonicalize_label(source_row.get("concept_en") or ""))
        for target_survey, target_item in targets.items():
            survey_key = _clean(target_survey).casefold()
            item_key = _clean(target_item)
            candidates = by_survey_item.get((survey_key, item_key), [])
            if not candidates:
                violations.append(f"link target ({target_survey}, {target_item}) has no concept")
                continue
            if not any(concept_label_key(canonicalize_label(candidate.get("concept_en") or "")) == source_label for candidate in candidates):
                violations.append(
                    f"link target ({target_survey}, {target_item}) hosts no concept matching label {source_label!r} (links {source_id})"
                )
    return violations


def audit_text_vs_concept_en(workspace: Path) -> list[str]:
    """Return informational interval text/concept_en inconsistencies."""

    workspace = Path(workspace)
    rows, _fieldnames = _read_concepts_csv(workspace / "concepts.csv")
    by_id = {
        _normalize_concept_id(row.get("id")): concept_label_key(canonicalize_label(row.get("concept_en") or ""))
        for row in rows
        if _normalize_concept_id(row.get("id"))
    }
    inconsistencies: list[str] = []
    annotations_dir = workspace / "annotations"
    if not annotations_dir.is_dir():
        return inconsistencies
    for annotation_path in sorted(annotations_dir.glob("*.parse.json")):
        record = json.loads(annotation_path.read_text(encoding="utf-8"))
        intervals = record.get("tiers", {}).get("concept", {}).get("intervals", []) if isinstance(record, dict) else []
        if not isinstance(intervals, list):
            continue
        for interval in intervals:
            if not isinstance(interval, dict):
                continue
            concept_id = _normalize_concept_id(interval.get("concept_id") or interval.get("conceptId"))
            text = concept_label_key(canonicalize_label(interval.get("text") or ""))
            expected = by_id.get(concept_id)
            if concept_id and text and expected and text != expected:
                inconsistencies.append(
                    f"{annotation_path.name} concept_id={concept_id}: text={text!r} != concept_en={expected!r}"
                )
    return inconsistencies


def _rows_already_canonical(workspace: Path, rows: list[dict[str, str]]) -> bool:
    for row in rows:
        concept_en = _clean(row.get("concept_en"))
        if variant_suffix(concept_en):
            return False
        if strip_cue_prefix(concept_en) != concept_en:
            return False
    return not verify_post_migration(workspace) and not validate_cross_survey_links(workspace)


def _iter_concept_id_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _CONCEPT_ID_KEYS:
                normalized = _normalize_concept_id(child)
                if normalized:
                    yield normalized
            else:
                yield from _iter_concept_id_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_concept_id_values(child)


def _read_concepts_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        return [dict(row) for row in reader], fieldnames


def _canonical_concept_rows(rows: list[dict[str, str]], merge_map: dict[str, str], fieldnames: list[str]) -> list[dict[str, str]]:
    grouped_noncanonical: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        concept_id = _normalize_concept_id(row.get("id"))
        canonical_id = merge_map.get(concept_id)
        if canonical_id:
            grouped_noncanonical.setdefault(canonical_id, []).append(row)

    canonical_rows: list[dict[str, str]] = []
    for row in rows:
        concept_id = _normalize_concept_id(row.get("id"))
        if not concept_id or concept_id in merge_map:
            continue
        output = _project_row(row, fieldnames)
        output["id"] = concept_id
        if concept_id in grouped_noncanonical:
            output["concept_en"] = canonicalize_label(output.get("concept_en") or "")
            for sibling in grouped_noncanonical[concept_id]:
                _fold_non_empty_values(output, sibling, fieldnames)
        canonical_rows.append(output)
    return canonical_rows


def _project_row(row: dict[str, str], fieldnames: list[str]) -> dict[str, str]:
    fields = fieldnames or ["id", "concept_en", "source_item", "source_survey", "custom_order"]
    return {name: _clean(row.get(name)) for name in fields}


def _fold_non_empty_values(target: dict[str, str], source: dict[str, str], fieldnames: list[str]) -> None:
    for name in fieldnames:
        if name in {"id", "concept_en"}:
            continue
        if not _clean(target.get(name)) and _clean(source.get(name)):
            target[name] = _clean(source.get(name))


def _render_concepts_csv(rows: list[dict[str, str]], fieldnames: list[str]) -> str:
    fields = fieldnames or ["id", "concept_en", "source_item", "source_survey", "custom_order"]
    from io import StringIO

    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name, "") for name in fields})
    return handle.getvalue()


def _strip_concept_interval_text(record: dict[str, Any], concept_canonical_by_id: dict[str, str]) -> int:
    intervals = record.get("tiers", {}).get("concept", {}).get("intervals", [])
    if not isinstance(intervals, list):
        return 0
    stripped = 0
    for interval in intervals:
        if not isinstance(interval, dict):
            continue
        concept_id = _normalize_concept_id(interval.get("concept_id") or interval.get("conceptId"))
        canonical = concept_canonical_by_id.get(concept_id, "")
        text = _clean(interval.get("text"))
        if not canonical or not text:
            continue
        stem = variant_stem(text)
        if stem != text and stem.casefold() == canonical.casefold():
            interval["text"] = stem
            stripped += 1
    return stripped


def _rewrite_concept_id_fields(value: Any, merge_map: dict[str, str]) -> int:
    rekeyed = 0
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _CONCEPT_ID_KEYS:
                new_value = _rewrite_concept_value(child, merge_map)
                if new_value != str(child):
                    value[key] = new_value
                    rekeyed += 1
            else:
                rekeyed += _rewrite_concept_id_fields(child, merge_map)
    elif isinstance(value, list):
        for child in value:
            rekeyed += _rewrite_concept_id_fields(child, merge_map)
    return rekeyed


def _rewrite_concept_tags(record: dict[str, Any], merge_map: dict[str, str]) -> int:
    concept_tags = record.get("concept_tags")
    if not isinstance(concept_tags, dict):
        return 0
    new_tags: dict[str, list[str]] = {}
    rekeyed = 0
    for old_id, tag_ids in concept_tags.items():
        new_id = merge_map.get(str(old_id), str(old_id))
        if new_id != str(old_id):
            rekeyed += 1
        merged = new_tags.setdefault(new_id, [])
        for tag_id in _as_list(tag_ids):
            tag_text = str(tag_id)
            if tag_text not in merged:
                merged.append(tag_text)
    if new_tags != concept_tags:
        record["concept_tags"] = new_tags
    return rekeyed


def _dedupe_sort_concepts(concepts: Iterable[str]) -> list[str]:
    return sorted({str(concept_id) for concept_id in concepts if str(concept_id).strip()}, key=_concept_sort_key)


def _rewrite_concept_value(value: Any, merge_map: dict[str, str]) -> str:
    return merge_map.get(str(value), str(value))


def _normalize_concept_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = int(text)
    except (TypeError, ValueError):
        return ""
    return str(number)


def _base_label_key(label: Any) -> str:
    return concept_label_key(canonicalize_label(_clean(label)))


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _concept_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(str(value)))
    except (TypeError, ValueError):
        return (1, str(value))


def _backup_file(path: Path) -> str:
    backup_path = path.with_name(f"{path.name}.bak-{_utc_now_compact()}-{_BACKUP_SUFFIX}")
    shutil.copy2(path, backup_path)
    return str(backup_path)


def _atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


__all__ = [
    "MigrationResult",
    "audit_text_vs_concept_en",
    "build_merge_map",
    "is_already_canonical",
    "rewrite_annotation_file",
    "rewrite_concepts_csv",
    "rewrite_parse_tags",
    "run_migration",
    "validate_cross_survey_links",
    "verify_post_migration",
]
