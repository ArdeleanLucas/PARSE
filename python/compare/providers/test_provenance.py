"""Tests for the provenance normalisation helper shared between the
fetcher and the Sources Report API. Both shapes (legacy bare-list and
new ``{"form", "sources"}``) must produce the same tuple stream so the
report endpoint can aggregate over mixed, partially-migrated corpora
without branching per entry."""

from pathlib import Path
import sys

# Ensure `compare.*` imports resolve when running from repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from compare.providers.provenance import (  # noqa: E402
    UNKNOWN_SOURCE,
    entry_has_forms,
    iter_forms_with_sources,
)


def test_iter_forms_handles_legacy_bare_list_with_unknown_source() -> None:
    """Pre-provenance corpora surface every form with the ``unknown``
    sentinel so the report can show them under an "Unattributed"
    bucket rather than silently dropping them."""
    out = list(iter_forms_with_sources(["ma:ʔ", "mɑ"]))
    assert out == [("ma:ʔ", [UNKNOWN_SOURCE]), ("mɑ", [UNKNOWN_SOURCE])]


def test_iter_forms_handles_new_provenance_shape() -> None:
    entry = [
        {"form": "ma:ʔ", "sources": ["wikidata", "wiktionary"]},
        {"form": "ɒːb", "sources": ["asjp"]},
    ]
    assert list(iter_forms_with_sources(entry)) == [
        ("ma:ʔ", ["wikidata", "wiktionary"]),
        ("ɒːb", ["asjp"]),
    ]


def test_iter_forms_mixed_shape_in_same_entry() -> None:
    """Realistically after a partial re-populate, one concept may hold
    both shapes side-by-side. The helper must not trip on the mix."""
    entry = [
        "legacy_form",
        {"form": "new_form", "sources": ["wikidata"]},
    ]
    assert list(iter_forms_with_sources(entry)) == [
        ("legacy_form", [UNKNOWN_SOURCE]),
        ("new_form", ["wikidata"]),
    ]


def test_iter_forms_empty_or_malformed_inputs_yield_nothing() -> None:
    assert list(iter_forms_with_sources(None)) == []
    assert list(iter_forms_with_sources([])) == []
    assert list(iter_forms_with_sources([""])) == []
    # dict without `form`
    assert list(iter_forms_with_sources([{"sources": ["asjp"]}])) == []
    # dict with empty form
    assert list(iter_forms_with_sources([{"form": "  ", "sources": ["asjp"]}])) == []
    # non-list top level
    assert list(iter_forms_with_sources("ma:ʔ")) == []


def test_iter_forms_missing_or_empty_sources_falls_back_to_unknown() -> None:
    """A dict entry without a ``sources`` key, or with an empty one,
    should still surface the form (attributed to ``unknown``) rather
    than being silently dropped. Otherwise a malformed row could erase
    a real form from the report."""
    assert list(iter_forms_with_sources([{"form": "ma:ʔ"}])) == [
        ("ma:ʔ", [UNKNOWN_SOURCE])
    ]
    assert list(iter_forms_with_sources([{"form": "ma:ʔ", "sources": []}])) == [
        ("ma:ʔ", [UNKNOWN_SOURCE])
    ]


def test_entry_has_forms_matches_iter_behaviour() -> None:
    assert entry_has_forms(["ma:ʔ"]) is True
    assert entry_has_forms([{"form": "ma:ʔ", "sources": ["asjp"]}]) is True
    assert entry_has_forms([]) is False
    assert entry_has_forms(None) is False
    assert entry_has_forms([""]) is False
    assert entry_has_forms([{"sources": ["asjp"]}]) is False
