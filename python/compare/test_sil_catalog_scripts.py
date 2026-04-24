"""Tests for the per-language ISO 15924 script field in SIL_CATALOG.

The script hint drives deterministic routing in the Reference Forms panel.
These tests lock in two contracts:

1. Every shipped catalog entry carries a script field (so the UI never
   has to fall back to the Unicode-block regex for bundled languages).
2. The script values use canonical ISO 15924 four-letter codes (Arab,
   Latn, Hebr, ...) -- not script names ("Arabic"), not 2/3-letter codes,
   not lowercased forms.
"""

from __future__ import annotations

try:
    from .sil_catalog import SIL_CATALOG
except ImportError:  # pragma: no cover -- direct-invoke fallback
    from sil_catalog import SIL_CATALOG  # type: ignore


# Subset of ISO 15924 codes actually used in SIL_CATALOG. Add more here
# when extending the catalog with languages in new scripts.
KNOWN_ISO_15924_CODES = {
    "Arab", "Armn", "Beng", "Cyrl", "Deva", "Ethi", "Geor", "Grek",
    "Gujr", "Guru", "Hang", "Hans", "Hant", "Hebr", "Jpan", "Khmr",
    "Knda", "Laoo", "Latn", "Mlym", "Mymr", "Sinh", "Syrc", "Taml",
    "Telu", "Thai", "Tibt",
}


def test_every_catalog_entry_has_a_script():
    missing = [e for e in SIL_CATALOG if "script" not in e]
    assert not missing, f"Entries missing 'script' field: {[e['code'] for e in missing]}"


def test_script_values_are_canonical_iso_15924():
    bad = [
        (e["code"], e["script"])
        for e in SIL_CATALOG
        if e.get("script") not in KNOWN_ISO_15924_CODES
    ]
    assert not bad, (
        "Catalog entries with non-canonical script codes (expected ISO 15924, "
        "4-letter title-case): " + repr(bad)
    )


def test_known_script_assignments_are_correct():
    # Spot-check the languages that drive the thesis use case + a few
    # that are easy to get wrong.
    by_code = {e["code"]: e for e in SIL_CATALOG}

    assert by_code["ar"]["script"] == "Arab"
    assert by_code["fa"]["script"] == "Arab"
    assert by_code["ckb"]["script"] == "Arab"   # Sorani uses Arabic
    assert by_code["kmr"]["script"] == "Latn"   # Kurmanji uses Latin
    assert by_code["sdh"]["script"] == "Arab"   # Southern Kurdish: Arabic
    assert by_code["tr"]["script"] == "Latn"
    assert by_code["heb"]["script"] == "Hebr"

    # Multi-script edge cases the modern dominant script wins.
    assert by_code["tgk"]["script"] == "Cyrl"   # Tajik is Cyrl now
    assert by_code["uzb"]["script"] == "Latn"   # Uzbek transitioned to Latn
    assert by_code["aze"]["script"] == "Latn"   # Azerbaijani transitioned

    # Greek is its own ISO code -- the Unicode regex fallback skips
    # Greek (because IPA uses β/χ/etc.), so the hint is the only
    # correct routing for ell/grc.
    assert by_code["ell"]["script"] == "Grek"
    assert by_code["grc"]["script"] == "Grek"
