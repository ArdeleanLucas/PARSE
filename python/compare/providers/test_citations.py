"""Tests for the per-provider academic citation map.

Locks in two contracts the Sources Report modal depends on:

1. Every provider id registered in ``PROVIDER_PRIORITY`` (plus the
   ``UNKNOWN_SOURCE`` sentinel) has a citation entry. A new provider
   can't ship without an entry -- otherwise the modal would render a
   bare provider id instead of a citation.

2. Each entry has the required fields the modal renders. ``citation``
   (free text) is mandatory; ``bibtex`` may be empty for non-bibliographic
   providers (LLM, manual, sentinel) but the *key must exist* so the
   modal's ``Export BibTeX`` filter can run without per-row null checks.
"""

from __future__ import annotations

import re

import pytest

try:
    from .citations import (
        CITATION_DISPLAY_ORDER,
        PROVIDER_CITATIONS,
        get_citation,
        get_citations,
    )
    from .registry import PROVIDER_PRIORITY
    from .provenance import UNKNOWN_SOURCE
except ImportError:  # pragma: no cover -- direct-invoke fallback
    from citations import (  # type: ignore
        CITATION_DISPLAY_ORDER,
        PROVIDER_CITATIONS,
        get_citation,
        get_citations,
    )
    from registry import PROVIDER_PRIORITY  # type: ignore
    from provenance import UNKNOWN_SOURCE  # type: ignore


REQUIRED_KEYS = {"label", "type", "authors", "year", "title", "citation", "bibtex"}
VALID_TYPES = {"dataset", "tool", "ai", "manual", "sentinel"}
TYPES_THAT_MAY_OMIT_BIBTEX = {"ai", "manual", "sentinel"}
DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s]+$")


# ---------------------------------------------------------------------------
# Coverage / completeness
# ---------------------------------------------------------------------------

def test_every_registry_provider_has_a_citation():
    missing = [p for p in PROVIDER_PRIORITY if p not in PROVIDER_CITATIONS]
    assert not missing, (
        "Providers in PROVIDER_PRIORITY without a citation entry: "
        f"{missing}. Add an entry to PROVIDER_CITATIONS in citations.py."
    )


def test_unknown_sentinel_has_a_citation():
    # The Sources Report modal renders ``unknown`` rows for legacy
    # bare-string entries; the citation must be present so the modal
    # can show a "re-populate to attribute" caveat.
    assert UNKNOWN_SOURCE in PROVIDER_CITATIONS


def test_no_orphan_citation_entries():
    # Reverse coverage: every citation entry corresponds to a real
    # provider id (or the sentinel). Catches typos that would render
    # never-used citation blocks.
    valid = set(PROVIDER_PRIORITY) | {UNKNOWN_SOURCE}
    orphans = [k for k in PROVIDER_CITATIONS if k not in valid]
    assert not orphans, (
        f"Citation entries with no matching provider id: {orphans}"
    )


def test_display_order_matches_citation_keys():
    # CITATION_DISPLAY_ORDER drives the modal's section ordering; every
    # provider with a citation must appear in it exactly once.
    expected = set(PROVIDER_CITATIONS.keys())
    actual = set(CITATION_DISPLAY_ORDER)
    assert expected == actual
    assert len(CITATION_DISPLAY_ORDER) == len(set(CITATION_DISPLAY_ORDER)), (
        "CITATION_DISPLAY_ORDER has duplicates"
    )


# ---------------------------------------------------------------------------
# Per-entry shape
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider_id", sorted(PROVIDER_CITATIONS.keys()))
def test_citation_entry_has_required_keys(provider_id):
    entry = PROVIDER_CITATIONS[provider_id]
    missing = REQUIRED_KEYS - entry.keys()
    assert not missing, (
        f"{provider_id}: missing required keys {missing}"
    )


@pytest.mark.parametrize("provider_id", sorted(PROVIDER_CITATIONS.keys()))
def test_citation_type_is_valid(provider_id):
    t = PROVIDER_CITATIONS[provider_id]["type"]
    assert t in VALID_TYPES, f"{provider_id}: type {t!r} not in {VALID_TYPES}"


@pytest.mark.parametrize("provider_id", sorted(PROVIDER_CITATIONS.keys()))
def test_citation_text_is_non_empty(provider_id):
    citation = PROVIDER_CITATIONS[provider_id]["citation"]
    assert isinstance(citation, str) and citation.strip(), (
        f"{provider_id}: citation must be a non-empty string"
    )


@pytest.mark.parametrize("provider_id", sorted(PROVIDER_CITATIONS.keys()))
def test_bibtex_present_for_bibliographic_providers(provider_id):
    entry = PROVIDER_CITATIONS[provider_id]
    bibtex = entry["bibtex"]
    assert isinstance(bibtex, str), f"{provider_id}: bibtex must be a string"
    if entry["type"] in TYPES_THAT_MAY_OMIT_BIBTEX:
        # LLM, manual, sentinel: bibtex may be empty (these aren't
        # bibliographically citable) but the field must exist.
        return
    assert bibtex.strip().startswith("@"), (
        f"{provider_id}: dataset/tool entries must have a BibTeX block "
        f"starting with @, got {bibtex!r}"
    )


@pytest.mark.parametrize("provider_id", sorted(PROVIDER_CITATIONS.keys()))
def test_doi_is_well_formed_when_present(provider_id):
    entry = PROVIDER_CITATIONS[provider_id]
    doi = entry.get("doi")
    if doi is None:
        return
    assert DOI_RE.match(doi), f"{provider_id}: DOI {doi!r} doesn't match 10.XXXX/... pattern"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_get_citations_returns_a_copy():
    a = get_citations()
    a["asjp"]["label"] = "MUTATED"
    b = get_citations()
    assert b["asjp"]["label"] != "MUTATED", (
        "get_citations() must return a defensive copy so modal-side "
        "mutation can't poison the module-level dict"
    )


def test_get_citation_falls_back_to_unknown_for_unrecognised_id():
    # A provider id the citations map doesn't know about -- say a
    # workspace-local override or a brand-new provider that landed
    # before its citation was added -- should still get a renderable
    # row (the sentinel) rather than blowing up the modal.
    entry = get_citation("definitely-not-a-real-provider")
    assert entry["type"] == "sentinel"
    assert entry["label"] == PROVIDER_CITATIONS[UNKNOWN_SOURCE]["label"]


def test_grokipedia_is_flagged_as_ai():
    # The modal renders ``ai`` rows with a red caveat banner. If
    # grokipedia ever drops to "tool" or "dataset" the warning vanishes,
    # which would let users cite LLM output as a primary source.
    assert PROVIDER_CITATIONS["grokipedia"]["type"] == "ai"
    note = PROVIDER_CITATIONS["grokipedia"].get("note", "")
    assert "verify" in note.lower() or "primary source" in note.lower()


def test_unknown_sentinel_is_marked_sentinel_with_remediation_note():
    entry = PROVIDER_CITATIONS[UNKNOWN_SOURCE]
    assert entry["type"] == "sentinel"
    assert "overwrite" in entry["note"].lower(), (
        "The unknown sentinel's note should tell users how to fix legacy "
        "data (re-run populate with overwrite=true)"
    )
