"""Regression tests for the LingPy wordlist provider's language matching.

These cover the substring-containment bug that caused Caucasian Cyrillic
forms (Avar, Dargin, ...) to be persisted under the Arabic (``ar``)
language slot. Symptoms in the field were e.g. ``ar.concepts.fire =
['чӀа', 'цӀа', 'цӀай']`` (Avar) instead of Arabic forms; the root cause
was a literal ``frag in lang_key`` substring check that matched ``"ar"``
inside ``"avar"`` / ``"karelian"`` / ``"hungarian"`` / etc.

The fix is exact case-insensitive equality (with whitespace + dash +
underscore folding) on the language key. These tests lock that down.
"""

from __future__ import annotations

import pytest

try:
    from .lingpy_wordlist import LingPyCldfProvider
except ImportError:  # pragma: no cover -- direct-invoke fallback
    from lingpy_wordlist import LingPyCldfProvider  # type: ignore


# ---------------------------------------------------------------------------
# _lang_key_matches: the substring trap, fixed
# ---------------------------------------------------------------------------

# The Arabic fragments include "ar" (ISO 639-1). Under the old substring
# check, every doculect whose name *contained* "ar" matched: avar,
# dargin, karelian, hungarian, magyar, etc. These tests assert that
# none of those collide under the new exact-equality matcher.
ARABIC_FRAGMENTS = ["arb", "ara", "ar", "arabic", "stan1318"]
PERSIAN_FRAGMENTS = ["pes", "fas", "fa", "persian", "farsi", "west2369"]
TURKISH_FRAGMENTS = ["tur", "tr", "turkish", "nucl1301"]


@pytest.mark.parametrize("doculect", [
    "avar",          # NE Caucasian Cyrillic -- the original bug report
    "dargin",        # NE Caucasian Cyrillic
    "karelian",      # Uralic Latin/Cyrillic
    "hungarian",     # Uralic Latin
    "magyar",        # Hungarian endonym
    "bulgarian",     # Slavic Cyrillic
    "akhvakh",       # NE Caucasian
    "chamalal",      # NE Caucasian
    "khwarezmian",   # extinct Iranian
])
def test_arabic_fragments_do_not_substring_match_other_languages(doculect):
    assert not LingPyCldfProvider._lang_key_matches(doculect, ARABIC_FRAGMENTS), (
        f"Arabic fragments {ARABIC_FRAGMENTS!r} substring-matched {doculect!r} "
        "-- the substring-collision bug has regressed"
    )


@pytest.mark.parametrize("doculect", [
    "fang",          # Bantu, contains "fa"
    "fante",         # Twi/Akan, contains "fa"
    "farefare",      # Gur, contains "fa"
    "kafa",          # Omotic, contains "fa"
])
def test_persian_fragments_do_not_substring_match_other_languages(doculect):
    assert not LingPyCldfProvider._lang_key_matches(doculect, PERSIAN_FRAGMENTS)


@pytest.mark.parametrize("doculect", [
    "trumai",        # Brazilian isolate, contains "tr"
    "estrumic",      # synthetic example -- many Slavic/Bantu names contain "tr"
    "central",       # contains "tr"
    "matrilineal",   # not a language but still substring-matches
])
def test_turkish_fragments_do_not_substring_match_other_languages(doculect):
    assert not LingPyCldfProvider._lang_key_matches(doculect, TURKISH_FRAGMENTS)


# ---------------------------------------------------------------------------
# Positive cases: legitimate matches still work
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doculect,fragments", [
    ("arabic", ARABIC_FRAGMENTS),
    ("Arabic", ARABIC_FRAGMENTS),         # case insensitive
    ("ARB", ARABIC_FRAGMENTS),            # case insensitive
    ("arb", ARABIC_FRAGMENTS),
    ("ara", ARABIC_FRAGMENTS),
    ("ar", ARABIC_FRAGMENTS),
    ("stan1318", ARABIC_FRAGMENTS),       # Glottolog id
    ("persian", PERSIAN_FRAGMENTS),
    ("farsi", PERSIAN_FRAGMENTS),
    ("pes", PERSIAN_FRAGMENTS),
    ("turkish", TURKISH_FRAGMENTS),
    ("tur", TURKISH_FRAGMENTS),
])
def test_legitimate_doculect_ids_still_match(doculect, fragments):
    assert LingPyCldfProvider._lang_key_matches(doculect, fragments)


