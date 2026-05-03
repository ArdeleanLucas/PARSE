"""Shared source-item helpers for PARSE concepts.csv."""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence

CONCEPT_FIELDNAMES: tuple[str, ...] = (
    "id",
    "concept_en",
    "source_item",
    "source_survey",
    "custom_order",
)
OPTIONAL_CONCEPT_FIELDNAMES: tuple[str, ...] = (
    "source_item",
    "source_survey",
    "custom_order",
)
LEGACY_SOURCE_ITEM_FIELDNAMES: tuple[str, ...] = ("survey_item",)

_KLQ_RE = re.compile(r"^\s*\(\s*([0-9]+(?:\.[0-9]+)*)\s*\)\s*[-\u2013\u2014]?\s*(.+?)\s*$")
_EXT_RE = re.compile(r"^\s*\[\s*([0-9]+(?:\.[0-9]+)*)\s*\]\s*[-\u2013\u2014]?\s*(.+?)\s*$")
# JBIL is flat-number-only; match order is KLQ -> EXT -> JBIL -> fallback.
_JBIL_RE = re.compile(r"^\s*([0-9]+)\s*[-\u2013\u2014]\s*(.+?)\s*$")


def parse_cue_name(cue: str) -> tuple[str | None, str | None, str]:
    """Return ``(source_item, source_survey, label)`` for an Audition cue name.

    Recognized formats:
        KLQ:  ``(1.2)- forehead``       -> ("1.2", "KLQ", "forehead")
        EXT:  ``[5.1]- The boy cut...`` -> ("5.1", "EXT", "The boy cut...")
        JBIL: ``324- we``               -> ("324", "JBIL", "we")

    Unrecognized free-form labels return ``(None, None, stripped_cue)`` so
    callers can still match rows by label without dropping data.
    """

    text = str(cue or "").strip()
    for regex, survey in ((_KLQ_RE, "KLQ"), (_EXT_RE, "EXT"), (_JBIL_RE, "JBIL")):
        match = regex.match(text)
        if match:
            return match.group(1), survey, match.group(2).strip()
    return None, None, text


def row_value(row: Mapping[str, object], *names: str) -> str:
    """Return the first case-insensitive CSV value for ``names`` from ``row``."""

    normalized = {str(key or "").strip().lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(str(name or "").strip().lower())
        if value is not None:
            return str(value or "").strip()
    return ""


def normalize_concept_csv_row(row: Mapping[str, object]) -> dict[str, str]:
    """Normalize any supported concepts.csv row to the current five columns."""

    return {
        "id": row_value(row, "id"),
        "concept_en": row_value(row, "concept_en", "label"),
        "source_item": row_value(row, "source_item", *LEGACY_SOURCE_ITEM_FIELDNAMES),
        "source_survey": row_value(row, "source_survey"),
        "custom_order": row_value(row, "custom_order"),
    }


def concept_row_from_item(item: Mapping[str, object]) -> dict[str, str]:
    """Normalize tool/import items that may use ``label`` instead of ``concept_en``."""

    row = normalize_concept_csv_row(item)
    if not row["concept_en"]:
        row["concept_en"] = row_value(item, "label")
    return row


def read_concepts_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read concepts.csv leniently and return current-schema rows."""

    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [normalize_concept_csv_row(row) for row in reader]


def write_concepts_csv_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    atomic: bool = False,
) -> None:
    """Write rows with the current concepts.csv header.

    When ``atomic`` is true, the file is written to ``concepts.csv.tmp``, fsynced,
    and renamed into place to avoid torn writes for MCP mutators.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_suffix(path.suffix + ".tmp") if atomic else path
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CONCEPT_FIELDNAMES))
        writer.writeheader()
        for row in rows:
            normalized = concept_row_from_item(row)
            writer.writerow({key: normalized.get(key, "") or "" for key in CONCEPT_FIELDNAMES})
        handle.flush()
        if atomic:
            os.fsync(handle.fileno())
    if atomic:
        target.replace(path)
        try:
            directory_fd = os.open(str(path.parent), os.O_DIRECTORY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def source_item_from_audition_row(row: object) -> tuple[str, str]:
    """Return ``(source_item, source_survey)`` for a parsed Audition row."""

    raw_name = str(getattr(row, "raw_name", "") or "")
    source_item, source_survey, _label = parse_cue_name(raw_name)
    if source_item:
        return source_item, (source_survey or "")
    return str(getattr(row, "concept_id", "") or "").strip(), ""


def ensure_concept_fieldnames(rows: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    """Return normalized rows ready for current-header CSV writing."""

    return [concept_row_from_item(row) for row in rows]
