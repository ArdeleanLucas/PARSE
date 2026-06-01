"""Relink duplicate cross-survey concepts by strict canonical gloss.

The v1 migration is intentionally simple: grouping scans the current concepts.csv
rows once, then each apply pass walks the affected JSON sidecars/files for each
accepted group. That is O(annotation_files × accepted_groups), which is fine for
Lucas's current thesis workspace but should be re-indexed before use on a
10k-concept corpus.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from concept_linking import normalize_cross_survey_gloss
from concept_source_item import read_concepts_csv_rows, row_value, write_concepts_csv_rows
from survey_overlap import (
    concept_survey_links_for_row,
    load_survey_overlap_state,
    normalize_survey_id,
    save_survey_overlap_state,
    survey_overlap_path,
)

ALGORITHM = "canonical_survey_gloss:v1-strict"

# Concept-id reference fields can appear in either snake_case (legacy/python
# payloads) or camelCase (PARSE annotation tier intervals: ``conceptId``). Both
# must be rewritten on merge or the relink silently half-applies, leaving the
# actual interval lexemes pointing at the merged-away id.
_CONCEPT_ID_FIELDS = ("concept_id", "conceptId")

# Concept-keyed sidecars rewritten on apply (in addition to annotations,
# parse-tags.json, parse-enrichments.json, concepts.csv, and survey-overlap).
_COMPARE_NOTES_FILENAME = "parseui-compare-notes-v1.json"


class ConceptRelinkError(Exception):
    """Raised when a requested relink migration is invalid or cannot be applied."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _id_sort_key(concept_id: object) -> tuple[int, int | str, str]:
    text = str(concept_id or "").strip()
    if text.isdigit():
        return (0, int(text), text)
    return (1, text, text)


def _row_id(row: Mapping[str, object]) -> str:
    return str(row.get("id") or "").strip()


def _metadata_rich(row: Mapping[str, object]) -> bool:
    return bool(row_value(row, "source_survey") and row_value(row, "source_item"))


def _source_row(row: Mapping[str, object]) -> dict[str, str]:
    return {
        "concept_id": _row_id(row),
        "concept_en": str(row.get("concept_en") or "").strip(),
        "source_survey": row_value(row, "source_survey"),
        "source_item": row_value(row, "source_item", "survey_item"),
    }


def _choose_keep_row(rows: Sequence[Mapping[str, object]]) -> tuple[str, str]:
    ordered = sorted(rows, key=lambda row: _id_sort_key(_row_id(row)))
    lowest = ordered[0]
    if not _metadata_rich(lowest):
        for row in ordered[1:]:
            if _metadata_rich(row):
                return _row_id(row), "metadata_rich_over_lowest_empty"
    return _row_id(lowest), "lowest_numeric_id"


def _build_group(canonical_gloss: str, rows: Sequence[Mapping[str, object]], state: Mapping[str, object]) -> dict[str, Any]:
    keep_id, keep_reason = _choose_keep_row(rows)
    ids = sorted((_row_id(row) for row in rows), key=_id_sort_key)
    labels = {_row_id(row): str(row.get("concept_en") or "").strip() for row in rows}
    links_by_survey: dict[str, str] = {}
    for row in sorted(rows, key=lambda item: _id_sort_key(_row_id(item))):
        links_by_survey.update(concept_survey_links_for_row(row, state))
    group: dict[str, Any] = {
        "canonical_gloss": canonical_gloss,
        "keep_concept_id": keep_id,
        "merge_concept_ids": [cid for cid in ids if cid != keep_id],
        "labels": labels,
        "links_by_survey": dict(sorted(links_by_survey.items())),
        "source_rows": [_source_row(row) for row in sorted(rows, key=lambda item: _id_sort_key(_row_id(item)))],
        "keep_reason": keep_reason,
    }
    return group


