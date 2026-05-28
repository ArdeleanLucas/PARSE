from __future__ import annotations

import json
from pathlib import Path

import pytest

from concept_canonical import (
    assign_variant_letters,
    canonicalize_label,
    label_key,
    strip_bare_variant_suffix,
    strip_clarifier,
    strip_cue_prefix,
    variant_stem,
    variant_suffix,
)
from concept_linking import normalize_cross_survey_gloss
from lexeme_notes import parse_audition_csv

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "variant-letters.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_fixture()["cases"], ids=lambda case: case["name"])
def test_assign_variant_letters_fixture_parity(case: dict) -> None:
    """Backend assignment must match the shared frontend fixture exactly."""

    assert assign_variant_letters(case["input"]) == case["expected"]


def test_assign_variant_letters_base26_fallback_after_z() -> None:
    intervals = [{"start": idx} for idx in range(28)]

    assert assign_variant_letters(intervals)[24:] == ["Y", "Z", "AA", "AB"]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("big (A)", "A"),
        ("big (Z)  ", "Z"),
        ("big (27)", "27"),
        ("hair (women)", ""),
        ("egg (e.g., chicken)", ""),
    ],
)
def test_variant_suffix_preserves_clarifier_parentheticals(label: str, expected: str) -> None:
    assert variant_suffix(label) == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("big (A)", "big"),
        ("big (27)", "big"),
        ("hair (women)", "hair (women)"),
        ("egg (e.g., chicken) (A)", "egg (e.g., chicken)"),
    ],
)
def test_variant_stem_strips_only_variant_parentheticals(label: str, expected: str) -> None:
    assert variant_stem(label) == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("head A", "head"),
        ("head Z", "head"),
        ("head E", "head"),
        ("head AB", "head AB"),
        ("the letter A", "the letter"),
    ],
)
def test_strip_bare_variant_suffix_widens_lexeme_letters_to_z(label: str, expected: str) -> None:
    assert strip_bare_variant_suffix(label) == expected


def test_strip_cue_prefix_handles_audition_prefix_shapes() -> None:
    assert strip_cue_prefix("48 stomach (organ)") == "stomach (organ)"
    assert strip_cue_prefix("(4.1)- big") == "big"
    assert strip_cue_prefix("[5.1]- the boy") == "the boy"
    assert strip_cue_prefix("  63: bread") == "bread"


def test_canonicalize_label_strips_cue_prefix_and_variant_forms() -> None:
    assert canonicalize_label("48 stomach (organ) (A)") == "stomach (organ)"
    assert canonicalize_label("(4.1)- big Z") == "big"
    assert canonicalize_label("hair (women)") == "hair (women)"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("hair (men)", "hair"),
        ("salt (eating)", "salt"),
        ("egg (e.g., chicken)", "egg"),
        ("dry", "dry"),
        ("big (A)", "big"),
        ("hair (women) (B)", "hair"),
        ("", ""),
    ],
)
def test_strip_clarifier_strips_all_parenthetical_content(label: str, expected: str) -> None:
    assert strip_clarifier(label) == expected


def test_label_key_preserves_existing_registry_semantics() -> None:
    assert label_key("  Big   Thing (A) ") == "big thing (a)"


def test_normalize_cross_survey_gloss_uses_shared_canonical_forms() -> None:
    assert normalize_cross_survey_gloss("(4.1)- big (A)") == normalize_cross_survey_gloss("big") == "big"
    assert normalize_cross_survey_gloss("48 stomach (organ) A") == "stomach (organ)"


def test_lexeme_note_parser_strips_e_to_z_bare_variants() -> None:
    text = "Name\tStart\tDuration\tTime Format\tType\tDescription\n(2.3)- father Z\t1.0\t0.5\tdecimal\tCue\t\n"

    [row] = parse_audition_csv(text)

    assert row.variant == "Z"
    assert row.remainder == "father"
