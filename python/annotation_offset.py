"""Shared annotation timestamp-offset logic for PARSE.

This module is intentionally neutral: both the HTTP offset-apply path
(`server_routes.annotate`) and the chat/MCP tool path (`ai.tools.offset_apply_tools`)
delegate here so offset semantics cannot drift between surfaces again.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ShiftResult:
    """Result envelope for an in-place annotation interval shift."""

    shifted_intervals: int = 0
    skipped_protected: int = 0
    shifted_concepts: set[str] = field(default_factory=set)
    preview: list[dict[str, Any]] = field(default_factory=list)


def _coerce_finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    if number in {float("inf"), float("-inf")}:
        return None
    return number


def interval_concept_identity(tier_key: str, raw: dict[str, Any], index: int) -> str:
    """Return a stable concept identity key for an annotation interval.

    Concept and mirror tiers now usually carry `concept_id` / `conceptId`.
    Legacy concept-tier rows may only have text, so concept-tier text (then row
    index) remains the fallback. Non-concept tiers without an explicit concept
    identity intentionally return the empty string; speaker-tier rows are then
    aligned by interval key instead of by speaker text.
    """
    for key in ("concept_id", "conceptId", "concept", "conceptKey", "id"):
        value = raw.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    if tier_key == "concept":
        text = str(raw.get("text") or "").strip()
        return text or "concept-index:{0}".format(index)
    return ""


def shift_annotation_intervals(
    record: dict[str, Any],
    offset_sec: float,
    *,
    collect_preview: bool = False,
    preview_limit: int = 5,
) -> ShiftResult:
    """Apply a global timestamp offset to annotation intervals in place.

    Concept-tier intervals with `imported_csv_start` are positioned absolutely:
    `new_start = max(0, imported_csv_start + offset_sec)`. Their resulting
    per-concept delta is then applied to mirror tiers (`ipa`, `ortho`,
    `ortho_words`, etc.) carrying the same concept identity. Legacy intervals
    without imported CSV provenance preserve the historical incremental shift.

    A concept-tier `manuallyAdjusted` flag protects that lexeme across mirror
    tiers by concept identity and by original `(start, end)` interval key; direct
    per-tier `manuallyAdjusted` flags are also protected.
    """
    result = ShiftResult()
    if not isinstance(record, dict):
        return result
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return result

    offset = float(offset_sec)
    concept_tier = tiers.get("concept")
    concept_intervals: list[Any] = []
    if isinstance(concept_tier, dict):
        raw_concept_intervals = concept_tier.get("intervals")
        if isinstance(raw_concept_intervals, list):
            concept_intervals = raw_concept_intervals

    delta_by_concept: dict[str, float] = {}
    delta_by_interval_key: dict[tuple[float, float], float] = {}
    protected_concept_ids: set[str] = set()
    protected_interval_keys: set[tuple[float, float]] = set()

    for index, raw in enumerate(concept_intervals):
        if not isinstance(raw, dict):
            continue
        concept_identity = interval_concept_identity("concept", raw, index)
        start = _coerce_finite_float(raw.get("start", raw.get("xmin")))
        end = _coerce_finite_float(raw.get("end", raw.get("xmax")))
        interval_key = (float(start), float(end)) if start is not None and end is not None else None
        if bool(raw.get("manuallyAdjusted")):
            if concept_identity:
                protected_concept_ids.add(concept_identity)
            if interval_key is not None:
                protected_interval_keys.add(interval_key)
            continue
        if start is None:
            continue
        imported_start = _coerce_finite_float(raw.get("imported_csv_start"))
        if imported_start is None:
            delta = offset
        else:
            delta = max(0.0, float(imported_start) + offset) - float(start)
        if concept_identity:
            delta_by_concept[concept_identity] = delta
        if interval_key is not None:
            delta_by_interval_key[interval_key] = delta

    for tier_key, tier in tiers.items():
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals")
        if not isinstance(intervals, list):
            continue
        for index, raw in enumerate(intervals):
            if not isinstance(raw, dict):
                continue
            start = _coerce_finite_float(raw.get("start", raw.get("xmin")))
            end = _coerce_finite_float(raw.get("end", raw.get("xmax")))
            if start is None or end is None:
                continue
            concept_identity = interval_concept_identity(str(tier_key), raw, index)
            interval_key = (float(start), float(end))
            concept_protected = bool(concept_identity) and concept_identity in protected_concept_ids
            interval_protected = interval_key in protected_interval_keys
            if bool(raw.get("manuallyAdjusted")) or concept_protected or interval_protected:
                result.skipped_protected += 1
                continue
            if concept_identity and concept_identity in delta_by_concept:
                delta = delta_by_concept[concept_identity]
            else:
                delta = delta_by_interval_key.get(interval_key, offset)
            new_start = max(0.0, float(start) + delta)
            new_end = max(new_start, float(end) + delta)
            raw["start"] = new_start
            raw["end"] = new_end
            if "xmin" in raw:
                raw["xmin"] = new_start
            if "xmax" in raw:
                raw["xmax"] = new_end
            result.shifted_intervals += 1
            if concept_identity:
                result.shifted_concepts.add(concept_identity)
            if collect_preview and len(result.preview) < preview_limit:
                result.preview.append(
                    {
                        "tier": tier_key,
                        "from": [float(start), float(end)],
                        "to": [new_start, new_end],
                        "concept_id": concept_identity,
                    }
                )

    return result