def _strip_parenthetical(text: str) -> str:
    stripped = re.sub(r"\s*\([^)]*\)\s*", " ", text)
    return " ".join(stripped.split()).strip()


def _fuzzy_candidates(rows: Sequence[Mapping[str, object]]) -> list[dict[str, str]]:
    by_canonical: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        key = normalize_cross_survey_gloss(str(row.get("concept_en") or ""))
        if key:
            by_canonical.setdefault(key, []).append(row)
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        cid = _row_id(row)
        label = str(row.get("concept_en") or "").strip()
        if not cid or not label:
            continue
        parenthetical = _strip_parenthetical(label)
        if parenthetical and parenthetical != label:
            key = normalize_cross_survey_gloss(parenthetical)
            for candidate in by_canonical.get(key, []):
                candidate_id = _row_id(candidate)
                if candidate_id != cid:
                    item = (label, str(candidate.get("concept_en") or "").strip(), "parenthetical_stripped_match")
                    if item not in seen:
                        seen.add(item)
                        out.append(
                            {
                                "incoming_label": label,
                                "candidate_label": item[1],
                                "candidate_concept_id": candidate_id,
                                "reason": "parenthetical_stripped_match",
                            }
                        )
        for token in [part.strip() for part in label.split(",") if part.strip()]:
            if token == label:
                continue
            key = normalize_cross_survey_gloss(token)
            for candidate in by_canonical.get(key, []):
                candidate_id = _row_id(candidate)
                if candidate_id != cid:
                    item = (label, str(candidate.get("concept_en") or "").strip(), "comma_token_match")
                    if item not in seen:
                        seen.add(item)
                        out.append(
                            {
                                "incoming_label": label,
                                "candidate_label": item[1],
                                "candidate_concept_id": candidate_id,
                                "reason": "comma_token_match",
                            }
                        )
    return out


def build_relink_by_gloss_plan(project_root: Path) -> dict[str, Any]:
    """Return a dry-run response for strict duplicate canonical-gloss groups."""

    root = Path(project_root)
    rows = read_concepts_csv_rows(root / "concepts.csv")
    state = load_survey_overlap_state(root)
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        cid = _row_id(row)
        label = str(row.get("concept_en") or "").strip()
        key = normalize_cross_survey_gloss(label)
        if cid and key:
            grouped.setdefault(key, []).append(row)
    groups = [
        _build_group(key, group_rows, state)
        for key, group_rows in sorted(grouped.items())
        if len({_row_id(row) for row in group_rows}) >= 2
    ]
    return {
        "ok": True,
        "applied": False,
        "algorithm": ALGORITHM,
        "groups": groups,
        "fuzzy_candidates": _fuzzy_candidates(rows),
    }


