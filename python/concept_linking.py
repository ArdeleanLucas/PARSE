"""Cross-survey concept linking helpers.

Implements the canonical-gloss matcher specified in
docs/cross-survey-concept-linking-plan.md section 3:

1. Trim input.
2. Strip one leading KLQ-style ``(N.M)- `` prefix (already-parsed JBIL bare
   prefixes are also normalized via :func:`parse_cue_name` first).
3. Strip one trailing single-uppercase variant suffix (`` A``..`` Z``).
4. Lowercase and collapse internal whitespace.
5. Keep parenthetical clarifiers strict.
6. Keep comma-separated alternatives strict.

A separate :func:`build_canonical_gloss_index` returns a mapping from canonical
key to the list of concept_ids that share that key. Callers decide what to do
when more than one id is present (the spec says: do not auto-link).
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

from concept_source_item import parse_cue_name

_KLQ_PREFIX_RE = re.compile(r"^\(\s*\d+(?:\.\d+)*\s*\)\s*[-–—]?\s*")
_TRAILING_VARIANT_RE = re.compile(r"\s+[A-Z]$")


def normalize_cross_survey_gloss(label: str) -> str:
    """Return the canonical v1 cross-survey key for ``label`` (empty if blank)."""

    text = str(label or "").strip()
    if not text:
        return ""

    # Step 2/3: strip one KLQ ``(N.M)- `` or JBIL ``N- `` prefix. parse_cue_name
    # already handles JBIL bare-numeric prefixes; we use it first when the label
    # looks like a bare-numeric cue so the leading number is removed before the
    # KLQ regex runs (which would no-op for bare numerics anyway).
    _item, _survey, parsed_label = parse_cue_name(text)
    text = parsed_label or text
    text = _KLQ_PREFIX_RE.sub("", text).strip()

    # Step 4: strip a single trailing uppercase variant suffix.
    text = _TRAILING_VARIANT_RE.sub("", text).strip()

    # Step 5: lowercase + collapse whitespace.
    text = " ".join(text.split()).casefold()
    return text


def build_canonical_gloss_index(rows: Iterable[Mapping[str, object]]) -> dict[str, list[str]]:
    """Map canonical key -> list of concept_ids whose label normalizes to it.

    Multiple ids at one key signal an ambiguous match; callers must not
    auto-link in that case.
    """

    index: dict[str, list[str]] = {}
    for row in rows:
        cid = str(row.get("id") or "").strip()
        label = str(row.get("concept_en") or "").strip()
        if not cid or not label:
            continue
        key = normalize_cross_survey_gloss(label)
        if not key:
            continue
        bucket = index.setdefault(key, [])
        if cid not in bucket:
            bucket.append(cid)
    return index


__all__ = ["normalize_cross_survey_gloss", "build_canonical_gloss_index"]
