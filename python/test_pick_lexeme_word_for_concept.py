from __future__ import annotations

from server_routes.annotate import _pick_lexeme_word_for_concept


def test_pick_lexeme_returns_single_overlapping_word() -> None:
    word = {"start": 1.1, "end": 1.9, "text": "head"}

    assert _pick_lexeme_word_for_concept(1.0, 2.0, [word]) == word


def test_pick_lexeme_picks_word_closest_to_concept_midpoint() -> None:
    words = [
        {"start": 1.0, "end": 1.3, "text": "the"},
        {"start": 1.4, "end": 1.7, "text": "head"},
        {"start": 1.7, "end": 2.0, "text": "is"},
    ]

    assert _pick_lexeme_word_for_concept(1.0, 2.0, words) == words[1]


def test_pick_lexeme_returns_none_for_no_overlap() -> None:
    words = [
        {"start": 0.0, "end": 0.5, "text": "before"},
        {"start": 2.1, "end": 2.5, "text": "after"},
    ]

    assert _pick_lexeme_word_for_concept(1.0, 2.0, words) is None


def test_pick_lexeme_tiebreaks_by_overlap_then_first_encountered() -> None:
    larger_overlap = {"start": 1.2, "end": 1.8, "text": "head"}
    smaller_overlap = {"start": 1.4, "end": 1.6, "text": "the"}
    assert _pick_lexeme_word_for_concept(1.0, 2.0, [smaller_overlap, larger_overlap]) == larger_overlap

    first = {"start": 1.0, "end": 1.4, "text": "first"}
    second = {"start": 1.6, "end": 2.0, "text": "second"}
    assert _pick_lexeme_word_for_concept(1.0, 2.0, [first, second]) == first


def test_pick_lexeme_skips_whitespace_only_text() -> None:
    good = {"start": 1.3, "end": 1.7, "text": "head"}

    assert _pick_lexeme_word_for_concept(
        1.0,
        2.0,
        [{"start": 1.4, "end": 1.6, "text": "  "}, good],
    ) == good


def test_pick_lexeme_skips_non_string_text() -> None:
    good = {"start": 1.3, "end": 1.7, "text": "head"}

    assert _pick_lexeme_word_for_concept(
        1.0,
        2.0,
        [
            {"start": 1.4, "end": 1.6, "text": None},
            {"start": 1.4, "end": 1.6, "text": 42},
            good,
        ],
    ) == good
