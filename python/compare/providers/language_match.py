"""Doculect / language-key exact matching for CLEF providers.

Many CLEF providers (lingpy_wordlist, pylexibank, pycldf, wiktionary) need to
resolve dataset language identifiers against the user's configured contact
languages. The naive approach -- Python substring containment
(``frag in lang_key``) -- caused a real substring-match cross-language pollution
bug where ``"ar"`` matched ``"avar"`` / ``"tatar"`` / ``"marathi"`` and dumped
Cyrillic and Devanagari forms under Arabic. The first fix landed in
``lingpy_wordlist.py``; this shared helper lifts that exact-equality logic so
sibling providers use the same safe matcher instead of reintroducing the bug.

Use ``lang_key_matches(lang_key, fragments)`` anywhere you might otherwise be
tempted to write ``any(frag in lang_key for frag in fragments)``.
"""

from typing import List


def _normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def lang_key_matches(lang_key: str, fragments: List[str]) -> bool:
    """True iff ``lang_key`` exactly equals one of ``fragments`` after normalization.

    Both sides are lowercased, whitespace-stripped, and have dashes / underscores
    collapsed. So ``"Standard Arabic"`` matches a fragment ``"standardarabic"``,
    but ``"avar"`` does not match ``"ar"``.
    """
    if not lang_key:
        return False

    target = _normalize(lang_key)
    for frag in fragments:
        if not isinstance(frag, str):
            continue
        if not frag.strip():
            continue
        if _normalize(frag) == target:
            return True
    return False
