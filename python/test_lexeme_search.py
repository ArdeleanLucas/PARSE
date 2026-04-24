"""Unit tests for python/ai/lexeme_search.py.

Phonemizer backend is patched out in most tests so the suite runs without
espeak-ng installed in the test environment. A dedicated test asserts
graceful degradation when phonemize_variant() returns an empty list.
"""

import json
import pathlib
import sys
from unittest import mock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import lexeme_search as lex  # noqa: E402


def _tier(name, display_order, intervals):
    return {"name": name, "display_order": display_order, "intervals": intervals}


def _record(tiers, *, speaker="Fail102", confirmed_anchors=None):
    return {
        "speaker": speaker,
        "tiers": tiers,
        "confirmed_anchors": confirmed_anchors or {},
    }


# Disable phonemizer by default so tests don't need espeak installed.
@pytest.fixture(autouse=True)
def _no_phonemizer(monkeypatch):
    monkeypatch.setattr(lex, "phonemize_variant", lambda v, language=lex.DEFAULT_LANGUAGE: [])


def test_levenshtein_basic():
    assert lex.levenshtein("yek", "yek") == 0
    assert lex.levenshtein("yek", "jek") == 1
    assert lex.levenshtein("yek", "yeke") == 1
    assert lex.levenshtein("abc", "") == 3


def test_normalized_levenshtein_scales_by_max_len():
    assert lex.normalized_levenshtein("yek", "yek") == 0.0
    assert lex.normalized_levenshtein("yek", "yak") == pytest.approx(1 / 3)


def test_normalize_strips_punct_and_collapses_whitespace():
    assert lex.normalize_for_match("Yek!") == "yek"
    assert lex.normalize_for_match("  YEK-e  ") == "yeke"
    assert lex.normalize_for_match("yek   du") == "yek du"


def test_search_returns_empty_when_no_record_or_variants():
    assert lex.search(None, ["yek"]) == []
    assert lex.search(_record({}), []) == []


def test_search_finds_exact_orth_match():
    rec = _record({
        "ortho": _tier("ortho", 3, [
            {"start": 0.0, "end": 0.5, "text": "yek"},
            {"start": 1.0, "end": 1.4, "text": "du"},
        ]),
    })
    hits = lex.search(rec, ["yek"])
    assert len(hits) >= 1
    assert hits[0]["matched_text"] == "yek"
    assert hits[0]["tier"] == "ortho"
    assert hits[0]["score"] > 0.8


def test_search_prefers_ortho_words_when_both_tiers_match():
    rec = _record({
        "ortho_words": _tier("ortho_words", 4, [
            {"start": 0.0, "end": 0.5, "text": "yek", "confidence": 0.95, "source": "forced_align"},
        ]),
        "ortho": _tier("ortho", 3, [
            {"start": 0.05, "end": 0.55, "text": "yek"},
        ]),
    })
    hits = lex.search(rec, ["yek"])
    # Dedup collapses to the higher-scoring tier; ortho_words has the greater weight.
    assert hits[0]["tier"] == "ortho_words"
    # ortho_words confidence 0.95 should be reflected in confidence_weight (clamped to [0.5, 1.0]).
    assert hits[0]["confidence_weight"] == pytest.approx(0.95, abs=1e-4)


def test_search_catches_near_misses_within_threshold():
    rec = _record({
        "ortho": _tier("ortho", 3, [{"start": 0, "end": 0.5, "text": "jek"}]),
    })
    hits = lex.search(rec, ["yek"])
    assert len(hits) == 1
    assert hits[0]["matched_variant"] == "yek"
    assert hits[0]["matched_text"] == "jek"


def test_search_respects_max_distance_threshold():
    rec = _record({
        "ortho": _tier("ortho", 3, [{"start": 0, "end": 0.5, "text": "totally different"}]),
    })
    assert lex.search(rec, ["yek"]) == []


def test_search_merges_adjacent_short_intervals_for_split_words():
    rec = _record({
        "ortho_words": _tier("ortho_words", 4, [
            {"start": 0.10, "end": 0.22, "text": "ye"},
            {"start": 0.24, "end": 0.35, "text": "k"},
        ]),
    })
    hits = lex.search(rec, ["yek"])
    merged = next((h for h in hits if h["start"] < 0.15 and h["end"] > 0.3), None)
    assert merged is not None
    assert merged["matched_text"] == "ye k"


def test_search_limits_results():
    intervals = [{"start": i, "end": i + 0.3, "text": "yek"} for i in range(20)]
    rec = _record({"ortho": _tier("ortho", 3, intervals)})
    assert len(lex.search(rec, ["yek"], limit=5)) == 5


def test_search_token_matches_first_word_of_multi_word_segment():
    rec = _record({
        "ortho": _tier("ortho", 3, [{"start": 5, "end": 6, "text": "yek dînarê"}]),
    })
    hits = lex.search(rec, ["yek"])
    assert len(hits) == 1


