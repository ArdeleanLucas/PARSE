from __future__ import annotations

import pytest

from concept_source_item import parse_cue_name


@pytest.mark.parametrize(
    ("cue", "expected_source_item", "expected_label"),
    [
        ("(1.2)- forehead", "1.2", "forehead"),
        ("(2.10)- maternal uncle", "2.10", "maternal uncle"),
        ("(1.10)- the baby is in the uterus", "1.10", "the baby is in the uterus"),
        ("(2.13)- paternal uncle’s son", "2.13", "paternal uncle’s son"),
        ("forehead", None, "forehead"),
        ("   (3.4)- leading whitespace", "3.4", "leading whitespace"),
        ("(4.5)-no space after dash", "4.5", "no space after dash"),
        ("(6.7) - dash space variant", "6.7", "dash space variant"),
        ("(8.9)— em dash variant", "8.9", "em dash variant"),
    ],
)
def test_parse_cue_name_extracts_source_item_and_label_variants(
    cue: str,
    expected_source_item: str | None,
    expected_label: str,
) -> None:
    assert parse_cue_name(cue) == (expected_source_item, expected_label)
