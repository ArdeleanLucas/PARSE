"""Canonical concept-label helpers shared across the PARSE backend.

This module is the Python-side single source of truth for concept variant
suffixes, Audition cue-prefix stripping, and per-speaker variant-letter
assignment. The frontend mirror for letter assignment is
``src/lib/conceptGrouping.ts::assignVariantLetters``; both sides consume
``tests/fixtures/variant-letters.json``.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

# Match trailing parenthetical variant suffixes: "big (A)" or "big (27)".
# Numeric suffixes are preserved for existing concepts_io duplicate behavior once
# A-Z is exhausted; clarifiers such as "(women)" remain untouched.
VARIANT_SUFFIX_RE = re.compile(r"\s*\(([A-Z]|\d+)\)\s*$")

# Match trailing bare single-uppercase-letter variants: "head A" -> "head".
# This intentionally excludes multi-letter/numeric tokens because the lexeme
# notes import path previously stripped only A-D and is widened here only to A-Z.
BARE_VARIANT_RE = re.compile(r"\s+([A-Z])\s*$")

# Match leading Audition-style cue prefixes that may leak into concept labels:
# "48 stomach", "(4.1)- big", "[5.1]- the boy", "63: bread".
LEADING_CUE_PREFIX_RE = re.compile(r"^\s*[\(\[]?\s*\d+(?:\.\d+)*\s*[\)\]]?\s*[-–—:]?\s+")

# Match any parenthetical clarifier chunk. Unlike ``VARIANT_SUFFIX_RE``, this
# intentionally strips free-text clarifiers and variant-like chunks wherever
# callers need a clarifier-tolerant comparison surface rather than data-model
# canonicalization.
CLARIFIER_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")


def variant_suffix(label: str) -> str:
    """Return a trailing parenthetical variant label, or ``""`` if absent."""

    match = VARIANT_SUFFIX_RE.search(str(label or "").strip())
    return match.group(1) if match else ""


def variant_stem(label: str) -> str:
    """Strip a trailing parenthetical variant suffix while preserving clarifiers."""

    return VARIANT_SUFFIX_RE.sub("", str(label or "").strip()).strip()


def strip_bare_variant_suffix(label: str) -> str:
    """Strip a trailing bare A-Z variant suffix from ``label``."""

    return BARE_VARIANT_RE.sub("", str(label or "").strip()).strip()


def strip_cue_prefix(label: str) -> str:
    """Strip a leading Audition cue prefix from ``label`` if present."""

    return LEADING_CUE_PREFIX_RE.sub("", str(label or "").strip()).strip()


def strip_clarifier(label: str) -> str:
    """Strip all parenthetical content from ``label``.

    This is deliberately broader than :func:`variant_stem`: it removes semantic
    clarifiers such as ``"hair (men)"`` / ``"salt (eating)"`` as well as
    variant-like chunks such as ``"big (A)"``. Keep it out of
    :func:`canonicalize_label` until PARSE intentionally performs a data-model
    re-merge; use it only at tolerant comparison/export surfaces.
    """

    text = CLARIFIER_PAREN_RE.sub(" ", str(label or "").strip())
    return " ".join(text.split())


def canonicalize_label(label: str) -> str:
    """Strip cue prefix plus parenthetical or bare variant suffixes."""

    text = strip_cue_prefix(label)
    text = variant_stem(text)
    text = strip_bare_variant_suffix(text)
    return text


def label_key(label: str) -> str:
    """Return PARSE's legacy whitespace-collapsed, casefolded label key."""

    return " ".join(str(label or "").strip().split()).casefold()


def assign_variant_letters(intervals: Sequence[Mapping[str, object]]) -> list[str]:
    """Compute per-interval variant letters by start-time rank.

    Returns letters in input order. Empty input returns ``[]``; a singleton
    returns ``[""]``; two or more intervals receive A, B, C... by ascending
    start time with original index as the deterministic tie-breaker. After Z,
    labels continue as AA, AB, ... to match the frontend helper.
    """

    count = len(intervals)
    if count == 0:
        return []
    if count == 1:
        return [""]

    indexed = [(_start_as_float(interval.get("start", 0.0)), index) for index, interval in enumerate(intervals)]
    indexed.sort(key=lambda item: (item[0], item[1]))

    letters = [""] * count
    for rank, (_start, original_index) in enumerate(indexed):
        letters[original_index] = _letter_for_rank(rank)
    return letters


def _start_as_float(value: object) -> float:
    if isinstance(value, (str, bytes, int, float)):
        try:
            return float(value or 0.0)
        except ValueError:
            return 0.0
    return 0.0


def _letter_for_rank(rank: int) -> str:
    """Return spreadsheet-style zero-based letters: 0 -> A, 25 -> Z, 26 -> AA."""

    n = rank
    label = ""
    while True:
        label = chr(ord("A") + (n % 26)) + label
        n = n // 26 - 1
        if n < 0:
            return label


__all__ = [
    "BARE_VARIANT_RE",
    "CLARIFIER_PAREN_RE",
    "LEADING_CUE_PREFIX_RE",
    "VARIANT_SUFFIX_RE",
    "assign_variant_letters",
    "canonicalize_label",
    "label_key",
    "strip_bare_variant_suffix",
    "strip_clarifier",
    "strip_cue_prefix",
    "variant_stem",
    "variant_suffix",
]