def test_search_adds_cross_speaker_bonus_when_other_speaker_confirmed_the_concept():
    target = _record({
        "ortho": _tier("ortho", 3, [{"start": 0, "end": 0.5, "text": "jek"}]),
    })
    # Other speaker already confirmed this concept with matched_text "yek".
    # The fuzzy match on "jek" gains a small cross-speaker bonus because the
    # cross-speaker reference also looks like "yek".
    others = [
        _record({}, speaker="Fail101", confirmed_anchors={
            "1": {"start": 10.0, "end": 10.5, "matched_text": "yek"},
        }),
    ]
    hits_with = lex.search(target, ["yek"], concept_id="1", cross_speaker_records=others)
    hits_without = lex.search(target, ["yek"], concept_id=None, cross_speaker_records=None)
    assert hits_with and hits_without
    assert hits_with[0]["score"] >= hits_without[0]["score"]
    assert hits_with[0]["cross_speaker_score"] > 0
    assert hits_without[0]["cross_speaker_score"] == 0


def test_search_cross_speaker_falls_back_to_ortho_words_when_anchor_has_no_text():
    target = _record({
        "ortho": _tier("ortho", 3, [{"start": 0, "end": 0.5, "text": "jek"}]),
    })
    others = [
        _record(
            {"ortho_words": _tier("ortho_words", 4, [
                {"start": 10.0, "end": 10.5, "text": "yek", "confidence": 0.9},
            ])},
            speaker="Fail101",
            confirmed_anchors={"1": {"start": 10.0, "end": 10.5}},  # no matched_text
        ),
    ]
    hits = lex.search(target, ["yek"], concept_id="1", cross_speaker_records=others)
    assert hits[0]["cross_speaker_score"] > 0


def test_search_respects_tiers_filter():
    rec = _record({
        "ortho_words": _tier("ortho_words", 4, [{"start": 0, "end": 0.3, "text": "yek"}]),
        "stt": _tier("stt", 5, [{"start": 0, "end": 0.3, "text": "yek"}]),
    })
    hits = lex.search(rec, ["yek"], tiers=["stt"])
    assert all(h["tier"] == "stt" for h in hits)


def test_search_dedups_near_identical_time_ranges_to_highest_score():
    rec = _record({
        "ortho_words": _tier("ortho_words", 4, [{"start": 1.0, "end": 1.5, "text": "yek"}]),
        "ortho":       _tier("ortho", 3,       [{"start": 1.001, "end": 1.501, "text": "yek"}]),
        "stt":         _tier("stt", 5,         [{"start": 1.0005, "end": 1.4995, "text": "yek"}]),
    })
    hits = lex.search(rec, ["yek"])
    assert len(hits) == 1
    assert hits[0]["tier"] == "ortho_words"


# ── load_contact_variants ────────────────────────────────────────────────

def test_load_contact_variants_handles_missing_file(tmp_path):
    missing = tmp_path / "nope.json"
    assert lex.load_contact_variants("1", missing) == []


def test_load_contact_variants_reads_mixed_schemas(tmp_path):
    path = tmp_path / "sil.json"
    path.write_text(json.dumps({
        "ar": {"name": "Arabic", "concepts": {"1": "wahid"}},
        "fa": {"name": "Persian", "concepts": {"1": ["yek", "yake"]}},
        "tr": {"name": "Turkish", "concepts": {"1": {"variants": ["bir", "bi"]}}},
    }), encoding="utf-8")
    found = lex.load_contact_variants("1", path)
    # Order is stable (dedupe preserves first-seen).
    assert found == ["wahid", "yek", "yake", "bir", "bi"]


def test_load_contact_variants_returns_empty_for_missing_concept(tmp_path):
    path = tmp_path / "sil.json"
    path.write_text(json.dumps({"ar": {"concepts": {}}}), encoding="utf-8")
    assert lex.load_contact_variants("99", path) == []


def test_load_contact_variants_tolerates_garbage(tmp_path):
    path = tmp_path / "sil.json"
    path.write_text("not json", encoding="utf-8")
    assert lex.load_contact_variants("1", path) == []


# ── phonemizer graceful degradation (no mocking needed, real call) ────────

def test_search_works_without_phonemizer_backend(monkeypatch):
    """Explicit regression guard: when phonemize_variant returns [] (espeak
    not installed / unsupported language / import error), the scorer must
    still surface orthographic matches instead of crashing or returning no
    results. This is what callers see on fresh Mac dev machines without
    espeak-ng."""
    monkeypatch.setattr(lex, "phonemize_variant", lambda v, language=lex.DEFAULT_LANGUAGE: [])
    rec = _record({
        "ortho": _tier("ortho", 3, [{"start": 0, "end": 0.5, "text": "yek"}]),
    })
    hits = lex.search(rec, ["yek"])
    assert hits and hits[0]["matched_text"] == "yek"
