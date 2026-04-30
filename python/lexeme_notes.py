"""Parse Adobe Audition marker CSV exports into per-lexeme import notes.

Audition exports marker files as tab-separated values despite the `.csv` extension.
Expected columns: Name, Start, Duration, Time Format, Type, Description.

The `Name` column embeds both the concept id (e.g. "(1.1)") and any analyst
comment tacked onto the label, like:

    (1.1)- hair
    (2.3)- father (vocative) B short word , but it is mostly used by childern

This module extracts (concept_id, start_sec, end_sec, note_text) tuples for
import into parse-enrichments.json under `lexeme_notes`.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


# Match leading Audition cue ids in "(1.1)- label", "[1.1]- label", or "9- label" form.
_PAREN_ID_PATTERN = re.compile(r"^\s*\(\s*([0-9]+(?:\.[0-9]+)*)\s*\)\s*[-\u2013\u2014:]?\s*(.*)$")
_BRACKET_ID_PATTERN = re.compile(r"^\s*\[\s*([0-9]+(?:\.[0-9]+)*)\s*\]\s*[-\u2013\u2014:]?\s*(.*)$")
_PLAIN_ID_PATTERN = re.compile(r"^\s*([0-9]+)\s*[-\u2013\u2014:]\s*(.*)$")
_TRAILING_VARIANT_PATTERN = re.compile(r"\s+([A-D])\s*$")


@dataclass
class CommentRow:
    concept_id: str
    start_sec: float
    duration_sec: float
    raw_name: str
    remainder: str  # text after the id prefix, with a terminal A/B/C/D variant stripped
    variant: str = ""

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec


def _parse_time(value: str) -> Optional[float]:
    """Accept '0:30.105', '1:25.396', '12:03', or plain seconds like '30.105'."""
    text = (value or "").strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
    except ValueError:
        return None
    return None


def _strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _record_value(record: dict, *names: str) -> str:
    normalized = {str(key or "").strip().lower(): value for key, value in record.items()}
    for name in names:
        value = normalized.get(name.strip().lower())
        if value is not None:
            return str(value)
    return ""


def _parse_name_prefix(name: str) -> Optional[tuple[str, str, str]]:
    """Return (concept_id, label/comment remainder, variant) for Audition Name."""
    text = (name or "").strip()
    match = _PAREN_ID_PATTERN.match(text) or _BRACKET_ID_PATTERN.match(text) or _PLAIN_ID_PATTERN.match(text)
    if not match:
        return None
    concept_id = match.group(1).strip()
    remainder = match.group(2).strip()
    variant = ""
    variant_match = _TRAILING_VARIANT_PATTERN.search(remainder)
    if variant_match:
        variant = variant_match.group(1)
        remainder = remainder[: variant_match.start()].strip()
    return concept_id, remainder, variant


def parse_audition_csv(text: str) -> List[CommentRow]:
    """Parse an Audition marker CSV (tab or comma separated) into CommentRows."""
    raw = _strip_bom(text or "")
    if not raw.strip():
        return []

    # Audition exports are tab-separated; sniff to stay tolerant.
    dialect = None
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters="\t,;")
    except csv.Error:
        pass

    reader = csv.DictReader(io.StringIO(raw), dialect=dialect) if dialect else csv.DictReader(io.StringIO(raw), delimiter="\t")

    rows: List[CommentRow] = []
    for record in reader:
        if not record:
            continue
        name = _record_value(record, "Name").strip()
        start_raw = _record_value(record, "Start")
        duration_raw = _record_value(record, "Duration") or "0"
        if not name:
            continue

        parsed_name = _parse_name_prefix(name)
        if parsed_name is None:
            concept_id, remainder, variant = "", name, ""
        else:
            concept_id, remainder, variant = parsed_name
        start_sec = _parse_time(start_raw) or 0.0
        duration_sec = _parse_time(duration_raw) or 0.0

        rows.append(
            CommentRow(
                concept_id=concept_id,
                start_sec=start_sec,
                duration_sec=duration_sec,
                raw_name=name,
                remainder=remainder,
                variant=variant,
            )
        )

    return rows


def _strip_known_label(remainder: str, label: str) -> str:
    """If remainder starts with the concept label, strip it and return the rest."""
    if not label:
        return remainder.strip()
    label_norm = label.strip().lower()
    rem_norm = remainder.strip().lower()
    if rem_norm.startswith(label_norm):
        tail = remainder.strip()[len(label):].strip()
        # Drop connector punctuation after the label.
        while tail.startswith((":", "-", "\u2013", "\u2014", ",")):
            tail = tail[1:].strip()
        return tail
    return remainder.strip()


def match_rows_to_lexemes(
    rows: Sequence[CommentRow],
    lexeme_intervals: Iterable[dict],
    concept_labels: Optional[dict] = None,
    tolerance_sec: float = 0.5,
) -> List[dict]:
    """Align CSV rows to actual lexeme intervals.

    Each `lexeme_intervals` entry: {"concept_id": str, "start": float, "end": float}
    Returns entries: {"concept_id", "note", "matched_start", "csv_start"}.

    Matching strategy:
      1. Prefer rows whose concept_id matches a lexeme concept_id.
      2. Among matches, prefer the lexeme whose start is closest to CSV start.
      3. If no concept_id match, fall back to nearest-time match within tolerance.
    """
    lexemes = [dict(lx) for lx in lexeme_intervals]
    results: List[dict] = []

    for row in rows:
        label = ""
        if concept_labels and row.concept_id in concept_labels:
            label = str(concept_labels[row.concept_id] or "")
        note_text = _strip_known_label(row.remainder, label)

        by_id = [lx for lx in lexemes if lx.get("concept_id") == row.concept_id]
        chosen: Optional[dict] = None

        if by_id:
            chosen = min(by_id, key=lambda lx: abs(float(lx.get("start") or 0.0) - row.start_sec))
        else:
            candidates = [
                lx for lx in lexemes
                if abs(float(lx.get("start") or 0.0) - row.start_sec) <= tolerance_sec
            ]
            if candidates:
                chosen = min(candidates, key=lambda lx: abs(float(lx.get("start") or 0.0) - row.start_sec))

        results.append({
            "concept_id": (chosen.get("concept_id") if chosen else row.concept_id) or row.concept_id,
            "note": note_text,
            "raw_name": row.raw_name,
            "matched_start": chosen.get("start") if chosen else None,
            "csv_start": row.start_sec,
            "csv_duration": row.duration_sec,
            "was_matched": chosen is not None,
        })

    return results
