#!/usr/bin/env python3
"""
textgrid_io.py - Praat TextGrid read/write helpers for PARSE.

This module provides bidirectional TextGrid I/O for PARSE's interval-tier
annotation model:
  - Read TextGrid long format
  - Read TextGrid short format
  - Write TextGrid long format

Public API:
  - read_textgrid(path)
  - write_textgrid(annotation_data, path, speaker)
  - annotations_to_textgrid_str(annotation_data, speaker)
  - textgrid_to_annotations(textgrid_data, speaker, project_id, source_audio)
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path


# Canonical tier names emitted into TextGrid files. The `ipa_phone` tier was
# added when phone-level IPA lanes shipped — Praat convention is short tier
# names, so we use "Phones" rather than "IPA (phones)". The word/lexeme tier
# stays "IPA". The `sentence` tier ships empty until sentence segmentation is
# wired up; it round-trips so external Praat edits aren't lost.
_CANONICAL_TEXTGRID_NAMES = {
    "ipa_phone": "Phones",
    "ipa": "IPA",
    "ortho": "Ortho",
    "stt": "STT",
    "concept": "Concept",
    "sentence": "Sentence",
    "speaker": "Speaker",
}

# Numeric ordering used to sort exported TextGrid tiers. Matches
# CANONICAL_TIER_ORDER in src/stores/annotationStore.ts — keep in sync.
_CANONICAL_DISPLAY_ORDERS = {
    "ipa_phone": 1,
    "ipa": 2,
    "ortho": 3,
    "stt": 4,
    "concept": 5,
    "sentence": 6,
    "speaker": 7,
}

_LONG_ITEM_HEADER_RE = re.compile(r"^item\s*\[\s*(\d+)\s*\]\s*:$")
_LONG_INTERVAL_HEADER_RE = re.compile(r"^intervals\s*\[\s*(\d+)\s*\]\s*:$")


class _LineReader:
    """Minimal line reader with helpful parse errors."""

    def __init__(self, lines: list[str], source_label: str) -> None:
        self._lines = lines
        self._source_label = source_label
        self._index = 0

    @property
    def source_label(self) -> str:
        return self._source_label

    def next_nonempty(self, context: str) -> tuple[str, int]:
        while self._index < len(self._lines):
            raw = self._lines[self._index]
            line_no = self._index + 1
            self._index += 1
            if line_no == 1 and raw.startswith("\ufeff"):
                raw = raw.lstrip("\ufeff")
            stripped = raw.strip()
            if stripped == "":
                continue
            return stripped, line_no
        raise ValueError(
            f"{self._source_label}: unexpected end of file while {context}"
        )


def _is_finite_number(value: float) -> bool:
    return value == value and value != float("inf") and value != float("-inf")


def _parse_quoted_token(
    token: str,
    source_label: str,
    line_no: int,
    context: str,
) -> str:
    if len(token) < 2 or not token.startswith('"') or not token.endswith('"'):
        raise ValueError(
            f"{source_label}: line {line_no}: expected quoted string for {context}, got {token!r}"
        )
    return token[1:-1].replace('""', '"')


def _parse_float_token(
    token: str,
    source_label: str,
    line_no: int,
    context: str,
) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise ValueError(
            f"{source_label}: line {line_no}: expected numeric value for {context}, got {token!r}"
        ) from exc

    if not _is_finite_number(value):
        raise ValueError(
            f"{source_label}: line {line_no}: non-finite numeric value for {context}"
        )
    return value


def _parse_int_token(
    token: str,
    source_label: str,
    line_no: int,
    context: str,
) -> int:
    value = _parse_float_token(token, source_label, line_no, context)
    if int(value) != value:
        raise ValueError(
            f"{source_label}: line {line_no}: expected integer value for {context}, got {token!r}"
        )
    return int(value)


def _extract_assignment_value(
    line: str,
    key: str,
    source_label: str,
    line_no: int,
) -> str:
    pattern = r"^" + re.escape(key) + r"\s*=\s*(.+)$"
    match = re.match(pattern, line)
    if not match:
        raise ValueError(
            f"{source_label}: line {line_no}: expected '{key} = ...', got {line!r}"
        )
    return match.group(1).strip()


def _read_assignment_token(reader: _LineReader, key: str) -> tuple[str, int]:
    line, line_no = reader.next_nonempty(f"reading '{key}'")
    value = _extract_assignment_value(line, key, reader.source_label, line_no)
    return value, line_no


def _read_regex(
    reader: _LineReader,
    regex: re.Pattern,
    context: str,
) -> tuple[re.Match, int]:
    line, line_no = reader.next_nonempty(context)
    match = regex.match(line)
    if not match:
        raise ValueError(
            f"{reader.source_label}: line {line_no}: malformed structure while {context}, got {line!r}"
        )
    return match, line_no


def _parse_short_header_file_type(line: str, source_label: str, line_no: int) -> str:
    if line.startswith("File type"):
        token = _extract_assignment_value(line, "File type", source_label, line_no)
        return _parse_quoted_token(token, source_label, line_no, "File type")
    if line.startswith('"'):
        return _parse_quoted_token(line, source_label, line_no, "File type")
    raise ValueError(
        f"{source_label}: line {line_no}: invalid TextGrid header line: {line!r}"
    )


def _parse_short_header_object_class(line: str, source_label: str, line_no: int) -> str:
    if line.startswith("Object class"):
        token = _extract_assignment_value(line, "Object class", source_label, line_no)
        return _parse_quoted_token(token, source_label, line_no, "Object class")
    if line.startswith('"'):
        return _parse_quoted_token(line, source_label, line_no, "Object class")
    if line == "TextGrid":
        return line
    raise ValueError(
        f"{source_label}: line {line_no}: invalid object class line: {line!r}"
    )


def _parse_short_string_or_bare(token: str, source_label: str, line_no: int, context: str) -> str:
    if token.startswith('"'):
        return _parse_quoted_token(token, source_label, line_no, context)
    return token


def _normalize_tier_name(tier_name: str) -> str:
    stripped = tier_name.strip()
    canonical_key = _canonical_annotation_key(stripped)
    if canonical_key is not None:
        return canonical_key
    return stripped


def _canonical_annotation_key(tier_name: str) -> str | None:
    lower = tier_name.strip().lower()
    if lower in _CANONICAL_TEXTGRID_NAMES:
        return lower
    return None


def _annotation_tier_to_textgrid_name(tier_name: str) -> str:
    lower = tier_name.strip().lower()
    if lower in _CANONICAL_TEXTGRID_NAMES:
        return _CANONICAL_TEXTGRID_NAMES[lower]
    return tier_name


def _coerce_float(value: object, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context}: boolean is not a valid number")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        raise ValueError(f"{context}: expected numeric value")
    if not _is_finite_number(number):
        raise ValueError(f"{context}: value must be finite")
    return number


def _coerce_display_order(value: object, default_order: int, context: str) -> int:
    if value is None:
        return default_order
    order = _coerce_float(value, context)
    if int(order) != order or int(order) < 1:
        raise ValueError(f"{context}: display_order must be a positive integer")
    return int(order)


def _normalize_intervals(intervals_value: object, context: str) -> list[dict]:
    if intervals_value is None:
        return []
    if not isinstance(intervals_value, list):
        raise ValueError(f"{context}: intervals must be a list")

    normalized = []
    for idx, interval in enumerate(intervals_value, start=1):
        if not isinstance(interval, dict):
            raise ValueError(f"{context}: interval[{idx}] must be an object")

        if "start" in interval:
            start_raw = interval["start"]
        elif "xmin" in interval:
            start_raw = interval["xmin"]
        else:
            raise ValueError(f"{context}: interval[{idx}] missing 'start'/'xmin'")

        if "end" in interval:
            end_raw = interval["end"]
        elif "xmax" in interval:
            end_raw = interval["xmax"]
        else:
            raise ValueError(f"{context}: interval[{idx}] missing 'end'/'xmax'")

        start = _coerce_float(start_raw, f"{context} interval[{idx}] start")
        end = _coerce_float(end_raw, f"{context} interval[{idx}] end")
        if start < 0:
            raise ValueError(f"{context}: interval[{idx}] start must be >= 0")
        if end < start:
            raise ValueError(f"{context}: interval[{idx}] end < start")

        text = interval.get("text", "")
        if text is None:
            text = ""
        normalized.append(
            {
                "start": float(start),
                "end": float(end),
                "text": str(text),
            }
        )

    return normalized


def _float_to_textgrid_number(value: float) -> str:
    text = repr(float(value))
    if text == "-0.0":
        return "0.0"
    return text


def _quote_textgrid_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _fill_interval_gaps(intervals: list[dict], duration: float) -> list[dict]:
    if duration < 0:
        raise ValueError("duration must be >= 0")

    ordered = sorted(intervals, key=lambda item: (item["start"], item["end"]))
    filled: list[dict] = []
    cursor = 0.0

    for interval in ordered:
        start = interval["start"]
        end = interval["end"]
        text = interval["text"]

        if start > cursor:
            filled.append({"start": float(cursor), "end": float(start), "text": ""})

        filled.append({"start": float(start), "end": float(end), "text": str(text)})

        if end > cursor:
            cursor = end

    if duration > cursor:
        filled.append({"start": float(cursor), "end": float(duration), "text": ""})

    if not filled and duration > 0:
        filled.append({"start": 0.0, "end": float(duration), "text": ""})

    return filled


def _parse_long_textgrid(lines: list[str], source_label: str) -> dict:
    reader = _LineReader(lines, source_label)

    file_type_token, file_type_line = _read_assignment_token(reader, "File type")
    file_type = _parse_quoted_token(
        file_type_token,
        source_label,
        file_type_line,
        "File type",
    )
    if "ootextfile" not in file_type.lower():
        raise ValueError(
            f"{source_label}: line {file_type_line}: unsupported File type {file_type!r}"
        )
    if "short" in file_type.lower():
        raise ValueError(
            f"{source_label}: line {file_type_line}: file declares short format, not long format"
        )

    object_token, object_line = _read_assignment_token(reader, "Object class")
    object_class = _parse_quoted_token(
        object_token,
        source_label,
        object_line,
        "Object class",
    )
    if object_class != "TextGrid":
        raise ValueError(
            f"{source_label}: line {object_line}: unsupported object class {object_class!r}"
        )

    xmin_token, xmin_line = _read_assignment_token(reader, "xmin")
    xmax_token, xmax_line = _read_assignment_token(reader, "xmax")
    xmin = _parse_float_token(xmin_token, source_label, xmin_line, "xmin")
    xmax = _parse_float_token(xmax_token, source_label, xmax_line, "xmax")

    tiers_line, tiers_line_no = reader.next_nonempty("reading tiers marker")
    if not re.match(r"^tiers\?\s*<exists>$", tiers_line):
        raise ValueError(
            f"{source_label}: line {tiers_line_no}: expected 'tiers? <exists>', got {tiers_line!r}"
        )

    size_token, size_line = _read_assignment_token(reader, "size")
    tier_count = _parse_int_token(size_token, source_label, size_line, "tier count")
    if tier_count < 0:
        raise ValueError(
            f"{source_label}: line {size_line}: tier count must be >= 0"
        )

    item_header_line, item_header_no = reader.next_nonempty("reading item list header")
    if not re.match(r"^item\s*\[\s*\]\s*:$", item_header_line):
        raise ValueError(
            f"{source_label}: line {item_header_no}: expected 'item []:', got {item_header_line!r}"
        )

    tiers = []
    for _ in range(tier_count):
        _match, _line_no = _read_regex(reader, _LONG_ITEM_HEADER_RE, "reading tier header")

        class_token, class_line = _read_assignment_token(reader, "class")
        tier_class = _parse_quoted_token(class_token, source_label, class_line, "tier class")
        if tier_class != "IntervalTier":
            raise ValueError(
                f"{source_label}: line {class_line}: unsupported tier class {tier_class!r}; only IntervalTier is supported"
            )

        name_token, name_line = _read_assignment_token(reader, "name")
        tier_name = _parse_quoted_token(name_token, source_label, name_line, "tier name")
        if tier_name.strip() == "":
            raise ValueError(
                f"{source_label}: line {name_line}: tier name cannot be empty"
            )

        tier_xmin_token, tier_xmin_line = _read_assignment_token(reader, "xmin")
        tier_xmax_token, tier_xmax_line = _read_assignment_token(reader, "xmax")
        tier_xmin = _parse_float_token(
            tier_xmin_token,
            source_label,
            tier_xmin_line,
            f"tier '{tier_name}' xmin",
        )
        tier_xmax = _parse_float_token(
            tier_xmax_token,
            source_label,
            tier_xmax_line,
            f"tier '{tier_name}' xmax",
        )

        intervals_size_line, intervals_size_no = reader.next_nonempty(
            f"reading interval count for tier '{tier_name}'"
        )
        intervals_match = re.match(r"^intervals:\s*size\s*=\s*(.+)$", intervals_size_line)
        if not intervals_match:
            raise ValueError(
                f"{source_label}: line {intervals_size_no}: expected 'intervals: size = N', got {intervals_size_line!r}"
            )
        interval_count = _parse_int_token(
            intervals_match.group(1).strip(),
            source_label,
            intervals_size_no,
            f"interval count for tier '{tier_name}'",
        )
        if interval_count < 0:
            raise ValueError(
                f"{source_label}: line {intervals_size_no}: interval count must be >= 0"
            )

        intervals = []
        for _ in range(interval_count):
            _match, _line_no = _read_regex(
                reader,
                _LONG_INTERVAL_HEADER_RE,
                f"reading interval header for tier '{tier_name}'",
            )

            int_xmin_token, int_xmin_line = _read_assignment_token(reader, "xmin")
            int_xmax_token, int_xmax_line = _read_assignment_token(reader, "xmax")
            text_token, text_line = _read_assignment_token(reader, "text")

            start = _parse_float_token(
                int_xmin_token,
                source_label,
                int_xmin_line,
                f"interval xmin in tier '{tier_name}'",
            )
            end = _parse_float_token(
                int_xmax_token,
                source_label,
                int_xmax_line,
                f"interval xmax in tier '{tier_name}'",
            )
            if end < start:
                raise ValueError(
                    f"{source_label}: line {int_xmax_line}: interval xmax < xmin in tier '{tier_name}'"
                )

            text = _parse_quoted_token(
                text_token,
                source_label,
                text_line,
                f"interval text in tier '{tier_name}'",
            )

            intervals.append({"start": start, "end": end, "text": text})

        tiers.append(
            {
                "name": tier_name,
                "class": tier_class,
                "xmin": tier_xmin,
                "xmax": tier_xmax,
                "intervals": intervals,
            }
        )

    return {"xmin": xmin, "xmax": xmax, "tiers": tiers}


def _parse_short_textgrid(lines: list[str], source_label: str) -> dict:
    reader = _LineReader(lines, source_label)

    header_line, header_no = reader.next_nonempty("reading file header")
    file_type = _parse_short_header_file_type(header_line, source_label, header_no)
    if "ootextfile" not in file_type.lower():
        raise ValueError(
            f"{source_label}: line {header_no}: unsupported File type {file_type!r}"
        )

    class_line, class_no = reader.next_nonempty("reading object class")
    object_class = _parse_short_header_object_class(class_line, source_label, class_no)
    if object_class != "TextGrid":
        raise ValueError(
            f"{source_label}: line {class_no}: unsupported object class {object_class!r}"
        )

    xmin_line, xmin_no = reader.next_nonempty("reading xmin")
    xmax_line, xmax_no = reader.next_nonempty("reading xmax")
    xmin = _parse_float_token(xmin_line, source_label, xmin_no, "xmin")
    xmax = _parse_float_token(xmax_line, source_label, xmax_no, "xmax")

    exists_line, exists_no = reader.next_nonempty("reading tiers marker")
    if exists_line not in ("<exists>", "tiers? <exists>"):
        raise ValueError(
            f"{source_label}: line {exists_no}: expected '<exists>', got {exists_line!r}"
        )

    count_line, count_no = reader.next_nonempty("reading tier count")
    tier_count = _parse_int_token(count_line, source_label, count_no, "tier count")
    if tier_count < 0:
        raise ValueError(
            f"{source_label}: line {count_no}: tier count must be >= 0"
        )

    tiers = []
    for tier_index in range(1, tier_count + 1):
        tier_class_line, tier_class_no = reader.next_nonempty(
            f"reading class for tier #{tier_index}"
        )
        tier_class = _parse_short_string_or_bare(
            tier_class_line,
            source_label,
            tier_class_no,
            f"class for tier #{tier_index}",
        )
        if tier_class != "IntervalTier":
            raise ValueError(
                f"{source_label}: line {tier_class_no}: unsupported tier class {tier_class!r}; only IntervalTier is supported"
            )

        tier_name_line, tier_name_no = reader.next_nonempty(
            f"reading name for tier #{tier_index}"
        )
        tier_name = _parse_short_string_or_bare(
            tier_name_line,
            source_label,
            tier_name_no,
            f"name for tier #{tier_index}",
        )
        if tier_name.strip() == "":
            raise ValueError(
                f"{source_label}: line {tier_name_no}: tier name cannot be empty"
            )

        tier_xmin_line, tier_xmin_no = reader.next_nonempty(
            f"reading xmin for tier '{tier_name}'"
        )
        tier_xmax_line, tier_xmax_no = reader.next_nonempty(
            f"reading xmax for tier '{tier_name}'"
        )
        tier_xmin = _parse_float_token(
            tier_xmin_line,
            source_label,
            tier_xmin_no,
            f"tier '{tier_name}' xmin",
        )
        tier_xmax = _parse_float_token(
            tier_xmax_line,
            source_label,
            tier_xmax_no,
            f"tier '{tier_name}' xmax",
        )

        intervals_count_line, intervals_count_no = reader.next_nonempty(
            f"reading interval count for tier '{tier_name}'"
        )
        interval_count = _parse_int_token(
            intervals_count_line,
            source_label,
            intervals_count_no,
            f"interval count for tier '{tier_name}'",
        )
        if interval_count < 0:
            raise ValueError(
                f"{source_label}: line {intervals_count_no}: interval count must be >= 0"
            )

        intervals = []
        for interval_index in range(1, interval_count + 1):
            int_start_line, int_start_no = reader.next_nonempty(
                f"reading xmin for interval #{interval_index} in tier '{tier_name}'"
            )
            int_end_line, int_end_no = reader.next_nonempty(
                f"reading xmax for interval #{interval_index} in tier '{tier_name}'"
            )
            text_line, text_no = reader.next_nonempty(
                f"reading text for interval #{interval_index} in tier '{tier_name}'"
            )

            start = _parse_float_token(
                int_start_line,
                source_label,
                int_start_no,
                f"interval xmin in tier '{tier_name}'",
            )
            end = _parse_float_token(
                int_end_line,
                source_label,
                int_end_no,
                f"interval xmax in tier '{tier_name}'",
            )
            if end < start:
                raise ValueError(
                    f"{source_label}: line {int_end_no}: interval xmax < xmin in tier '{tier_name}'"
                )

            text = _parse_short_string_or_bare(
                text_line,
                source_label,
                text_no,
                f"interval text in tier '{tier_name}'",
            )

            intervals.append({"start": start, "end": end, "text": text})

        tiers.append(
            {
                "name": tier_name,
                "class": tier_class,
                "xmin": tier_xmin,
                "xmax": tier_xmax,
                "intervals": intervals,
            }
        )

    return {"xmin": xmin, "xmax": xmax, "tiers": tiers}


def _parse_textgrid_content(content: str, source_label: str) -> dict:
    lines = content.splitlines()
    if not lines:
        raise ValueError(f"{source_label}: empty file")

    first_line = lines[0].lstrip("\ufeff").strip()
    if first_line == "":
        for candidate in lines[1:]:
            candidate_stripped = candidate.strip()
            if candidate_stripped:
                first_line = candidate_stripped
                break

    parse_short_first = "short" in first_line.lower()

    if parse_short_first:
        try:
            return _parse_short_textgrid(lines, source_label)
        except ValueError as short_error:
            try:
                return _parse_long_textgrid(lines, source_label)
            except ValueError as long_error:
                raise ValueError(
                    f"{source_label}: failed to parse short TextGrid ({short_error}); long parse also failed ({long_error})"
                ) from long_error

    try:
        return _parse_long_textgrid(lines, source_label)
    except ValueError as long_error:
        try:
            return _parse_short_textgrid(lines, source_label)
        except ValueError as short_error:
            raise ValueError(
                f"{source_label}: failed to parse long TextGrid ({long_error}); short parse also failed ({short_error})"
            ) from short_error


def _parsed_textgrid_to_schema(parsed: dict, source_label: str) -> dict:
    duration = _coerce_float(parsed.get("xmax"), f"{source_label}: xmax")
    if duration < 0:
        raise ValueError(f"{source_label}: xmax must be >= 0")

    tiers_value = parsed.get("tiers")
    if not isinstance(tiers_value, list):
        raise ValueError(f"{source_label}: malformed parser output (tiers must be a list)")

    tiers_out = {}
    for index, tier in enumerate(tiers_value, start=1):
        if not isinstance(tier, dict):
            raise ValueError(f"{source_label}: malformed tier entry at index {index}")

        tier_name_raw = tier.get("name")
        if not isinstance(tier_name_raw, str):
            raise ValueError(f"{source_label}: tier #{index} missing valid name")

        tier_name = _normalize_tier_name(tier_name_raw)
        if tier_name == "":
            raise ValueError(f"{source_label}: tier #{index} has empty name")
        if tier_name in tiers_out:
            raise ValueError(
                f"{source_label}: duplicate tier name after normalization: {tier_name!r}"
            )

        canonical_key = _canonical_annotation_key(tier_name_raw)
        if canonical_key is not None:
            display_order = _CANONICAL_DISPLAY_ORDERS[canonical_key]
        else:
            display_order = index

        intervals = _normalize_intervals(
            tier.get("intervals", []),
            f"{source_label}: tier '{tier_name}'",
        )
        tiers_out[tier_name] = {
            "type": "interval",
            "display_order": display_order,
            "intervals": intervals,
        }

    return {
        "duration_sec": float(duration),
        "tiers": tiers_out,
    }


def _read_textgrid_from_content(content: str, source_label: str) -> dict:
    parsed = _parse_textgrid_content(content, source_label)
    return _parsed_textgrid_to_schema(parsed, source_label)


def read_textgrid(path: Path) -> dict:
    """
    Parse a .TextGrid file (long or short format).

    Returns dict with duration_sec and tiers keyed by normalized tier name.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Failed to read TextGrid file '{path}': {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"TextGrid file '{path}' is not valid UTF-8: {exc}") from exc

    return _read_textgrid_from_content(content, str(path))


