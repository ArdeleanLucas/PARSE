"""Compute cross-survey concept_survey_links patches from a reference lexeme CSV.

This module is intentionally sidecar-only: it reads `concepts.csv`, reads the
reference CSV (`source,id,lexeme`), and returns a patch suitable for
`survey-overlap.json::concept_survey_links`. It never mutates concepts or
annotations directly.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Mapping

from concept_registry import concept_label_key
from concept_source_item import read_concepts_csv_rows, row_value
from survey_overlap import load_survey_overlap_state, normalize_survey_id, update_survey_overlap_state

CrossSurveyLinkSummary = dict[str, list[dict[str, object]]]


def _empty_summary() -> CrossSurveyLinkSummary:
    return {"matched": [], "would_add": [], "conflicts": [], "skipped_multiword": []}


def _strip_parens(label: str) -> str:
    """Return label text with one pass of parenthetical disambiguators removed."""

    return re.sub(r"\s*\([^)]*\)\s*", " ", str(label or "")).strip()


def _stripped_label_key(label: str) -> str:
    return concept_label_key(_strip_parens(label))


def _is_single_word_concept(label: str) -> bool:
    text = _strip_parens(label)
    return bool(text) and "(" not in text and ")" not in text and "," not in text and not any(ch.isspace() for ch in text)


def _ordered_links(links: Mapping[str, str]) -> dict[str, str]:
    return {sid: str(links[sid]) for sid in sorted(links)}


def _add_reference_link(
    index: dict[str, dict[str, str]],
    conflicts: dict[str, list[dict[str, str]]],
    key: str,
    survey_id: str,
    source_item: str,
) -> None:
    links = index.setdefault(key, {})
    existing = links.get(survey_id)
    if existing and existing != source_item:
        conflicts.setdefault(key, []).append(
            {"survey": survey_id, "first_source_item": existing, "conflicting_source_item": source_item}
        )
        return
    links[survey_id] = source_item


def _read_reference_links(
    reference_path: Path,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, list[dict[str, str]]],
    dict[str, dict[str, str]],
    set[str],
]:
    exact_index: dict[str, dict[str, str]] = {}
    exact_conflicts: dict[str, list[dict[str, str]]] = {}
    stripped_entries: dict[str, dict[str, list[tuple[str, str]]]] = {}
    with reference_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            survey_id = normalize_survey_id(row_value(row, "source"))
            source_item = row_value(row, "id")
            label = row_value(row, "lexeme")
            key = concept_label_key(label)
            stripped_key = _stripped_label_key(label)
            if not survey_id or not source_item or not key:
                continue
            _add_reference_link(exact_index, exact_conflicts, key, survey_id, source_item)
            if stripped_key:
                stripped_entries.setdefault(stripped_key, {}).setdefault(survey_id, []).append((label, source_item))

    stripped_index: dict[str, dict[str, str]] = {}
    stripped_ambiguous_keys: set[str] = set()
    for stripped_key, survey_entries in stripped_entries.items():
        for survey_id, entries in survey_entries.items():
            if len(entries) == 1:
                source_item = entries[0][1]
            else:
                bare_entries = [
                    source_item for original_label, source_item in entries if concept_label_key(original_label) == stripped_key
                ]
                if len(bare_entries) != 1:
                    stripped_ambiguous_keys.add(stripped_key)
                    continue
                source_item = bare_entries[0]
            stripped_index.setdefault(stripped_key, {})[survey_id] = source_item
    return exact_index, exact_conflicts, stripped_index, stripped_ambiguous_keys


def compute_cross_survey_link_patch(
    workspace: Path | str,
    reference_path: Path | str,
    single_word_only: bool = True,
) -> CrossSurveyLinkSummary:
    """Return sidecar link additions for concepts found in a reference lexeme CSV.

    A concept is safe to populate only when its legacy primary
    `(source_survey, source_item)` exactly matches the reference row for the same
    lexeme. Matching reference links already present in the sidecar are not
    returned in `would_add`, making the output idempotent after apply.
    """

    workspace_path = Path(workspace).expanduser().resolve()
    reference = Path(reference_path).expanduser().resolve()
    summary = _empty_summary()
    rows = read_concepts_csv_rows(workspace_path / "concepts.csv")
    if not rows:
        return summary

    reference_links, reference_conflicts, stripped_reference_links, stripped_ambiguous_keys = _read_reference_links(reference)
    state = load_survey_overlap_state(workspace_path)
    sidecar_links_raw = state.get("concept_survey_links")
    sidecar_links = sidecar_links_raw if isinstance(sidecar_links_raw, Mapping) else {}

    for row in rows:
        concept_id = str(row.get("id") or "").strip()
        label = str(row.get("concept_en") or "").strip()
        if not concept_id or not label:
            continue
        if single_word_only and not _is_single_word_concept(label):
            summary["skipped_multiword"].append(
                {"concept_id": concept_id, "concept_en": label, "reason": "single_word_only"}
            )
            continue

        label_key = concept_label_key(label)
        links = reference_links.get(label_key)
        if label_key in reference_conflicts:
            summary["conflicts"].append(
                {
                    "concept_id": concept_id,
                    "concept_en": label,
                    "reason": "reference_ambiguous",
                    "reference_conflicts": reference_conflicts[label_key],
                }
            )
            continue

        if not links or len(links) < 2:
            stripped_key = _stripped_label_key(label)
            stripped_links = stripped_reference_links.get(stripped_key) if stripped_key else None
            if stripped_key in stripped_ambiguous_keys:
                summary["conflicts"].append(
                    {
                        "concept_id": concept_id,
                        "concept_en": label,
                        "reason": "stripped_match_ambiguous",
                        "stripped_key": stripped_key,
                    }
                )
                continue
            if stripped_links and len(stripped_links) >= 2:
                links = stripped_links
        if not links:
            continue

        legacy_survey = normalize_survey_id(row.get("source_survey"))
        legacy_item = str(row.get("source_item") or "").strip()
        reference_primary = links.get(legacy_survey)
        if not legacy_survey or not legacy_item or reference_primary != legacy_item:
            summary["conflicts"].append(
                {
                    "concept_id": concept_id,
                    "concept_en": label,
                    "reason": "legacy_primary_mismatch",
                    "legacy_primary": {"survey": legacy_survey, "source_item": legacy_item},
                    "reference_primary": {"survey": legacy_survey, "source_item": reference_primary or ""},
                    "reference_links": _ordered_links(links),
                }
            )
            continue

        existing_for_concept_raw = sidecar_links.get(concept_id) if isinstance(sidecar_links, Mapping) else None
        existing_for_concept = existing_for_concept_raw if isinstance(existing_for_concept_raw, Mapping) else {}
        sidecar_mismatches: list[dict[str, str]] = []
        additions: dict[str, str] = {}
        for survey_id, source_item in sorted(links.items()):
            if survey_id == legacy_survey and source_item == legacy_item:
                continue
            existing_source_item = str(existing_for_concept.get(survey_id) or "").strip()
            if existing_source_item == source_item:
                continue
            if existing_source_item and existing_source_item != source_item:
                sidecar_mismatches.append(
                    {
                        "survey": survey_id,
                        "existing_source_item": existing_source_item,
                        "reference_source_item": source_item,
                    }
                )
                continue
            additions[survey_id] = source_item

        summary["matched"].append(
            {
                "concept_id": concept_id,
                "concept_en": label,
                "legacy_primary": {"survey": legacy_survey, "source_item": legacy_item},
                "reference_links": _ordered_links(links),
            }
        )
        if sidecar_mismatches:
            summary["conflicts"].append(
                {
                    "concept_id": concept_id,
                    "concept_en": label,
                    "reason": "existing_sidecar_mismatch",
                    "sidecar_mismatches": sidecar_mismatches,
                }
            )
            continue
        if additions:
            summary["would_add"].append(
                {"concept_id": concept_id, "concept_en": label, "links": _ordered_links(additions)}
            )

    return summary


def patch_from_cross_survey_link_summary(
    summary: Mapping[str, object],
    *,
    full: bool = False,
) -> dict[str, dict[str, str]]:
    """Return an `update_survey_overlap_state` patch from a computed summary.

    Merge mode writes only `would_add` deltas. Replace mode must rebuild the
    sidecar from the full matched set because the current sidecar is cleared
    before write.
    """

    patch: dict[str, dict[str, str]] = {}
    entries_key = "matched" if full else "would_add"
    entries = summary.get(entries_key) if isinstance(summary, Mapping) else None
    if not isinstance(entries, list):
        return patch
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        concept_id = str(entry.get("concept_id") or "").strip()
        links_raw = entry.get("reference_links" if full else "links")
        if not concept_id or not isinstance(links_raw, Mapping):
            continue
        legacy_survey = ""
        if full:
            legacy_primary = entry.get("legacy_primary")
            if isinstance(legacy_primary, Mapping):
                legacy_survey = normalize_survey_id(legacy_primary.get("survey"))
        links = {
            normalized_survey: str(source_item or "").strip()
            for survey_id, source_item in links_raw.items()
            if (normalized_survey := normalize_survey_id(survey_id))
            and normalized_survey != legacy_survey
            and str(source_item or "").strip()
        }
        if links:
            patch[concept_id] = _ordered_links(links)
    return patch


def _sidecar_diff(
    before: Mapping[str, object],
    after: Mapping[str, object],
    patch: Mapping[str, Mapping[str, str]],
    *,
    replace: bool,
) -> dict[str, Any]:
    concept_ids = sorted(patch)
    return {
        "before": {concept_id: before.get(concept_id, {}) for concept_id in concept_ids},
        "after": {concept_id: after.get(concept_id, {}) for concept_id in concept_ids},
        "added": {concept_id: dict(patch[concept_id]) for concept_id in concept_ids},
        "replace_mode": bool(replace),
    }


def apply_cross_survey_link_patch(
    workspace: Path | str,
    summary: Mapping[str, object],
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Apply a computed cross-survey link summary to survey-overlap.json.

    Merge mode preserves existing `concept_survey_links`; replace mode clears only
    that sidecar section before writing the computed patch. All other
    survey-overlap sections are left untouched by `update_survey_overlap_state`.
    """

    workspace_path = Path(workspace).expanduser().resolve()
    patch = patch_from_cross_survey_link_summary(summary, full=replace)
    before_state = load_survey_overlap_state(workspace_path)
    before_links = dict(before_state.get("concept_survey_links") or {})
    if patch or replace:
        patch_payload: dict[str, object] = {"concept_survey_links": patch}
        if replace:
            patch_payload["reset_concept_survey_links"] = True
        after_state = update_survey_overlap_state(workspace_path, patch_payload)
    else:
        after_state = before_state
    after_links = dict(after_state.get("concept_survey_links") or {})
    return _sidecar_diff(before_links, after_links, patch, replace=replace)
