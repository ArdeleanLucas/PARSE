"""Advisory integrity checks for cross-survey links in survey-overlap.json.

The checks are intentionally non-blocking. They catch links whose target survey
item has no owning concepts.csv row, links that land on a different-gloss row, and
links where the owning target row does not link/own back to the source row.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Mapping

from concept_identity import same_stem_unlinked_clusters
from concept_source_item import read_concepts_csv_rows, row_value
from survey_overlap import (
    concept_survey_links_for_row,
    load_survey_overlap_state,
    normalize_survey_id,
    normalize_survey_overlap_state,
    save_survey_overlap_state,
)

def _id_sort_key(row_id: object) -> tuple[int, object]:
    text = str(row_id or "").strip()
    return (0, int(text)) if text.isdigit() else (1, text)


def _row_id(row: Mapping[str, object]) -> str:
    return str(row_value(row, "id") or "").strip()


def _row_gloss(row: Mapping[str, object]) -> str:
    return str(row_value(row, "concept_en", "label") or "").strip()


def _legacy_pair(row: Mapping[str, object]) -> tuple[str, str] | None:
    survey = normalize_survey_id(row_value(row, "source_survey"))
    item = row_value(row, "source_item", "survey_item")
    if not survey or not item:
        return None
    return survey, item


def _owner_index(rows: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], list[Mapping[str, object]]]:
    owners: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        pair = _legacy_pair(row)
        if pair is not None:
            owners.setdefault(pair, []).append(row)
    for owner_rows in owners.values():
        owner_rows.sort(key=lambda row: _id_sort_key(_row_id(row)))
    return owners


def _source_index(rows: Sequence[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    return {_row_id(row): row for row in rows if _row_id(row)}


def _link_payload(survey: str, item: str) -> dict[str, str]:
    return {"survey": survey, "item": item}


def _filtered_links(state: Mapping[str, object], only_links: Mapping[str, Mapping[str, str]] | None) -> dict[str, dict[str, str]]:
    root = state.get("concept_survey_links") if isinstance(state, Mapping) else None
    all_links = root if isinstance(root, Mapping) else {}
    if only_links is None:
        return normalize_survey_overlap_state({"concept_survey_links": all_links})["concept_survey_links"]
    clean_filter = normalize_survey_overlap_state({"concept_survey_links": only_links})["concept_survey_links"]
    out: dict[str, dict[str, str]] = {}
    for cid, links in clean_filter.items():
        existing = all_links.get(cid) if isinstance(all_links, Mapping) else None
        if not isinstance(existing, Mapping):
            continue
        clean_existing = normalize_survey_overlap_state({"concept_survey_links": {cid: existing}})["concept_survey_links"].get(cid, {})
        selected = {survey: item for survey, item in clean_filter[cid].items() if clean_existing.get(survey) == item}
        if selected:
            out[cid] = selected
    return out


def audit_survey_overlap_links(
    project_root: Path,
    *,
    state: Mapping[str, object] | None = None,
    only_links: Mapping[str, Mapping[str, str]] | None = None,
    include_same_stem: bool = True,
) -> dict[str, Any]:
    """Return advisory integrity findings for global concept_survey_links.

    ``only_links`` limits classification to a just-written subset while still
    resolving those links against the full merged state. The CLI omits it to scan
    every existing sidecar link.
    """

    project_root = Path(project_root)
    rows = read_concepts_csv_rows(project_root / "concepts.csv")
    source_by_id = _source_index(rows)
    owners = _owner_index(rows)
    effective_state = state if state is not None else load_survey_overlap_state(project_root)
    links_by_concept = _filtered_links(effective_state, only_links)

    from compare_bundles import _gloss_mismatch  # reuse the conservative MC-458-B heuristic without a module cycle

    report: dict[str, Any] = {
        "gloss_mismatch": [],
        "dangling": [],
        "non_reciprocal": [],
        "same_stem_unlinked": [],
    }
    ok: list[dict[str, Any]] = []

    for source_id in sorted(links_by_concept, key=_id_sort_key):
        source_row = source_by_id.get(source_id)
        if source_row is None:
            continue
        source_gloss = _row_gloss(source_row)
        source_pair = _legacy_pair(source_row)
        for survey, item in sorted(links_by_concept[source_id].items()):
            link = _link_payload(survey, item)
            target_rows = owners.get((survey, item), [])
            if not target_rows:
                report["dangling"].append({"source_id": source_id, "link": link})
                continue

            link_ok = True
            for target_row in target_rows:
                target_id = _row_id(target_row)
                if target_id == source_id:
                    continue
                target_gloss = _row_gloss(target_row)
                if _gloss_mismatch(source_gloss, target_gloss):
                    link_ok = False
                    report["gloss_mismatch"].append(
                        {
                            "source_id": source_id,
                            "source_gloss": source_gloss,
                            "link": link,
                            "target_id": target_id,
                            "target_gloss": target_gloss,
                        }
                    )

                if source_pair is not None:
                    target_links = concept_survey_links_for_row(target_row, effective_state)
                    if target_links.get(source_pair[0]) != source_pair[1]:
                        link_ok = False
                        report["non_reciprocal"].append(
                            {
                                "source_id": source_id,
                                "source_gloss": source_gloss,
                                "link": link,
                                "target_id": target_id,
                                "target_gloss": target_gloss,
                                "expected_backlink": _link_payload(source_pair[0], source_pair[1]),
                            }
                        )
            if link_ok:
                ok.append({"source_id": source_id, "link": link})

    if ok:
        report["ok"] = ok
    if include_same_stem:
        report["same_stem_unlinked"] = same_stem_unlinked_clusters(project_root)
    return report


def survey_overlap_link_warnings(
    project_root: Path,
    *,
    state: Mapping[str, object] | None = None,
    only_links: Mapping[str, Mapping[str, str]] | None = None,
) -> list[str]:
    """Return stable advisory warning strings for API write responses."""

    report = audit_survey_overlap_links(project_root, state=state, only_links=only_links, include_same_stem=False)
    warnings: list[str] = []
    for entry in report["gloss_mismatch"]:
        link = entry["link"]
        warnings.append(
            "gloss-mismatch: concept {source_id} ({source_gloss}) links to {survey}:{item} owned by concept {target_id} ({target_gloss})".format(
                source_id=entry["source_id"],
                source_gloss=entry["source_gloss"],
                survey=link["survey"],
                item=link["item"],
                target_id=entry["target_id"],
                target_gloss=entry["target_gloss"],
            )
        )
    for entry in report["dangling"]:
        link = entry["link"]
        warnings.append(
            "dangling: concept {source_id} links to {survey}:{item} but no concepts.csv row owns that survey item".format(
                source_id=entry["source_id"], survey=link["survey"], item=link["item"]
            )
        )
    for entry in report["non_reciprocal"]:
        link = entry["link"]
        backlink = entry["expected_backlink"]
        warnings.append(
            "non-reciprocal: concept {source_id} links to {survey}:{item} owned by concept {target_id}, but target does not link/own back to {back_survey}:{back_item}".format(
                source_id=entry["source_id"],
                survey=link["survey"],
                item=link["item"],
                target_id=entry["target_id"],
                back_survey=backlink["survey"],
                back_item=backlink["item"],
            )
        )
    return warnings


def _load_fixes(path: Path) -> dict[str, dict[str, str | None]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("fixes file must be an object keyed by concept id")
    fixes: dict[str, dict[str, str | None]] = {}
    for concept_id, links in payload.items():
        cid = str(concept_id or "").strip()
        if not cid or not isinstance(links, Mapping):
            continue
        clean_links: dict[str, str | None] = {}
        for survey_id, source_item in links.items():
            survey = normalize_survey_id(survey_id)
            if not survey:
                continue
            if source_item is None:
                clean_links[survey] = None
            else:
                item = str(source_item or "").strip()
                clean_links[survey] = item or None
        if clean_links:
            fixes[cid] = clean_links
    return fixes


def _backup_survey_overlap(project_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%fZ")
    backup_dir = project_root / "backups" / f"survey-overlap-link-integrity-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_path = backup_dir / "survey-overlap.json"
    source_path = project_root / "survey-overlap.json"
    if source_path.exists():
        shutil.copy2(source_path, backup_path)
    else:
        backup_path.write_text(json.dumps(normalize_survey_overlap_state({}), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return backup_path


def apply_survey_overlap_link_fixes(project_root: Path, fixes_file: Path, *, execute: bool = False) -> dict[str, Any]:
    """Dry-run or execute a curated concept_survey_links correction map.

    Fix shape: ``{concept_id: {survey: item_or_null}}``. ``null``/empty removes
    that survey link. Dry-run is the default; execute writes a timestamped backup
    first and is idempotent when the target state is already present.
    """

    project_root = Path(project_root)
    fixes = _load_fixes(Path(fixes_file))
    state = load_survey_overlap_state(project_root)
    current_links: dict[str, dict[str, str]] = {
        cid: dict(links) for cid, links in state.get("concept_survey_links", {}).items()
    }
    next_links: dict[str, dict[str, str]] = {cid: dict(links) for cid, links in current_links.items()}
    would_change: dict[str, dict[str, dict[str, str]]] = {}

    for concept_id in sorted(fixes, key=_id_sort_key):
        before = dict(next_links.get(concept_id, {}))
        after = dict(before)
        for survey, item in fixes[concept_id].items():
            if item is None:
                after.pop(survey, None)
            else:
                after[survey] = item
        if before != after:
            would_change[concept_id] = {"before": before, "after": after}
        if after:
            next_links[concept_id] = after
        else:
            next_links.pop(concept_id, None)

    backup_path: str | None = None
    if execute and would_change:
        backup = _backup_survey_overlap(project_root)
        backup_path = str(backup)
        next_state = dict(state)
        next_state["concept_survey_links"] = next_links
        save_survey_overlap_state(project_root, next_state)

    after_audit = audit_survey_overlap_links(
        project_root,
        state={**state, "concept_survey_links": next_links},
    )
    return {
        "applied": bool(execute),
        "fixes_file": str(Path(fixes_file)),
        "backup_path": backup_path,
        "would_change": would_change,
        "audit_after": after_audit,
    }
