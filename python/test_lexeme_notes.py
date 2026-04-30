"""Regression tests for Adobe Audition lexeme-note CSV parsing."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lexeme_notes import _parse_time, parse_audition_csv


def test_parse_audition_csv_accepts_hierarchical_and_plain_integer_prefixes() -> None:
    csv_text = (
        "\ufeffName\tStart\tDuration\tTime Format\tType\tDescription\n"
        "(8.4)- to listen to\t2:48:11.681\t0:00.993\tdecimal\tCue\t\n"
        "9- nine\t20:12.776\t0:00.967\tdecimal\tCue\t\n"
        "32- hair B\t0:01.000\t0:00.500\tdecimal\tCue\t\n"
        "(2.13)- paternal uncle's son\t0:02.000\t0:00.500\tdecimal\tCue\t\n"
    )

    rows = parse_audition_csv(csv_text)

    assert [(row.concept_id, row.remainder, row.variant) for row in rows] == [
        ("8.4", "to listen to", ""),
        ("9", "nine", ""),
        ("32", "hair", "B"),
        ("2.13", "paternal uncle's son", ""),
    ]
    assert rows[0].start_sec == pytest.approx(10091.681)
    assert rows[1].start_sec == pytest.approx(1212.776)


def test_parse_audition_csv_accepts_bracket_prefixes_and_bare_names() -> None:
    csv_text = (
        "Name\tStart\tDuration\tTime Format\tType\tDescription\n"
        "[5.1]- The boy cut the rope\t0:01.000\t0:00.500\tdecimal\tCue\t\n"
        "[5.22]- Sahar was coming down the mountain with the mule A\t0:02.000\t0:00.500\tdecimal\tCue\t\n"
        "He saw me\t0:03.000\t0:00.500\tdecimal\tCue\t\n"
        "(2.29- child of one's son)-\t0:04.000\t0:00.500\tdecimal\tCue\t\n"
    )

    rows = parse_audition_csv(csv_text)

    assert [(row.concept_id, row.remainder, row.variant, row.raw_name) for row in rows] == [
        ("5.1", "The boy cut the rope", "", "[5.1]- The boy cut the rope"),
        (
            "5.22",
            "Sahar was coming down the mountain with the mule",
            "A",
            "[5.22]- Sahar was coming down the mountain with the mule A",
        ),
        ("", "He saw me", "", "He saw me"),
        ("", "(2.29- child of one's son)-", "", "(2.29- child of one's son)-"),
    ]


def test_parse_time_accepts_hms_minutes_seconds_and_plain_seconds() -> None:
    assert _parse_time("2:48:11.681") == pytest.approx(10091.681)
    assert _parse_time("20:12.776") == pytest.approx(1212.776)
    assert _parse_time("30.105") == pytest.approx(30.105)
