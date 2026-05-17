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
        iv = {
            "start": start,
            "end": start + 0.5,
            "text": text,
            "imported_csv_start": start,
            "imported_csv_end": start + 0.5,
        }
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

    shifted, protected_, shifted_concepts = _annotation_shift_intervals(record, 5.0)

    assert shifted == 1
    assert protected_ == 1
    assert shifted_concepts == 1

    concept = record["tiers"]["concept"]["intervals"]
    by_text = {iv["text"]: iv for iv in concept}
    # STONE was locked — stays put.
    assert by_text["STONE"]["start"] == 10.0
    assert by_text["STONE"]["end"] == 10.5
    assert by_text["STONE"]["manuallyAdjusted"] is True
    # WATER shifts to imported_csv_start + offset, while original imported CSV provenance stays pinned.
    assert by_text["WATER"]["start"] == by_text["WATER"]["imported_csv_start"] + 5.0
    assert by_text["WATER"]["end"] == by_text["WATER"]["imported_csv_end"] + 5.0
    assert by_text["WATER"]["imported_csv_start"] == 20.0
    assert by_text["WATER"]["imported_csv_end"] == 20.5



def _interval(start: float, text: str, concept_id: str, *, imported: bool = True, protected: bool = False):
    item = {
        "start": start,
        "end": start + 0.5,
        "text": text,
        "concept_id": concept_id,
    }
    if imported:
        item["imported_csv_start"] = start
        item["imported_csv_end"] = start + 0.5
    if protected:
        item["manuallyAdjusted"] = True
    return item


def _multi_tier_record(*, imported: bool = True, protected: bool = False):
    return {
        "speaker": "Fail02",
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": [
                    _interval(78.0, "jbil 2", "42", imported=imported, protected=protected)
                ],
            },
            "ipa": {
                "type": "interval",
                "display_order": 1,
                "intervals": [_interval(78.0, "dʒbil", "42", imported=False)],
            },
            "ortho": {
                "type": "interval",
                "display_order": 2,
                "intervals": [_interval(78.0, "jbil", "42", imported=False)],
            },
            "ortho_words": {
                "type": "interval",
                "display_order": 3,
                "intervals": [_interval(78.0, "jbil", "42", imported=imported)],
            },
            "speaker": {
                "type": "interval",
                "display_order": 4,
                # Runtime normalization rebuilds this tier from concept timings
                # without concept_id; offset apply must still keep it aligned.
                "intervals": [{"start": 78.0, "end": 78.5, "text": "Fail02"}],
            },
        },
    }


def test_multi_apply_with_imported_csv_is_idempotent() -> None:
    record = _multi_tier_record()

    _annotation_shift_intervals(record, 339.0)
    first_round = {iv["text"]: iv for iv in record["tiers"]["concept"]["intervals"]}
    assert first_round["jbil 2"]["start"] == 417.0

    _annotation_shift_intervals(record, 422.0)
    second_round = {iv["text"]: iv for iv in record["tiers"]["concept"]["intervals"]}
    assert second_round["jbil 2"]["start"] == 500.0
    assert second_round["jbil 2"]["start"] != 839.0


def test_multi_apply_mirror_tiers_stay_aligned() -> None:
    record = _multi_tier_record()

    _annotation_shift_intervals(record, 339.0)
    _annotation_shift_intervals(record, 422.0)

    starts = {
        tier_key: record["tiers"][tier_key]["intervals"][0]["start"]
        for tier_key in ("concept", "ipa", "ortho", "ortho_words", "speaker")
    }
    assert starts == {
        "concept": 500.0,
        "ipa": 500.0,
        "ortho": 500.0,
        "ortho_words": 500.0,
        "speaker": 500.0,
    }


def test_apply_without_imported_csv_uses_incremental_fallback() -> None:
    record = _multi_tier_record(imported=False)

    _annotation_shift_intervals(record, 339.0)
    _annotation_shift_intervals(record, 422.0)

    # Intentional legacy fallback for pre-MC-410-C annotations without imported CSV provenance.
    assert record["tiers"]["concept"]["intervals"][0]["start"] == 78.0 + 339.0 + 422.0


def test_apply_does_not_mutate_imported_csv_fields() -> None:
    record = _multi_tier_record()
    before = {
        tier_key: [
            (iv.get("imported_csv_start"), iv.get("imported_csv_end"))
            for iv in tier.get("intervals", [])
        ]
        for tier_key, tier in record["tiers"].items()
    }

    _annotation_shift_intervals(record, 339.0)
    _annotation_shift_intervals(record, 422.0)

    after = {
        tier_key: [
            (iv.get("imported_csv_start"), iv.get("imported_csv_end"))
            for iv in tier.get("intervals", [])
        ]
        for tier_key, tier in record["tiers"].items()
    }
    assert after == before


def test_protected_concept_skipped_across_tiers() -> None:
    record = _multi_tier_record(protected=True)

    shifted, protected_, shifted_concepts = _annotation_shift_intervals(record, 339.0)

    assert shifted == 0
    assert protected_ == 5
    assert shifted_concepts == 0
    for tier_key in ("concept", "ipa", "ortho", "ortho_words", "speaker"):
        interval = record["tiers"][tier_key]["intervals"][0]
        assert interval["start"] == 78.0
        assert interval["end"] == 78.5