def annotations_to_textgrid_str(annotation_data: dict, speaker: str) -> str:
    """
    Serialize annotation data to a Praat TextGrid long-format string.

    Only interval tiers are written. Tiers are sorted by display_order, and gaps
    are filled with empty intervals.
    """
    if not isinstance(annotation_data, dict):
        raise ValueError("annotation_data must be an object")
    if not isinstance(speaker, str) or speaker.strip() == "":
        raise ValueError("speaker must be a non-empty string")

    tiers_value = annotation_data.get("tiers")
    if not isinstance(tiers_value, dict):
        raise ValueError("annotation_data['tiers'] must be an object")

    collected_tiers = []
    max_end = 0.0

    for tier_name, tier_data in tiers_value.items():
        if not isinstance(tier_name, str):
            raise ValueError("tier names must be strings")
        if not isinstance(tier_data, dict):
            raise ValueError(f"tier '{tier_name}' must be an object")

        tier_type = tier_data.get("type", "interval")
        if tier_type != "interval":
            continue

        intervals = _normalize_intervals(
            tier_data.get("intervals", []),
            f"annotation tier '{tier_name}'",
        )
        for interval in intervals:
            if interval["end"] > max_end:
                max_end = interval["end"]

        display_order = _coerce_display_order(
            tier_data.get("display_order"),
            default_order=9999,
            context=f"tier '{tier_name}' display_order",
        )
        textgrid_name = _annotation_tier_to_textgrid_name(tier_name)
        if textgrid_name.strip() == "":
            raise ValueError(f"tier '{tier_name}' resolves to an empty TextGrid name")

        collected_tiers.append(
            {
                "name": textgrid_name,
                "display_order": display_order,
                "intervals": intervals,
            }
        )

    collected_tiers.sort(key=lambda tier: (tier["display_order"], tier["name"].lower()))

    seen_names = set()
    for tier in collected_tiers:
        name = tier["name"]
        if name in seen_names:
            raise ValueError(
                f"Duplicate TextGrid tier name after normalization: {name!r}"
            )
        seen_names.add(name)

    if "source_audio_duration_sec" in annotation_data:
        duration = _coerce_float(
            annotation_data["source_audio_duration_sec"],
            "annotation_data['source_audio_duration_sec']",
        )
    elif "duration_sec" in annotation_data:
        duration = _coerce_float(
            annotation_data["duration_sec"],
            "annotation_data['duration_sec']",
        )
    else:
        duration = 0.0

    if duration < 0:
        raise ValueError("duration must be >= 0")
    if max_end > duration:
        duration = max_end

    lines = [
        'File type = "ooTextFile"',
        'Object class = "TextGrid"',
        "",
        f"xmin = {_float_to_textgrid_number(0.0)}",
        f"xmax = {_float_to_textgrid_number(duration)}",
        "tiers? <exists>",
        f"size = {len(collected_tiers)}",
        "item []:",
    ]

    for tier_idx, tier in enumerate(collected_tiers, start=1):
        tier_name = tier["name"]
        filled_intervals = _fill_interval_gaps(tier["intervals"], duration)

        lines.extend(
            [
                f"    item [{tier_idx}]:",
                '        class = "IntervalTier"',
                f"        name = {_quote_textgrid_string(tier_name)}",
                f"        xmin = {_float_to_textgrid_number(0.0)}",
                f"        xmax = {_float_to_textgrid_number(duration)}",
                f"        intervals: size = {len(filled_intervals)}",
            ]
        )

        for interval_idx, interval in enumerate(filled_intervals, start=1):
            lines.extend(
                [
                    f"        intervals [{interval_idx}]:",
                    f"            xmin = {_float_to_textgrid_number(interval['start'])}",
                    f"            xmax = {_float_to_textgrid_number(interval['end'])}",
                    f"            text = {_quote_textgrid_string(interval['text'])}",
                ]
            )

    return "\n".join(lines) + "\n"


