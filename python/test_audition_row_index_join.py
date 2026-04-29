"""Regression tests for Audition cue/comments row-index import-note joins."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lexeme_notes import parse_audition_csv
from server_routes import media


def _rows(names: list[str]):
    lines = ["Name\tStart\tDuration\tTime Format\tType\tDescription"]
    for index, name in enumerate(names):
        lines.append(f"{name}\t{index}\t1\tdecimal\tCue\t")
    return parse_audition_csv("\n".join(lines) + "\n")


def test_row_index_join_extracts_appended_notes_and_skips_unchanged_rows(capsys) -> None:
    cue_rows = _rows(["9- nine", "(8.4)- to listen to", "32- hair B"])
    comments_rows = _rows([
        "9- nine",
        "(8.4)- to listen to - reduced vowel",
        '32- hair B "another way of pronuncing"',
    ])
    resolved = [
        {"id": "225", "audition_prefix": "9"},
        {"id": "226", "audition_prefix": "8.4"},
        {"id": "227", "audition_prefix": "32"},
    ]

    notes = media._collect_audition_comment_notes(cue_rows, comments_rows, resolved, "cue.csv", "cue.comments.csv")

    assert notes == [
        {
            "concept_id": "226",
            "import_note": "reduced vowel",
            "import_raw": "(8.4)- to listen to - reduced vowel",
            "import_index": 1,
            "audition_prefix": "8.4",
        },
        {
            "concept_id": "227",
            "import_note": '"another way of pronuncing"',
            "import_raw": '32- hair B "another way of pronuncing"',
            "import_index": 2,
            "audition_prefix": "32",
        },
    ]
    assert capsys.readouterr().err == ""


def test_row_index_join_logs_and_skips_misaligned_prefix(capsys) -> None:
    cue_rows = _rows(["9- nine", "(8.4)- to listen to"])
    comments_rows = _rows(["9- nine analyst note", "(8.5)- to listen to analyst edited prefix"])
    resolved = [
        {"id": "225", "audition_prefix": "9"},
        {"id": "226", "audition_prefix": "8.4"},
    ]

    notes = media._collect_audition_comment_notes(cue_rows, comments_rows, resolved, "cue.csv", "cue.comments.csv")

    assert notes == [
        {
            "concept_id": "225",
            "import_note": "analyst note",
            "import_raw": "9- nine analyst note",
            "import_index": 0,
            "audition_prefix": "9",
        }
    ]
    captured = capsys.readouterr()
    assert "[audition-csv] row 1 misaligned:" in captured.err
    assert "cue=(8.4)- to listen to" in captured.err
    assert "comments=(8.5)- to listen to analyst edited prefix" in captured.err


def test_row_index_join_logs_length_mismatch_and_aborts_notes(capsys) -> None:
    cue_rows = _rows(["9- nine", "(8.4)- to listen to"])
    comments_rows = _rows(["9- nine analyst note"])
    resolved = [
        {"id": "225", "audition_prefix": "9"},
        {"id": "226", "audition_prefix": "8.4"},
    ]

    notes = media._collect_audition_comment_notes(cue_rows, comments_rows, resolved, "cue.csv", "cue.comments.csv")

    assert notes == []
    captured = capsys.readouterr()
    assert "[audition-csv] comments row count mismatch for cue.csv vs cue.comments.csv: 2 != 1" in captured.err
