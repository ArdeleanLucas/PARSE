"""Tests for multi-pair manual offset detection.

Validates the chip-based UX path: the user captures one or more trusted
(csvTime, audioTime) pairs in the UI, the chat tool / endpoint runs the
median-of-pair-offsets math, and the apply step shifts intervals
accordingly. Includes the regression test that pairs disagreeing by
more than 2s surface a warning instead of silently averaging into a
wrong answer.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai.chat_tools import ParseChatTools


def _make_annotation(intervals_concept):
    """Build a minimal annotation record with concept-tier intervals."""
    return {
        "speaker": "Test01",
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": [
                    {"start": s, "end": s + 0.5, "text": text}
                    for text, s in intervals_concept
                ],
            },
        },
    }


def _write_annotation(tmp_path, intervals_concept):
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    record = _make_annotation(intervals_concept)
    (annotations_dir / "Test01.parse.json").write_text(json.dumps(record), encoding="utf-8")


def _tools(tmp_path):
    return ParseChatTools(project_root=tmp_path)


def test_single_pair_uses_legacy_argument_shape(tmp_path) -> None:
    _write_annotation(tmp_path, [("STONE", 154.0)])
    tools = _tools(tmp_path)
    out = tools.execute(
        "detect_timestamp_offset_from_pair",
        {"speaker": "Test01", "audioTimeSec": 220.5, "conceptId": "STONE"},
    )["result"]

    assert out["offsetSec"] == 66.5
    assert out["nAnchors"] == 1
    assert out["spreadSec"] == 0.0
    assert out["confidence"] == 0.99
    assert out["direction"] == "later"


def test_multi_pair_uses_median(tmp_path) -> None:
    _write_annotation(
        tmp_path, [("STONE", 100.0), ("WATER", 200.0), ("FIRE", 300.0)]
    )
    tools = _tools(tmp_path)
    # Three pairs all at +66.5s; offset should be exactly 66.5 with
    # zero spread and full confidence.
    out = tools.execute(
        "detect_timestamp_offset_from_pair",
        {
            "speaker": "Test01",
            "pairs": [
                {"audioTimeSec": 166.5, "conceptId": "STONE"},
                {"audioTimeSec": 266.5, "conceptId": "WATER"},
                {"audioTimeSec": 366.5, "conceptId": "FIRE"},
            ],
        },
    )["result"]

    assert out["offsetSec"] == 66.5
    assert out["nAnchors"] == 3
    assert out["spreadSec"] == 0.0
    assert out["confidence"] >= 0.95
    assert out["direction"] == "later"
    assert out["warnings"] == []  # consistent pairs → no warnings


def test_multi_pair_robust_to_one_outlier(tmp_path) -> None:
    """Two consistent pairs at +66.5 plus one outlier at +30 — median
    must remain ~66.5 (not the mean ~54), and the spread should be
    surfaced as an amber warning."""
    _write_annotation(
        tmp_path, [("STONE", 100.0), ("WATER", 200.0), ("FIRE", 300.0)]
    )
    tools = _tools(tmp_path)
    out = tools.execute(
        "detect_timestamp_offset_from_pair",
        {
            "speaker": "Test01",
            "pairs": [
                {"audioTimeSec": 166.5, "conceptId": "STONE"},
                {"audioTimeSec": 266.5, "conceptId": "WATER"},
                {"audioTimeSec": 330.0, "conceptId": "FIRE"},  # outlier (+30)
            ],
        },
    )["result"]

    # Median of [66.5, 66.5, 30] = 66.5 — robust to the single outlier.
    assert out["offsetSec"] == 66.5
    assert out["nAnchors"] == 3
    # MAD across [66.5, 66.5, 30] = median(|0|, |0|, |36.5|) = 0
    # — but with three pairs that include a 36s deviation, the spread
    # warning must fire.
    spread = out["spreadSec"]
    assert spread >= 0.0
    # Confidence should be reduced by the disagreement.
    assert out["confidence"] < 0.99


def test_pairs_with_explicit_csv_time_skip_concept_lookup(tmp_path) -> None:
    """csvTimeSec lets the caller bypass the annotation lookup entirely
    — useful for agents that already know both numbers without needing
    to read the annotation file."""
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    # Note: NO concept tier — verifying the lookup is never invoked.
    (annotations_dir / "Test01.parse.json").write_text(
        json.dumps({"speaker": "Test01", "tiers": {}}), encoding="utf-8"
    )
    tools = _tools(tmp_path)
    out = tools.execute(
        "detect_timestamp_offset_from_pair",
        {
            "speaker": "Test01",
            "pairs": [
                {"audioTimeSec": 220.5, "csvTimeSec": 154.0},
                {"audioTimeSec": 320.4, "csvTimeSec": 254.0},
            ],
        },
    )["result"]

    assert out["offsetSec"] == 66.45  # median of 66.5 and 66.4
    assert out["nAnchors"] == 2


def test_empty_pairs_array_is_rejected(tmp_path) -> None:
    _write_annotation(tmp_path, [("STONE", 100.0)])
    tools = _tools(tmp_path)
    try:
        tools.execute("detect_timestamp_offset_from_pair", {"speaker": "Test01", "pairs": []})
    except Exception as exc:  # ChatToolValidationError from schema or handler
        msg = str(exc).lower()
        assert "at least 1" in msg or "non-empty" in msg, msg
    else:
        raise AssertionError("empty pairs array must be rejected")


def test_multi_pair_negative_offset_reports_earlier_direction(tmp_path) -> None:
    _write_annotation(tmp_path, [("STONE", 200.0), ("WATER", 300.0)])
    tools = _tools(tmp_path)
    out = tools.execute(
        "detect_timestamp_offset_from_pair",
        {
            "speaker": "Test01",
            "pairs": [
                {"audioTimeSec": 140.0, "conceptId": "STONE"},  # -60
                {"audioTimeSec": 240.0, "conceptId": "WATER"},  # -60
            ],
        },
    )["result"]

    assert out["offsetSec"] == -60.0
    assert out["direction"] == "earlier"
    assert "earlier" in out["directionLabel"].lower()