def write_textgrid(annotation_data: dict, path: Path, speaker: str) -> None:
    """
    Write annotation data to Praat TextGrid long format.

    Only interval tiers are written. Tiers are sorted by display_order.
    Empty interval gaps are filled automatically.
    """
    textgrid_str = annotations_to_textgrid_str(annotation_data, speaker)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textgrid_str, encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Failed to write TextGrid '{path}': {exc}") from exc


def textgrid_to_annotations(
    textgrid_data: dict,
    speaker: str,
    project_id: str,
    source_audio: str,
) -> dict:
    """
    Convert parsed TextGrid tier data to full PARSE annotation file schema.

    Tier names are matched case-insensitively to Phones/IPA/Ortho/STT/Concept/Sentence/Speaker.
    Unknown tiers are preserved using their original names.
    """
    if not isinstance(textgrid_data, dict):
        raise ValueError("textgrid_data must be an object")
    if not isinstance(speaker, str) or speaker.strip() == "":
        raise ValueError("speaker must be a non-empty string")
    if not isinstance(project_id, str) or project_id.strip() == "":
        raise ValueError("project_id must be a non-empty string")
    if not isinstance(source_audio, str):
        raise ValueError("source_audio must be a string")

    duration = _coerce_float(textgrid_data.get("duration_sec"), "textgrid_data['duration_sec']")
    if duration < 0:
        raise ValueError("textgrid_data['duration_sec'] must be >= 0")

    tiers_value = textgrid_data.get("tiers")
    if not isinstance(tiers_value, dict):
        raise ValueError("textgrid_data['tiers'] must be an object")

    tiers_out = {
        name: {"type": "interval", "display_order": order, "intervals": []}
        for name, order in _CANONICAL_DISPLAY_ORDERS.items()
    }

    seen_canonical = set()
    next_custom_display_order = max(_CANONICAL_DISPLAY_ORDERS.values()) + 1

    for tier_name, tier_data in tiers_value.items():
        if not isinstance(tier_name, str):
            raise ValueError("textgrid_data tier names must be strings")
        if not isinstance(tier_data, dict):
            raise ValueError(f"tier '{tier_name}' must be an object")

        intervals = _normalize_intervals(
            tier_data.get("intervals", []),
            f"textgrid_data tier '{tier_name}'",
        )

        canonical_key = _canonical_annotation_key(tier_name)
        if canonical_key is not None:
            if canonical_key in seen_canonical:
                raise ValueError(
                    f"Duplicate canonical tier in TextGrid data: {canonical_key!r}"
                )
            tiers_out[canonical_key] = {
                "type": "interval",
                "display_order": _CANONICAL_DISPLAY_ORDERS[canonical_key],
                "intervals": intervals,
            }
            seen_canonical.add(canonical_key)
            continue

        display_order = _coerce_display_order(
            tier_data.get("display_order"),
            default_order=next_custom_display_order,
            context=f"tier '{tier_name}' display_order",
        )
        if display_order >= next_custom_display_order:
            next_custom_display_order = display_order + 1

        if tier_name in tiers_out:
            raise ValueError(
                f"Custom tier name collides with canonical tier: {tier_name!r}"
            )

        tiers_out[tier_name] = {
            "type": "interval",
            "display_order": display_order,
            "intervals": intervals,
        }

    now_iso = (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    return {
        "version": 1,
        "project_id": project_id,
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": duration,
        "tiers": tiers_out,
        "metadata": {
            "language_code": "und",
            "created": now_iso,
            "modified": now_iso,
        },
    }


def _load_json_file(path: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Failed to read JSON file '{path}': {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"JSON file '{path}' is not valid UTF-8: {exc}") from exc

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"JSON root in '{path}' must be an object")
    return data


def _run_cli_read(input_path: Path) -> None:
    data = read_textgrid(input_path)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _run_cli_write(input_path: Path, output_path: Path, speaker: str) -> None:
    annotation_data = _load_json_file(input_path)
    write_textgrid(annotation_data, output_path, speaker)
    print(f"OK: wrote {output_path}")


def _run_cli_roundtrip(
    input_path: Path,
    speaker: str | None,
    project_id: str,
    source_audio: str,
) -> None:
    parsed = read_textgrid(input_path)
    resolved_speaker = speaker if speaker else input_path.stem
    annotations = textgrid_to_annotations(
        parsed,
        speaker=resolved_speaker,
        project_id=project_id,
        source_audio=source_audio,
    )
    serialized = annotations_to_textgrid_str(annotations, resolved_speaker)
    reparsed = _read_textgrid_from_content(serialized, "<roundtrip>")

    output = {
        "input": parsed,
        "roundtrip": reparsed,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textgrid_io.py",
        description="Praat TextGrid bidirectional I/O for PARSE.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read", help="Read TextGrid and dump JSON")
    read_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to input .TextGrid",
    )

    write_parser = subparsers.add_parser(
        "write", help="Convert annotation JSON to TextGrid"
    )
    write_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to PARSE annotation JSON",
    )
    write_parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to output .TextGrid",
    )
    write_parser.add_argument(
        "--speaker",
        required=True,
        help="Speaker ID (used by exporter)",
    )

    roundtrip_parser = subparsers.add_parser(
        "roundtrip", help="Read, convert, re-serialize, and parse again"
    )
    roundtrip_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to input .TextGrid",
    )
    roundtrip_parser.add_argument(
        "--speaker",
        default=None,
        help="Speaker ID override (defaults to input filename stem)",
    )
    roundtrip_parser.add_argument(
        "--project-id",
        default="parse-roundtrip",
        help="Project ID used for generated annotation JSON",
    )
    roundtrip_parser.add_argument(
        "--source-audio",
        default="",
        help="Source audio path used for generated annotation JSON",
    )

    return parser


def main() -> None:
    parser = _build_cli_parser()
    args = parser.parse_args()

    try:
        if args.command == "read":
            _run_cli_read(args.input)
        elif args.command == "write":
            _run_cli_write(args.input, args.output, args.speaker)
        elif args.command == "roundtrip":
            _run_cli_roundtrip(
                input_path=args.input,
                speaker=args.speaker,
                project_id=args.project_id,
                source_audio=args.source_audio,
            )
        else:
            parser.error(f"Unknown command: {args.command}")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
