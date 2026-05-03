from __future__ import annotations

import pytest

from concept_source_item import parse_cue_name


@pytest.mark.parametrize(
    ("cue", "expected_source_item", "expected_source_survey", "expected_label"),
    [
        ("(1.2)- forehead", "1.2", "KLQ", "forehead"),
        ("(2.10)- maternal uncle", "2.10", "KLQ", "maternal uncle"),
        ("(1.10)- the baby is in the uterus", "1.10", "KLQ", "the baby is in the uterus"),
        ("(2.13)- paternal uncle's son", "2.13", "KLQ", "paternal uncle's son"),
        ("(2.13)- paternal uncle’s son", "2.13", "KLQ", "paternal uncle’s son"),
        ("1- one", "1", "JBIL", "one"),
        ("324-we", "324", "JBIL", "we"),
        ("325- you (pl.)", "325", "JBIL", "you (pl.)"),
        ("[5.1]- The boy cut the rope with a knife", "5.1", "EXT", "The boy cut the rope with a knife"),
        ("[5.20]- When I was cutting up vegetables, I cut my hand.", "5.20", "EXT", "When I was cutting up vegetables, I cut my hand."),
        ("forehead", None, None, "forehead"),
        ("   (3.4)- leading whitespace", "3.4", "KLQ", "leading whitespace"),
        ("(4.5)-no space after dash", "4.5", "KLQ", "no space after dash"),
        ("(6.7) - dash space variant", "6.7", "KLQ", "dash space variant"),
        ("(8.9)— em dash variant", "8.9", "KLQ", "em dash variant"),
        ("1.2- bare dotted no parens", None, None, "1.2- bare dotted no parens"),
    ],
)
def test_parse_cue_name_extracts_source_item_survey_and_label_variants(
    cue: str,
    expected_source_item: str | None,
    expected_source_survey: str | None,
    expected_label: str,
) -> None:
    assert parse_cue_name(cue) == (expected_source_item, expected_source_survey, expected_label)
