"""Regression tests for multi-word IPA forms in LingPy cognate clustering.

LingPy's ``ipa2tokens`` rejects forms containing spaces (e.g. Kurdish
light-verb constructions like ``"qap girtin"``). LexStat surfaces this as
``ValueError: Could not convert item ID: <row>`` and aborts the entire
phonetic-similarity job. ``_lingpy_safe_form`` collapses internal
whitespace to LingPy's ``_`` word-boundary symbol so the wordlist
tokenizes cleanly -- without mutating any stored or displayed form.
"""

from __future__ import annotations

import pytest

try:
    from .cognate_compute import (
        ConceptSpec,
        FormRecord,
        _compute_cognate_sets_with_lingpy,
        _lingpy_safe_form,
    )
except ImportError:  # pragma: no cover -- direct-invoke fallback
    from cognate_compute import (  # type: ignore
        ConceptSpec,
        FormRecord,
        _compute_cognate_sets_with_lingpy,
        _lingpy_safe_form,
    )


# ---------------------------------------------------------------------------
# _lingpy_safe_form -- pure, no LingPy dependency
# ---------------------------------------------------------------------------

def test_safe_form_collapses_internal_space():
    assert _lingpy_safe_form("qap girtin") == "qap_girtin"


def test_safe_form_handles_multiple_and_repeated_spaces():
    assert _lingpy_safe_form("qap/gaza girtin") == "qap/gaza_girtin"
    assert _lingpy_safe_form("a   b\tc") == "a_b_c"


def test_safe_form_leaves_single_word_unchanged():
    assert _lingpy_safe_form("xwārdin") == "xwārdin"


def test_safe_form_strips_edges_without_introducing_separators():
    assert _lingpy_safe_form("  girtin  ") == "girtin"


def test_safe_form_tolerates_none_and_empty():
    assert _lingpy_safe_form("") == ""
    assert _lingpy_safe_form(None) == ""  # type: ignore[arg-type]


def test_safe_form_produces_no_spaces_for_realistic_forms():
    samples = ["qap/gaza girtin", "qap girtin", "ser birrin", "destê xwe"]
    for form in samples:
        assert " " not in _lingpy_safe_form(form)


# ---------------------------------------------------------------------------
# Full path -- guarded; only runs where LingPy is installed (e.g. CI/server)
# ---------------------------------------------------------------------------

def test_multiword_forms_do_not_crash_lexstat():
    pytest.importorskip("lingpy")

    forms_by_concept = {
        "627": [
            FormRecord("Badr01", "627", "", "qap/gaza girtin", "", 0.0, 1.0),
            FormRecord("Fail03", "627", "", "qap girtin", "", 0.0, 1.0),
            FormRecord("Kalh02", "627", "", "qap girtin", "", 0.0, 1.0),
        ],
        "626": [
            FormRecord("Fail03", "626", "", "xwārdin", "", 0.0, 1.0),
            FormRecord("Kalh02", "626", "", "xwardin", "", 0.0, 1.0),
        ],
    }
    concepts = [ConceptSpec(concept_id="626"), ConceptSpec(concept_id="627")]

    # Previously raised "Could not convert item ID: <row>".
    result = _compute_cognate_sets_with_lingpy(forms_by_concept, concepts, 0.6)

    assert set(result.keys()) == {"626", "627"}
    # The multi-word concept still gets grouped (speakers preserved verbatim).
    speakers_627 = {s for group in result["627"].values() for s in group}
    assert speakers_627 == {"Badr01", "Fail03", "Kalh02"}


def test_unclusterable_placeholder_is_dropped_not_crashed():
    pytest.importorskip("lingpy")

    # A bare "?" tokenises to only-unknown characters and aborts LexStat
    # with "Could not convert item ID". It should be dropped, the rest
    # clustered, and no exception raised.
    forms_by_concept = {
        "629": [
            FormRecord("Badr01", "629", "", "?", "", 0.0, 1.0),
            FormRecord("Fail03", "629", "", "dest", "", 0.0, 1.0),
            FormRecord("Kalh02", "629", "", "dest", "", 0.0, 1.0),
        ],
    }
    concepts = [ConceptSpec(concept_id="629")]

    result = _compute_cognate_sets_with_lingpy(forms_by_concept, concepts, 0.6)

    speakers_629 = {s for group in result.get("629", {}).values() for s in group}
    # The two real forms still cluster; the "?" placeholder is omitted.
    assert speakers_629 == {"Fail03", "Kalh02"}
    assert "Badr01" not in speakers_629


def test_all_unclusterable_returns_empty_without_crashing():
    pytest.importorskip("lingpy")

    forms_by_concept = {
        "999": [
            FormRecord("Badr01", "999", "", "?", "", 0.0, 1.0),
            FormRecord("Fail03", "999", "", "?", "", 0.0, 1.0),
        ],
    }
    concepts = [ConceptSpec(concept_id="999")]

    assert _compute_cognate_sets_with_lingpy(forms_by_concept, concepts, 0.6) == {}


def test_skipped_out_collects_unclusterable_forms():
    pytest.importorskip("lingpy")

    # The "?" placeholder is skipped; the collector records what/why so the
    # caller can surface it instead of dropping it silently.
    forms_by_concept = {
        "629": [
            FormRecord("Badr01", "629", "", "?", "", 0.0, 1.0),
            FormRecord("Fail03", "629", "", "dest", "", 0.0, 1.0),
            FormRecord("Kalh02", "629", "", "dest", "", 0.0, 1.0),
        ],
    }
    concepts = [ConceptSpec(concept_id="629")]

    skipped: list = []
    _compute_cognate_sets_with_lingpy(forms_by_concept, concepts, 0.6, skipped_out=skipped)

    assert skipped == [{"concept_id": "629", "speaker": "Badr01", "form": "?"}]


def test_skipped_out_stays_empty_when_all_clusterable():
    pytest.importorskip("lingpy")

    forms_by_concept = {
        "626": [
            FormRecord("Fail03", "626", "", "xwārdin", "", 0.0, 1.0),
            FormRecord("Kalh02", "626", "", "xwardin", "", 0.0, 1.0),
        ],
    }
    concepts = [ConceptSpec(concept_id="626")]

    skipped: list = []
    _compute_cognate_sets_with_lingpy(forms_by_concept, concepts, 0.6, skipped_out=skipped)

    assert skipped == []
