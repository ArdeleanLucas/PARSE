"""Tests for the Reference Forms selection mask.

Covers the three legs of ``filter_refs_by_selection`` semantics, the
round-trip through ``load_contact_language_data``, and the resulting
``compute_similarity_scores`` behaviour when selections are active.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from .cognate_compute import (
        ConceptSpec,
        FormRecord,
        compute_similarity_scores,
        filter_refs_by_selection,
        load_contact_language_data,
    )
except ImportError:  # pragma: no cover -- direct-invoke fallback
    from cognate_compute import (  # type: ignore
        ConceptSpec,
        FormRecord,
        compute_similarity_scores,
        filter_refs_by_selection,
        load_contact_language_data,
    )


# ---------------------------------------------------------------------------
# filter_refs_by_selection
# ---------------------------------------------------------------------------

def test_filter_refs_by_selection_none_returns_refs_unchanged():
    refs = ["maːʔ", "ماء", "muya"]
    filtered, explicit_empty = filter_refs_by_selection(refs, None)
    assert filtered == refs
    # Returns a *copy* so callers can mutate freely.
    assert filtered is not refs
    assert explicit_empty is False


def test_filter_refs_by_selection_empty_is_explicit_opt_out():
    refs = ["maːʔ", "ماء"]
    filtered, explicit_empty = filter_refs_by_selection(refs, [])
    assert filtered == []
    assert explicit_empty is True


def test_filter_refs_by_selection_subset_keeps_only_allowed():
    refs = ["maːʔ", "ماء", "muya"]
    filtered, explicit_empty = filter_refs_by_selection(refs, ["ماء"])
    assert filtered == ["ماء"]
    assert explicit_empty is False


def test_filter_refs_by_selection_ignores_unknown_entries():
    # A selection carrying a form no longer in ``refs`` (maybe removed by
    # a later re-populate) should just be dropped, not surfaced as an
    # explicit-empty signal.
    refs = ["maːʔ"]
    filtered, explicit_empty = filter_refs_by_selection(refs, ["stale-form"])
    assert filtered == []
    assert explicit_empty is False


def test_filter_refs_by_selection_normalises_whitespace():
    refs = ["  maːʔ  "]
    filtered, explicit_empty = filter_refs_by_selection(refs, ["maːʔ"])
    assert filtered == ["  maːʔ  "]
    assert explicit_empty is False


# ---------------------------------------------------------------------------
# load_contact_language_data
# ---------------------------------------------------------------------------

def _write_sil_config(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "sil_contact_languages.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_contact_language_data_returns_empty_selections_by_default(tmp_path):
    path = _write_sil_config(tmp_path, {
        "_meta": {"primary_contact_languages": ["ar"]},
        "ar": {"name": "Arabic", "concepts": {"water": ["maːʔ"]}},
    })
    _, _, selections = load_contact_language_data(path)
    assert selections == {}


def test_load_contact_language_data_parses_form_selections(tmp_path):
    path = _write_sil_config(tmp_path, {
        "_meta": {
            "primary_contact_languages": ["ar", "fa"],
            "form_selections": {
                "water": {
                    "ar": ["ماء"],
                    "fa": [],   # explicit opt-out
                },
            },
        },
        "ar": {"name": "Arabic", "concepts": {"water": ["ماء", "maːʔ"]}},
        "fa": {"name": "Persian", "concepts": {"water": ["آب"]}},
    })
    _, _, selections = load_contact_language_data(path)
    assert selections == {
        "water": {
            "ar": ["ماء"],
            "fa": [],
        },
    }


def test_load_contact_language_data_normalises_concept_keys(tmp_path):
    path = _write_sil_config(tmp_path, {
        "_meta": {
            "primary_contact_languages": ["ar"],
            "form_selections": {
                "#water:Water": {"ar": ["ماء"]},
            },
        },
        "ar": {"name": "Arabic", "concepts": {"water": ["ماء"]}},
    })
    _, _, selections = load_contact_language_data(path)
    assert "water" in selections
    assert selections["water"]["ar"] == ["ماء"]


def test_load_contact_language_data_skips_malformed_selection_shapes(tmp_path):
    path = _write_sil_config(tmp_path, {
        "_meta": {
            "primary_contact_languages": ["ar"],
            "form_selections": {
                "water": "not-a-dict",
                "fire": {"ar": "not-a-list"},
                "": {"ar": ["stale"]},
            },
        },
        "ar": {"name": "Arabic", "concepts": {"water": ["ماء"]}},
    })
    _, _, selections = load_contact_language_data(path)
    assert selections == {}


# ---------------------------------------------------------------------------
# compute_similarity_scores honours the mask
# ---------------------------------------------------------------------------

def _make_records(speaker: str, concept_id: str, ipa: str) -> dict:
    return {concept_id: [FormRecord(
        speaker=speaker,
        concept_id=concept_id,
        concept_label="",
        ipa=ipa,
        ortho="",
        start_sec=0.0,
        end_sec=1.0,
    )]}


def test_compute_similarity_scores_without_selection_uses_all_refs():
    records = _make_records("SPK-01", "water", "maːʔ")
    refs = {"water": {"ar": ["ماء", "maːʔ"]}}
    scores = compute_similarity_scores(
        forms_by_concept=records,
        concepts=[ConceptSpec(concept_id="water", label="water")],
        contact_languages=["ar"],
        refs_by_concept=refs,
    )
    assert scores["water"]["SPK-01"]["ar"]["has_reference_data"] is True
    assert scores["water"]["SPK-01"]["ar"]["score"] == 0.0


def test_compute_similarity_scores_selection_filters_refs():
    # Exact-match IPA ref is deselected -> only the Arabic-script ref is
    # considered, so the edit distance jumps from 0.0 to 1.0.
    records = _make_records("SPK-01", "water", "maːʔ")
    refs = {"water": {"ar": ["ماء", "maːʔ"]}}
    selections = {"water": {"ar": ["ماء"]}}
    scores = compute_similarity_scores(
        forms_by_concept=records,
        concepts=[ConceptSpec(concept_id="water", label="water")],
        contact_languages=["ar"],
        refs_by_concept=refs,
        form_selections_by_concept=selections,
    )
    assert scores["water"]["SPK-01"]["ar"]["score"] == 1.0


def test_compute_similarity_scores_empty_selection_skips_similarity():
    records = _make_records("SPK-01", "water", "maːʔ")
    refs = {"water": {"ar": ["ماء", "maːʔ"]}}
    selections = {"water": {"ar": []}}
    scores = compute_similarity_scores(
        forms_by_concept=records,
        concepts=[ConceptSpec(concept_id="water", label="water")],
        contact_languages=["ar"],
        refs_by_concept=refs,
        form_selections_by_concept=selections,
    )
    cell = scores["water"]["SPK-01"]["ar"]
    # refs exist on disk, but user deselected everything -> score is
    # skipped while has_reference_data remains True so the UI can
    # distinguish this from "no refs available".
    assert cell["has_reference_data"] is True
    assert cell["score"] is None


def test_compute_similarity_scores_selection_routes_by_concept_label():
    # The ConceptSpec here has a numeric concept_id + English label.
    # Selections written against the English label (what the UI uses as
    # its stable key) should still apply to records keyed by the
    # numeric id.
    records = _make_records("SPK-01", "42", "maːʔ")
    refs = {"42": {"ar": ["ماء", "maːʔ"]}}
    selections = {"water": {"ar": ["ماء"]}}   # deselect the exact IPA match
    scores = compute_similarity_scores(
        forms_by_concept=records,
        concepts=[ConceptSpec(concept_id="42", label="water")],
        contact_languages=["ar"],
        refs_by_concept=refs,
        form_selections_by_concept=selections,
    )
    # Label "water" matched the selection, exact IPA was filtered out,
    # so the best remaining ref is the Arabic-script "ماء" -> distance 1.0.
    assert scores["42"]["SPK-01"]["ar"]["score"] == 1.0
