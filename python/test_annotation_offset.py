from __future__ import annotations

import copy
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai.chat_tools import ParseChatTools
from ai.tools.offset_apply_tools import _shift_annotation_intervals as _chat_shift_intervals
from annotation_offset import interval_concept_identity, shift_annotation_intervals
from server_routes.annotate import _annotation_shift_intervals as _http_shift_intervals


def _interval(
    start: float,
    text: str,
    concept_id: str,
    *,
    imported: bool = True,
    protected: bool = False,
    include_xmin: bool = False,
) -> dict[str, Any]:
    interval: dict[str, Any] = {
        "start": start,
        "end": start + 0.5,
        "text": text,
        "concept_id": concept_id,
    }
    if imported:
        interval["imported_csv_start"] = start
        interval["imported_csv_end"] = start + 0.5
    if protected:
        interval["manuallyAdjusted"] = True
    if include_xmin:
        interval["xmin"] = start
        interval["xmax"] = start + 0.5
    return interval


def _multi_tier_record() -> dict[str, Any]:
    return {
        "speaker": "Test01",
        "metadata": {"modified": "stable"},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 0,
                "intervals": [
                    _interval(78.0, "jbil 2", "42", imported=True),
                    _interval(120.0, "locked", "77", imported=True, protected=True),
                ],
            },
            "ipa": {
                "type": "interval",
                "display_order": 1,
                "intervals": [
                    _interval(78.0, "dʒbil", "42", imported=False, include_xmin=True),
                    _interval(120.0, "lɑkt", "77", imported=False),
                ],
            },
            "ortho": {
                "type": "interval",
                "display_order": 2,
                "intervals": [
                    _interval(78.0, "jbil", "42", imported=False),
                    _interval(120.0, "locked", "77", imported=False),
                ],
            },
            "speaker": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 78.0, "end": 78.5, "text": "Test01"},
                    {"start": 120.0, "end": 120.5, "text": "Test01"},
                ],
            },
        },
    }


def _stable_record(record: dict[str, Any]) -> dict[str, Any]:
    stable = copy.deepcopy(record)
    for tier in stable.get("tiers", {}).values():
        intervals = tier.get("intervals") if isinstance(tier, dict) else None
        if isinstance(intervals, list):
            intervals.sort(
                key=lambda item: (
                    str(item.get("concept_id", "")),
                    str(item.get("text", "")),
                    float(item.get("start", item.get("xmin", 0.0))),
                    float(item.get("end", item.get("xmax", 0.0))),
                )
            )
    return stable


def test_interval_concept_identity_normalizes_known_identity_fields() -> None:
    assert interval_concept_identity("concept", {"concept_id": 42}, 0) == "42"
    assert interval_concept_identity("concept", {"conceptId": " 042 "}, 0) == "042"
    assert interval_concept_identity("concept", {"conceptKey": "abc"}, 0) == "abc"
    assert interval_concept_identity("concept", {"text": "STONE"}, 4) == "STONE"
    assert interval_concept_identity("concept", {"text": "   "}, 4) == "concept-index:4"
    assert interval_concept_identity("speaker", {"text": "Test01"}, 4) == ""


def test_shift_annotation_intervals_collects_limited_preview_and_updates_xmin_xmax() -> None:
    record = _multi_tier_record()

    result = shift_annotation_intervals(record, 300.0, collect_preview=True, preview_limit=2)

    assert result.shifted_intervals == 4
    assert result.skipped_protected == 4
    assert result.shifted_concepts == {"42"}
    assert result.preview == [
        {"tier": "concept", "from": [78.0, 78.5], "to": [378.0, 378.5], "concept_id": "42"},
        {"tier": "ipa", "from": [78.0, 78.5], "to": [378.0, 378.5], "concept_id": "42"},
    ]
    ipa = next(
        interval
        for interval in record["tiers"]["ipa"]["intervals"]
        if interval.get("concept_id") == "42"
    )
    assert ipa["start"] == 378.0
    assert ipa["end"] == 378.5
    assert ipa["xmin"] == 378.0
    assert ipa["xmax"] == 378.5


def test_shift_annotation_intervals_negative_offset_uses_absolute_imported_base() -> None:
    record = _multi_tier_record()

    shift_annotation_intervals(record, 300.0)
    result = shift_annotation_intervals(record, -20.0)

    assert result.shifted_intervals == 4
    assert result.skipped_protected == 4
    starts = {
        tier_key: record["tiers"][tier_key]["intervals"][0]["start"]
        for tier_key in ("concept", "ipa", "ortho", "speaker")
    }
    assert starts == {"concept": 58.0, "ipa": 58.0, "ortho": 58.0, "speaker": 58.0}
    locked = record["tiers"]["concept"]["intervals"][1]
    assert locked["start"] == 120.0
    assert locked["manuallyAdjusted"] is True


def test_http_and_chat_offset_paths_produce_identical_record_state() -> None:
    http_record = _multi_tier_record()
    chat_record = copy.deepcopy(http_record)

    http_shifted, http_skipped, http_concepts = _http_shift_intervals(http_record, 300.0)
    chat_shifted, chat_concepts, chat_preview = _chat_shift_intervals(chat_record, 300.0)

    assert http_shifted == chat_shifted == 4
    assert http_skipped == 4
    assert http_concepts == chat_concepts == 1
    assert chat_preview[0]["to"] == [378.0, 378.5]
    assert _stable_record(http_record) == _stable_record(chat_record)


def test_parse_chat_tools_multi_apply_converges_to_imported_plus_last_offset(tmp_path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    annotation_path = annotations_dir / "Test01.parse.json"
    annotation_path.write_text(json.dumps(_multi_tier_record()), encoding="utf-8")
    tools = ParseChatTools(project_root=tmp_path)

    tools.execute(
        "apply_timestamp_offset",
        {"speaker": "Test01", "offsetSec": 339.0, "dryRun": False},
    )
    tools.execute(
        "apply_timestamp_offset",
        {"speaker": "Test01", "offsetSec": 300.0, "dryRun": False},
    )

    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    by_text = {
        interval["text"]: interval
        for interval in persisted["tiers"]["concept"]["intervals"]
    }
    assert by_text["jbil 2"]["start"] == 378.0
    assert by_text["jbil 2"]["start"] != 78.0 + 339.0 + 300.0
    assert by_text["jbil 2"]["imported_csv_start"] == 78.0
