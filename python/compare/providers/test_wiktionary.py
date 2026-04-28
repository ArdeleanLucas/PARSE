from __future__ import annotations

try:
    from .wiktionary import WiktionaryProvider
except ImportError:  # pragma: no cover -- direct-invoke fallback
    from wiktionary import WiktionaryProvider  # type: ignore


def test_extract_ipa_for_arabic_matches_bcp47_base_and_excludes_avar():
    provider = WiktionaryProvider()
    wikitext = """
== Avar ==
{{IPA|avar|/t͡ɬa/}}

== Arabic ==
{{IPA|ar|/maːʔ/}}

== Moroccan Arabic ==
{{IPA|ar-MA|/ma/}}
"""

    forms = provider._extract_ipa_for_lang(wikitext, "ar")

    assert forms == ["maːʔ", "ma"]
    assert all("t͡ɬ" not in form for form in forms)


def test_extract_ipa_for_arabic_matches_name_and_iso3_tags():
    provider = WiktionaryProvider()
    wikitext = """
{{IPA|Arabic|/ħa/}}
{{IPA|arb|/ʕarabi/}}
{{IPA|avar|/t͡ɬa/}}
"""

    forms = provider._extract_ipa_for_lang(wikitext, "ar")

    assert forms == ["ħa", "ʕarabi"]
    assert all("t͡ɬ" not in form for form in forms)