def test_whitespace_and_dash_folding_lets_compound_names_match():
    # "Standard Arabic" lower-cases + space-strips to "standardarabic",
    # and a fragment "standardarabic" should hit. This is the only
    # tolerance we extend beyond strict equality so canonical naming
    # variations (spacing, dashes, underscores) don't lose matches.
    fragments = ["standardarabic", "modernstandardarabic"]
    assert LingPyCldfProvider._lang_key_matches("Standard Arabic", fragments)
    assert LingPyCldfProvider._lang_key_matches("standard-arabic", fragments)
    assert LingPyCldfProvider._lang_key_matches("modern_standard_arabic", fragments)


def test_empty_inputs_are_safe():
    assert not LingPyCldfProvider._lang_key_matches("", ["arabic"])
    assert not LingPyCldfProvider._lang_key_matches("arabic", [])
    assert not LingPyCldfProvider._lang_key_matches("arabic", [""])
    assert not LingPyCldfProvider._lang_key_matches("arabic", [None])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# _iso_to_lang_keys: contract
# ---------------------------------------------------------------------------

def test_known_iso_codes_carry_canonical_fragments():
    p = LingPyCldfProvider()
    ar_frags = p._iso_to_lang_keys("ar")
    assert "arabic" in ar_frags
    assert "arb" in ar_frags
    assert "ara" in ar_frags
    fa_frags = p._iso_to_lang_keys("fa")
    assert "persian" in fa_frags
    assert "farsi" in fa_frags


def test_unknown_iso_falls_back_to_passthrough():
    p = LingPyCldfProvider()
    # Codes not in the ISO_FRAGMENTS map should still produce a usable
    # single-fragment list -- the equality matcher will hit if the
    # dataset's doculect id matches the ISO directly.
    assert p._iso_to_lang_keys("xyz123") == ["xyz123"]


# ---------------------------------------------------------------------------
# Integration: simulated index, end-to-end pollution check
# ---------------------------------------------------------------------------

def _stub_provider_with_index(index):
    """Build a provider whose ``fetch`` will use ``index`` as if a CLDF
    dataset were loaded. Skips the real LingPy import path."""
    p = LingPyCldfProvider()
    # Override the dataset-discovery hooks so ``fetch`` runs against our
    # in-memory index instead of the filesystem.
    p._find_metadata_files = lambda: [object()]   # type: ignore[assignment]
    p._load_dataset = lambda mf: object()         # type: ignore[assignment]
    p._build_index = lambda wl: index             # type: ignore[assignment]
    return p


def test_fetch_does_not_pollute_arabic_with_avar_forms():
    # Index simulating a Lexibank dataset that includes both Arabic and
    # several Caucasian languages whose doculect ids contain "ar" as a
    # substring. Pre-fix, fetching for ``ar`` would return the union of
    # all of these. Post-fix, only the Arabic doculect contributes.
    index = {
        "arabic":   {"fire": ["نار"], "water": ["ماء"]},
        "avar":     {"fire": ["цӀа"], "water": ["лъин"]},
        "dargin":   {"fire": ["цIа"]},
        "karelian": {"fire": ["tuli"]},
    }
    p = _stub_provider_with_index(index)
    results = list(p.fetch(
        concepts=["fire", "water"],
        language_codes=["ar"],
        language_meta={},
    ))

    by_concept = {(r.concept_en, r.language_code): r.forms for r in results}
    assert by_concept[("fire", "ar")] == ["نار"]
    assert by_concept[("water", "ar")] == ["ماء"]


def test_fetch_returns_empty_when_no_matching_doculect():
    # When the dataset really doesn't carry the requested language, we
    # return an empty form list rather than dragging in something that
    # accidentally substring-matches.
    index = {
        "avar":     {"fire": ["цӀа"]},
        "karelian": {"fire": ["tuli"]},
    }
    p = _stub_provider_with_index(index)
    results = list(p.fetch(
        concepts=["fire"],
        language_codes=["ar"],
        language_meta={},
    ))
    assert results == [
        # FetchResult.forms is empty -- the caller (registry) will fall
        # back to the next provider in priority order.
        results[0],
    ]
    assert results[0].forms == []
    assert results[0].language_code == "ar"