def _group_signature(group: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
    keep = str(group.get("keep_concept_id") or "").strip()
    merge_ids = tuple(sorted((str(cid or "").strip() for cid in group.get("merge_concept_ids") or ()), key=_id_sort_key))
    return keep, merge_ids


def _is_fuzzy_shape(group: Mapping[str, object]) -> bool:
    return any(key in group for key in ("incoming_label", "candidate_label", "reason"))


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_save(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _rewrite_annotation_payload(value: Any, mapping: Mapping[str, str]) -> tuple[Any, int]:
    count = 0
    if isinstance(value, list):
        new_list = []
        for item in value:
            rewritten, item_count = _rewrite_annotation_payload(item, mapping)
            count += item_count
            new_list.append(rewritten)
        return new_list, count
    if isinstance(value, dict):
        new_dict: dict[str, Any] = {}
        for key, item in value.items():
            new_key = str(key)
            for old, new in mapping.items():
                if new_key == old:
                    new_key = new
                    count += 1
                    break
                if new_key.startswith(old + "::"):
                    new_key = new + new_key[len(old) :]
                    count += 1
                    break
            if key in _CONCEPT_ID_FIELDS and str(item or "").strip() in mapping:
                new_dict[new_key] = mapping[str(item or "").strip()]
                count += 1
            else:
                rewritten, item_count = _rewrite_annotation_payload(item, mapping)
                count += item_count
                new_dict[new_key] = rewritten
        return new_dict, count
    return value, count


def _rewrite_concept_keys(value: Any, mapping: Mapping[str, str]) -> tuple[Any, int]:
    count = 0
    if isinstance(value, list):
        new_list = []
        for item in value:
            if isinstance(item, str) and item in mapping:
                new_list.append(mapping[item])
                count += 1
            else:
                rewritten, item_count = _rewrite_concept_keys(item, mapping)
                new_list.append(rewritten)
                count += item_count
        return new_list, count
    if isinstance(value, dict):
        new_dict: dict[str, Any] = {}
        for key, item in value.items():
            renamed = str(key) in mapping
            new_key = mapping.get(str(key), str(key))
            if renamed:
                count += 1
            if key in _CONCEPT_ID_FIELDS and str(item or "").strip() in mapping:
                value_out = mapping[str(item or "").strip()]
                count += 1
            else:
                value_out, item_count = _rewrite_concept_keys(item, mapping)
                count += item_count
            # Collision: a merge_id key renamed onto a key that already exists
            # (the canonical keep_id). Keep the canonical entry; drop the
            # merged-in duplicate. The keep_id's own (non-renamed) key always
            # writes, so destination wins regardless of iteration order.
            if renamed and new_key in new_dict:
                continue
            new_dict[new_key] = value_out
        return new_dict, count
    return value, count


def _rewrite_tags_payload(payload: Any, mapping: Mapping[str, str]) -> tuple[Any, int]:
    count = 0
    if not isinstance(payload, list):
        return payload, 0
    for tag in payload:
        if not isinstance(tag, dict) or not isinstance(tag.get("concepts"), list):
            continue
        seen: set[str] = set()
        concepts: list[str] = []
        for item in tag["concepts"]:
            cid = str(item or "").strip()
            new_id = mapping.get(cid, cid)
            if new_id != cid:
                count += 1
            if new_id and new_id not in seen:
                concepts.append(new_id)
                seen.add(new_id)
        tag["concepts"] = concepts
    return payload, count


def _references_any_json(path: Path, merge_ids: set[str]) -> bool:
    try:
        payload = _json_load(path)
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    text = json.dumps(payload, ensure_ascii=False)
    return any(f'"{cid}"' in text or f'"{cid}::' in text for cid in merge_ids)


def _backup_files(root: Path, files: Sequence[Path]) -> list[str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = root / "backups" / f"relink-by-gloss-{stamp}"
    backup_paths: list[str] = []
    for path in files:
        rel = path.relative_to(root)
        dest = backup_root / rel
        if not path.exists():
            if path.name != "survey-overlap.json":
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "color_coding_enabled": False,
                        "surveys": {},
                        "concept_survey_links": {},
                        "speaker_choices": {},
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            backup_paths.append(_relative(dest, root))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        backup_paths.append(_relative(dest, root))
    return backup_paths


def _files_to_backup(root: Path, merge_ids: set[str]) -> list[Path]:
    files = [root / "concepts.csv", survey_overlap_path(root)]
    annotations_dir = root / "annotations"
    if annotations_dir.is_dir():
        for path in sorted({*annotations_dir.glob("*.json"), *annotations_dir.glob("*.parse.json")}):
            if _references_any_json(path, merge_ids):
                files.append(path)
    for name in ("parse-tags.json", "parse-enrichments.json", _COMPARE_NOTES_FILENAME):
        path = root / name
        if path.exists() and _references_any_json(path, merge_ids):
            files.append(path)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def _assert_no_merged_refs(root: Path, merge_ids: set[str]) -> None:
    """Fail loudly if any merged-away concept id still has a structural reference.

    Catches incomplete rewrites (e.g. a field-name variant the rewriter missed)
    before the migration is declared successful. Raised errors propagate to the
    apply rollback. Only structural references are checked — quoted id tokens
    (``"635"``), key prefixes (``"635::``), and concepts.csv id rows — not
    free-text prose that merely mentions an old id.
    """

    if not merge_ids:
        return
    offenders: list[str] = []
    try:
        for row in read_concepts_csv_rows(root / "concepts.csv"):
            if _row_id(row) in merge_ids:
                offenders.append(f"concepts.csv:id={_row_id(row)}")
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    json_targets: list[Path] = []
    annotations_dir = root / "annotations"
    if annotations_dir.is_dir():
        json_targets.extend(sorted({*annotations_dir.glob("*.json"), *annotations_dir.glob("*.parse.json")}))
    for name in ("parse-tags.json", "parse-enrichments.json", _COMPARE_NOTES_FILENAME):
        json_targets.append(root / name)
    for path in json_targets:
        if path.exists() and _references_any_json(path, merge_ids):
            offenders.append(_relative(path, root))
    if offenders:
        raise ConceptRelinkError(500, "post_apply_dangling_refs:" + ",".join(offenders))


def _apply_one_group(root: Path, group: Mapping[str, Any], rows: list[dict[str, str]], state: dict[str, Any]) -> dict[str, Any]:
    keep_id = str(group["keep_concept_id"])
    merge_ids = {str(cid) for cid in group["merge_concept_ids"]}
    affected_ids = set(merge_ids) | {keep_id}
    mapping = {merge_id: keep_id for merge_id in merge_ids}
    rows_by_id = {_row_id(row): row for row in rows}

    links: dict[str, str] = {}
    for cid in sorted(affected_ids, key=_id_sort_key):
        row = rows_by_id.get(cid, {})
        links.update(concept_survey_links_for_row(row, state))
    links = dict(sorted(links.items()))

    state_links = {cid: dict(values) for cid, values in state.get("concept_survey_links", {}).items()}
    for merge_id in merge_ids:
        state_links.pop(merge_id, None)
    if links:
        state_links[keep_id] = links
    else:
        state_links.pop(keep_id, None)
    state["concept_survey_links"] = state_links

    speaker_choices: dict[str, dict[str, str]] = {}
    for speaker, choices in state.get("speaker_choices", {}).items():
        if not isinstance(choices, Mapping):
            continue
        new_choices = {str(cid): normalize_survey_id(sid) for cid, sid in choices.items() if str(cid) not in merge_ids}
        for merge_id in sorted(merge_ids, key=_id_sort_key):
            chosen = normalize_survey_id(choices.get(merge_id))
            if chosen and chosen in links:
                new_choices[keep_id] = chosen
        clean = {cid: sid for cid, sid in new_choices.items() if sid}
        if clean:
            speaker_choices[str(speaker)] = clean
    state["speaker_choices"] = speaker_choices

    rows[:] = [row for row in rows if _row_id(row) not in merge_ids]
    return {**group, "links_by_survey": links}


def apply_relink_by_gloss(project_root: Path, accepted_groups: Sequence[Mapping[str, object]] | None = None) -> dict[str, Any]:
    """Apply accepted strict relink groups and return the migration response."""

    root = Path(project_root)
    if accepted_groups is not None:
        if isinstance(accepted_groups, (str, bytes)) or not isinstance(accepted_groups, Sequence):
            raise ConceptRelinkError(400, "accepted_groups_must_be_group_objects")
        if any(not isinstance(group, Mapping) for group in accepted_groups):
            raise ConceptRelinkError(400, "accepted_groups_must_be_group_objects")
    for group in accepted_groups or ():
        if _is_fuzzy_shape(group):
            return {"error": "fuzzy_candidates_require_manual_relabel"}

    dry_run = build_relink_by_gloss_plan(root)
    current_by_signature = {_group_signature(group): group for group in dry_run["groups"]}
    if accepted_groups is None:
        groups_to_apply = list(dry_run["groups"])
    else:
        groups_to_apply = []
        for group in accepted_groups:
            signature = _group_signature(group)
            if signature not in current_by_signature:
                raise ConceptRelinkError(400, "accepted_group_not_current")
            groups_to_apply.append(current_by_signature[signature])

    merge_ids = {merge_id for group in groups_to_apply for merge_id in group["merge_concept_ids"]}
    backup_paths = _backup_files(root, _files_to_backup(root, merge_ids))
    if merge_ids and not backup_paths:
        raise ConceptRelinkError(500, "backup_failed")

    mutated_paths: list[Path] = []
    try:
        rows = read_concepts_csv_rows(root / "concepts.csv")
        state = load_survey_overlap_state(root)
        applied_groups = [_apply_one_group(root, group, rows, state) for group in groups_to_apply]

        annotation_rewrites: dict[str, int] = {}
        mapping = {merge_id: group["keep_concept_id"] for group in applied_groups for merge_id in group["merge_concept_ids"]}
        annotations_dir = root / "annotations"
        if annotations_dir.is_dir():
            for path in sorted({*annotations_dir.glob("*.json"), *annotations_dir.glob("*.parse.json")}):
                payload = _json_load(path)
                rewritten, count = _rewrite_annotation_payload(payload, mapping)
                if count:
                    _json_save(path, rewritten)
                    mutated_paths.append(path)
                    annotation_rewrites[_relative(path, root)] = count

        tags_path = root / "parse-tags.json"
        if tags_path.exists():
            payload = _json_load(tags_path)
            rewritten, count = _rewrite_tags_payload(payload, mapping)
            if count:
                _json_save(tags_path, rewritten)
                mutated_paths.append(tags_path)

        enrichments_path = root / "parse-enrichments.json"
        if enrichments_path.exists():
            payload = _json_load(enrichments_path)
            rewritten, count = _rewrite_concept_keys(payload, mapping)
            if count:
                _json_save(enrichments_path, rewritten)
                mutated_paths.append(enrichments_path)

        compare_notes_path = root / _COMPARE_NOTES_FILENAME
        if compare_notes_path.exists():
            payload = _json_load(compare_notes_path)
            rewritten, count = _rewrite_concept_keys(payload, mapping)
            if count:
                _json_save(compare_notes_path, rewritten)
                mutated_paths.append(compare_notes_path)

        concepts_path = root / "concepts.csv"
        write_concepts_csv_rows(concepts_path, rows, atomic=True)
        mutated_paths.append(concepts_path)
        overlap_path = survey_overlap_path(root)
        save_survey_overlap_state(root, state)
        mutated_paths.append(overlap_path)

        # Post-apply integrity gate: no merged-away id may retain a structural
        # reference. A failure here rolls back via the except clause below.
        _assert_no_merged_refs(root, merge_ids)
        return {
            "ok": True,
            "applied": True,
            "algorithm": ALGORITHM,
            "groups": applied_groups,
            "fuzzy_candidates": [],
            "backup_paths": backup_paths,
            "annotation_rewrites": annotation_rewrites,
        }
    except Exception as exc:
        try:
            for backup_path in backup_paths:
                backup_rel = Path(backup_path)
                if len(backup_rel.parts) < 3 or backup_rel.parts[0] != "backups":
                    continue
                original = root.joinpath(*backup_rel.parts[2:])
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / backup_rel, original)
        except Exception as restore_exc:
            raise ConceptRelinkError(
                500,
                f"apply_failed_restore_failed:{exc}:{restore_exc}",
            ) from restore_exc
        raise ConceptRelinkError(500, "apply_failed_restored_from_backup") from exc


__all__ = ["ALGORITHM", "ConceptRelinkError", "build_relink_by_gloss_plan", "apply_relink_by_gloss"]
