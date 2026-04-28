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


def test_translation_table_extraction():
    provider = WiktionaryProvider()
    wikitext = """
====Translations====
* Arabic: {{t|ar|شَعْر}} {{t+|ar|[[كتاب|كِتاب]]}} {{tt|ar|ماء}} {{tt+|ar|شَعْر}}
* Central Kurdish: {{t+|ckb|قژ}} {{tt|ckb|[[پەر]]}}
* Persian: {{tt|fa|مو}} {{t+|fas|موى}}
* Turkish: {{t|tr|saç}}
* Noise: {{t-needed|ar}} {{t|ar|{{l|ar|ماء}}}} {{t|ar|}}
"""

    assert provider._extract_translation_table_forms(wikitext, "ar") == ["شَعْر", "كِتاب", "ماء"]
    assert provider._extract_translation_table_forms(wikitext, "ckb") == ["قژ", "پەر"]
    assert provider._extract_translation_table_forms(wikitext, "fa") == ["مو", "موى"]


def test_lookup_prefers_translation_table_before_ipa(monkeypatch):
    provider = WiktionaryProvider()
    wikitext = """
{{t|ar|ماء}}
{{IPA|ar|/maːʔ/}}
"""
    monkeypatch.setattr(provider, "_fetch_en_wiktionary_wikitext", lambda _word: wikitext)

    assert provider._lookup("water", "ar") == ["ماء"]


def test_extract_any_ipa_ignores_wikilink_brackets():
    provider = WiktionaryProvider()
    wikitext = """
[[File:Pieni2.jpg|thumb]] [[کتاب]] /www.usgs.gov/ /water-science-school/ [maːʔ]
"""

    assert provider._extract_any_ipa(wikitext) == ["maːʔ"]
