"""Regression coverage for annotation interval normalization metadata."""
from __future__ import annotations

import csv
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server
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


def _write_concepts_csv(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerows(rows)


def _read_concepts_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _record_with_tiers(tiers: dict[str, object]) -> dict[str, object]:
    return {
        "speaker": "Khan01",
        "source_audio": "audio/working/Khan01.wav",
        "source_audio_duration_sec": 5.0,
        "metadata": {"language_code": "sdh"},
        "tiers": tiers,
    }


def test_normalizer_backfills_concept_id_when_label_matches_existing(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts_csv(concepts_path, [{"id": "2", "concept_en": "Forehead"}])
    before_mtime = concepts_path.stat().st_mtime_ns
    time.sleep(0.01)

    normalized = _normalize_annotation_record(
        _record_with_tiers(
            {
                "concept": {
                    "type": "interval",
                    "intervals": [{"start": 0.0, "end": 1.0, "text": "  FOREHEAD  "}],
                }
            }
        ),
        "Khan01",
    )

    interval = normalized["tiers"]["concept"]["intervals"][0]
    assert interval["concept_id"] == "2"
    assert concepts_path.stat().st_mtime_ns == before_mtime
    assert _read_concepts_csv(concepts_path) == [{"id": "2", "concept_en": "Forehead"}]


def test_normalizer_allocates_new_concept_id_when_label_unknown_and_grows_concepts_csv(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts_csv(
        concepts_path,
        [
            {"id": "2", "concept_en": "forehead"},
            {"id": "225", "concept_en": "nine"},
        ],
    )

    normalized = _normalize_annotation_record(
        _record_with_tiers(
            {
                "concept": {
                    "type": "interval",
                    "intervals": [{"start": 0.0, "end": 1.0, "text": "to listen to"}],
                }
            }
        ),
        "Khan01",
    )

    interval = normalized["tiers"]["concept"]["intervals"][0]
    assert interval["concept_id"] == "226"
    assert _read_concepts_csv(concepts_path) == [
        {"id": "2", "concept_en": "forehead", "source_item": "", "source_survey": "", "custom_order": ""},
        {"id": "225", "concept_en": "nine", "source_item": "", "source_survey": "", "custom_order": ""},
        {"id": "226", "concept_en": "to listen to", "source_item": "", "source_survey": "", "custom_order": ""},
    ]


def test_normalizer_leaves_existing_concept_id_untouched(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts_csv(concepts_path, [{"id": "2", "concept_en": "forehead"}])

    normalized = _normalize_annotation_record(
        _record_with_tiers(
            {
                "concept": {
                    "type": "interval",
                    "intervals": [
                        {"start": 0.0, "end": 1.0, "text": "unknown new label", "concept_id": "900"}
                    ],
                }
            }
        ),
        "Khan01",
    )

    interval = normalized["tiers"]["concept"]["intervals"][0]
    assert interval["concept_id"] == "900"
    assert _read_concepts_csv(concepts_path) == [{"id": "2", "concept_en": "forehead"}]


def test_normalizer_logs_warning_for_concept_interval_with_empty_text_and_leaves_id_empty(
    tmp_path: pathlib.Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    normalized = _normalize_annotation_record(
        _record_with_tiers(
            {
                "concept": {
                    "type": "interval",
                    "intervals": [{"start": 0.0, "end": 1.0, "text": "   ", "concept_id": ""}],
                }
            }
        ),
        "Khan01",
    )

    interval = normalized["tiers"]["concept"]["intervals"][0]
    assert interval.get("concept_id", "") == ""
    captured = capsys.readouterr()
    assert "Khan01 concept-tier interval 0 has empty text" in captured.err
    assert "concept_id left blank" in captured.err
    assert not (tmp_path / "concepts.csv").exists()


def test_normalizer_does_not_touch_ipa_or_ortho_or_ortho_words_tier_concept_ids(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts_csv(concepts_path, [{"id": "2", "concept_en": "forehead"}])

    normalized = _normalize_annotation_record(
        _record_with_tiers(
            {
                "concept": {"type": "interval", "intervals": []},
                "ipa": {
                    "type": "interval",
                    "intervals": [{"start": 0.0, "end": 1.0, "text": "forehead", "concept_id": ""}],
                },
                "ortho": {
                    "type": "interval",
                    "intervals": [{"start": 1.0, "end": 2.0, "text": "new label", "concept_id": ""}],
                },
                "ortho_words": {
                    "type": "interval",
                    "intervals": [{"start": 2.0, "end": 3.0, "text": "new label"}],
                },
            }
        ),
        "Khan01",
    )

    assert normalized["tiers"]["ipa"]["intervals"][0]["concept_id"] == ""
    assert normalized["tiers"]["ortho"]["intervals"][0]["concept_id"] == ""
    assert "concept_id" not in normalized["tiers"]["ortho_words"]["intervals"][0]
    assert _read_concepts_csv(concepts_path) == [{"id": "2", "concept_en": "forehead"}]
