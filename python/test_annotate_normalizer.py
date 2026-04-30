"""Regression coverage for annotation interval normalization metadata."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from server import _annotation_normalize_interval, _normalize_annotation_record


def test_normalize_interval_preserves_explicit_trace_metadata_fields() -> None:
    raw = {
        "start": "1.25",
        "end": "2.5",
        "text": "1: to listen",
        "manuallyAdjusted": True,
        "concept_id": 17,
        "import_index": "4",
        "audition_prefix": 8.4,
        "conceptId": "legacy-17",
        "source": "concept_window_ipa",
    }

    normalized = _annotation_normalize_interval(raw)

    assert normalized == {
        "start": 1.25,
        "end": 2.5,
        "text": "1: to listen",
        "manuallyAdjusted": True,
        "concept_id": "17",
        "import_index": 4,
        "audition_prefix": "8.4",
        "conceptId": "legacy-17",
        "source": "concept_window_ipa",
    }


def test_normalize_interval_drops_only_bad_import_index() -> None:
    raw = {
        "start": 1.0,
        "end": 2.0,
        "text": "bad row index still keeps trace ids",
        "concept_id": "42",
        "import_index": "not-an-int",
        "audition_prefix": "32",
        "conceptId": "legacy-42",
        "source": "concept_window_ipa",
    }

    normalized = _annotation_normalize_interval(raw)

    assert normalized is not None
    assert normalized["concept_id"] == "42"
    assert normalized["audition_prefix"] == "32"
    assert normalized["conceptId"] == "legacy-42"
    assert normalized["source"] == "concept_window_ipa"
    assert "import_index" not in normalized


def test_normalize_interval_drops_unknown_fields() -> None:
    raw = {
        "start": 1.0,
        "end": 2.0,
        "text": "whitelist remains closed",
        "concept_id": "99",
        "import_index": 3,
        "audition_prefix": "row_3",
        "garbage": "must not pass through",
        "client_only": {"nested": True},
    }

    normalized = _annotation_normalize_interval(raw)

    assert normalized is not None
    assert normalized["concept_id"] == "99"
    assert normalized["import_index"] == 3
    assert normalized["audition_prefix"] == "row_3"
    assert "garbage" not in normalized
    assert "client_only" not in normalized


def test_normalize_annotation_record_preserves_trace_metadata_across_round_trip() -> None:
    # PR #200/#201/#203 rely on these explicit fields so the frontend can join
    # concept rows to Audition-imported intervals by concept_id/import_index
    # instead of by start-sorted array position.
    payload = {
        "speaker": "Fail02",
        "source_audio": "audio/working/Fail02.wav",
        "source_audio_duration_sec": 5.0,
        "metadata": {"language_code": "sdh"},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": [
                    {
                        "start": 2.0,
                        "end": 2.5,
                        "text": "2: water",
                        "concept_id": 2,
                        "import_index": "7",
                        "audition_prefix": 9,
                        "conceptId": "legacy-2",
                        "source": "concept_window_ipa",
                        "garbage": "drop me",
                    },
                    {
                        "start": 1.0,
                        "end": 1.5,
                        "text": "1: stone",
                        "concept_id": "1",
                        "import_index": 6,
                        "audition_prefix": "8.4",
                        "conceptId": "legacy-1",
                        "source": "concept_window_ipa",
                    },
                ],
            }
        },
    }

    saved = _normalize_annotation_record(payload, "Fail02")
    reloaded = _normalize_annotation_record(saved, "Fail02")

    intervals_by_text = {
        interval["text"]: interval
        for interval in reloaded["tiers"]["concept"]["intervals"]
    }
    water = intervals_by_text["2: water"]
    stone = intervals_by_text["1: stone"]

    assert water["concept_id"] == "2"
    assert water["import_index"] == 7
    assert water["audition_prefix"] == "9"
    assert water["conceptId"] == "legacy-2"
    assert water["source"] == "concept_window_ipa"
    assert "garbage" not in water

    assert stone["concept_id"] == "1"
    assert stone["import_index"] == 6
    assert stone["audition_prefix"] == "8.4"
    assert stone["conceptId"] == "legacy-1"
    assert stone["source"] == "concept_window_ipa"