def test_shift_intervals_reports_distinct_shifted_concepts_across_tiers() -> None:
    record = {
        "speaker": "Test01",
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": [
                    {"start": 10.0, "end": 10.5, "text": "1: STONE", "concept_id": "1"},
                    {"start": 20.0, "end": 20.5, "text": "2: WATER", "concept_id": "2"},
                ],
            },
            "ortho": {
                "type": "interval",
                "display_order": 1,
                "intervals": [
                    {"start": 10.0, "end": 10.5, "text": "berd", "concept_id": "1"},
                    {"start": 20.0, "end": 20.5, "text": "aw", "concept_id": "2"},
                ],
            },
            "ipa": {
                "type": "interval",
                "display_order": 2,
                "intervals": [
                    {"start": 10.0, "end": 10.5, "text": "bɛrd", "concept_id": "1"},
                    {"start": 20.0, "end": 20.5, "text": "aw", "concept_id": "2"},
                ],
            },
        },
    }

    shifted, protected_, shifted_concepts = _annotation_shift_intervals(record, 1.0)

    assert shifted == 6
    assert protected_ == 0
    assert shifted_concepts == 2


def test_shift_intervals_returns_zero_zero_for_empty_record() -> None:
    shifted, protected_, shifted_concepts = _annotation_shift_intervals({}, 1.0)
    assert shifted == 0
    assert protected_ == 0
    assert shifted_concepts == 0


def test_shift_intervals_all_protected_shifts_nothing() -> None:
    record = _record_with_two_lexemes((True, True))

    shifted, protected_, shifted_concepts = _annotation_shift_intervals(record, -3.0)

    assert shifted == 0
    assert protected_ == 2
    assert shifted_concepts == 0
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


def test_apply_then_mark_round_trip_persists_flag(tmp_path) -> None:
    """Simulate the frontend MC-410-B sequence:
      (1) /api/offset/apply shifts every interval by offsetSec;
      (2) the client reloads, marks each surviving anchor as manuallyAdjusted
          using the post-shift positions, and POSTs the record back via
          /api/annotations/{speaker}.
    Verify the flag survives a normalize + JSON round-trip so a subsequent
    apply will treat the anchor as protected."""
    from server import _normalize_annotation_record, _read_json_file, _write_json_file

    record = {
        "speaker": "Test01",
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": [
                    {"start": 8.0, "end": 8.4, "text": "WATER"},
                    {"start": 10.0, "end": 10.4, "text": "FIRE"},
                ],
            }
        },
    }

    # (1) Backend apply: nothing flagged yet, so both shift by +2.25.
    shifted, protected_, _ = _annotation_shift_intervals(record, 2.25)
    assert shifted == 2
    assert protected_ == 0

    # Normalize once so the speaker/ipa/ortho mirror tiers exist — the real
    # /api/annotations roundtrip always sees a normalized record, and the
    # client's markLexemeManuallyAdjusted flags every tier whose interval
    # matches the (start, end) pair.
    record = _normalize_annotation_record(record, "Test01")

    # (2) Simulate the client mark loop: flag every interval (across all
    # tiers) at the post-shift anchor positions.
    anchor_positions = [(10.25, 10.65), (12.25, 12.65)]
    for tier in record["tiers"].values():
        for iv in tier.get("intervals", []):
            if any(
                abs(iv["start"] - s) < 1e-3 and abs(iv["end"] - e) < 1e-3
                for s, e in anchor_positions
            ):
                iv["manuallyAdjusted"] = True

    # POST /api/annotations/{speaker} normalizes the body, then writes JSON.
    normalized = _normalize_annotation_record(record, "Test01")
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    path = annotations_dir / "Test01.parse.json"
    _write_json_file(path, normalized)

    # GET /api/annotations/{speaker} re-reads from disk.
    reloaded = _read_json_file(path, {})
    persisted = {iv["text"]: iv for iv in reloaded["tiers"]["concept"]["intervals"]}
    assert persisted["WATER"]["start"] == 10.25
    assert persisted["WATER"]["manuallyAdjusted"] is True
    assert persisted["FIRE"]["start"] == 12.25
    assert persisted["FIRE"]["manuallyAdjusted"] is True

    # A second apply must now skip the concept-tier anchors — proving the
    # round-trip actually protected them rather than just preserving the
    # field cosmetically. (The auto-mirrored speaker tier is rebuilt from
    # concept on every save by _annotation_sync_speaker_tier and does not
    # carry per-interval flags; that desync is a separate, pre-existing
    # concern outside Lane B's scope.)
    _, second_protected, _ = _annotation_shift_intervals(reloaded, 1.0)
    assert second_protected >= 2
    concept_after = {iv["text"]: iv for iv in reloaded["tiers"]["concept"]["intervals"]}
    assert concept_after["WATER"]["start"] == 10.25
    assert concept_after["FIRE"]["start"] == 12.25


def test_chat_tools_apply_offset_reports_distinct_shifted_concepts(tmp_path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    path = annotations_dir / "Test01.parse.json"
    path.write_text(
        json.dumps(
            {
                "speaker": "Test01",
                "tiers": {
                    "concept": {
                        "intervals": [
                            {"start": 1.0, "end": 1.5, "text": "1: ash", "concept_id": "1"},
                            {"start": 2.0, "end": 2.5, "text": "2: water", "concept_id": "2"},
                        ]
                    },
                    "ortho": {
                        "intervals": [
                            {"start": 1.0, "end": 1.5, "text": "xol", "concept_id": "1"},
                            {"start": 2.0, "end": 2.5, "text": "aw", "concept_id": "2"},
                        ]
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    tools = ParseChatTools(project_root=tmp_path)

    dry_run = tools.execute(
        "apply_timestamp_offset",
        {"speaker": "Test01", "offsetSec": 0.25, "dryRun": True},
    )["result"]
    applied = tools.execute(
        "apply_timestamp_offset",
        {"speaker": "Test01", "offsetSec": 0.25, "dryRun": False},
    )["result"]

    assert path.is_file()
    assert dry_run["wouldShiftIntervals"] == 4
    assert dry_run["wouldShiftConcepts"] == 2
    assert applied["shiftedIntervals"] == 4
    assert applied["shiftedConcepts"] == 2
