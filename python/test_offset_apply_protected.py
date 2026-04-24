"""Tests for the ``manuallyAdjusted`` protection flag.

When the annotator flags a lexeme as manually adjusted — either by editing
its start/end directly or by capturing an offset anchor pair for it — a
subsequent global offset apply must leave that lexeme in place. Covers
both the server's ``_annotation_shift_intervals`` helper (driving the
``/api/offset/apply`` endpoint) and the agent-side
``ParseChatTools._shift_annotation_intervals`` used by ``apply_timestamp_offset``.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai.chat_tools import ParseChatTools
from server import _annotation_normalize_interval, _annotation_shift_intervals


def _record_with_two_lexemes(flags: tuple[bool, bool]):
    """Build a minimal record with two concept-tier lexemes; ``flags``
    controls ``manuallyAdjusted`` on each."""
    intervals = []
    for idx, (start, text, flag) in enumerate(
        [(10.0, "STONE", flags[0]), (20.0, "WATER", flags[1])]
    ):
        iv = {"start": start, "end": start + 0.5, "text": text}
        if flag:
            iv["manuallyAdjusted"] = True
        intervals.append(iv)
    return {
        "speaker": "Test01",
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": intervals,
            }
        },
    }


def test_shift_intervals_skips_manually_adjusted_intervals() -> None:
    record = _record_with_two_lexemes((True, False))

    shifted, protected_ = _annotation_shift_intervals(record, 5.0)

    assert shifted == 1
    assert protected_ == 1

    concept = record["tiers"]["concept"]["intervals"]
    by_text = {iv["text"]: iv for iv in concept}
    # STONE was locked — stays put.
    assert by_text["STONE"]["start"] == 10.0
    assert by_text["STONE"]["end"] == 10.5
    assert by_text["STONE"]["manuallyAdjusted"] is True
    # WATER shifts by +5s.
    assert by_text["WATER"]["start"] == 25.0
    assert by_text["WATER"]["end"] == 25.5


def test_shift_intervals_returns_zero_zero_for_empty_record() -> None:
    shifted, protected_ = _annotation_shift_intervals({}, 1.0)
    assert shifted == 0
    assert protected_ == 0


def test_shift_intervals_all_protected_shifts_nothing() -> None:
    record = _record_with_two_lexemes((True, True))

    shifted, protected_ = _annotation_shift_intervals(record, -3.0)

    assert shifted == 0
    assert protected_ == 2
    # Both intervals kept their original timing.
    concept = record["tiers"]["concept"]["intervals"]
    starts = sorted(iv["start"] for iv in concept)
    assert starts == [10.0, 20.0]


def test_normalize_interval_preserves_manually_adjusted_flag() -> None:
    raw = {"start": 1.0, "end": 2.0, "text": "x", "manuallyAdjusted": True}
    normalized = _annotation_normalize_interval(raw)
    assert normalized is not None
    assert normalized["manuallyAdjusted"] is True


def test_normalize_interval_always_emits_flag_as_bool() -> None:
    # Absent key → explicit False so every interval has the same shape on
    # disk (see server._annotation_normalize_interval).
    absent = _annotation_normalize_interval({"start": 1.0, "end": 2.0, "text": "x"})
    assert absent is not None
    assert absent["manuallyAdjusted"] is False

    explicit_false = _annotation_normalize_interval(
        {"start": 1.0, "end": 2.0, "text": "x", "manuallyAdjusted": False}
    )
    assert explicit_false is not None
    assert explicit_false["manuallyAdjusted"] is False


def _write_speaker_with_lexemes(tmp_path, intervals):
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    record = {
        "speaker": "Test01",
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": intervals,
            }
        },
    }
    (annotations_dir / "Test01.parse.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    return annotations_dir / "Test01.parse.json"


def test_chat_tools_apply_offset_skips_manually_adjusted(tmp_path) -> None:
    intervals = [
        {"start": 10.0, "end": 10.5, "text": "STONE", "manuallyAdjusted": True},
        {"start": 20.0, "end": 20.5, "text": "WATER"},
    ]
    path = _write_speaker_with_lexemes(tmp_path, intervals)
    tools = ParseChatTools(project_root=tmp_path)

    out = tools.execute(
        "apply_timestamp_offset",
        {"speaker": "Test01", "offsetSec": 5.0, "dryRun": False},
    )["result"]

    assert out["shiftedIntervals"] == 1

    persisted = json.loads(path.read_text(encoding="utf-8"))
    by_text = {iv["text"]: iv for iv in persisted["tiers"]["concept"]["intervals"]}
    assert by_text["STONE"]["start"] == 10.0
    assert by_text["STONE"]["manuallyAdjusted"] is True
    assert by_text["WATER"]["start"] == 25.0
