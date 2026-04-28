"""Wiktionary/Wikipedia provider — translation-table forms with IPA fallback."""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List

import requests

from .base import BaseProvider, FetchResult
from .language_match import lang_key_matches

_CACHE_DIR = Path(__file__).resolve().parents[3] / "config" / "cache"

WIKTIONARY_IPA_RE = re.compile(r'\{\{IPA\|([^}|]+)\|(/[^/]+/|[\[{][^\]}]+[\]}])\}\}')
WIKTIONARY_TRANSLATION_RE = re.compile(r"\{\{(t\+?\|[^{}]*)\}\}", re.IGNORECASE)
WIKILINK_RE = re.compile(r"^\[\[([^\]]+)\]\]$")
IPA_SLASH_RE = re.compile(r'/([^/]{1,40})/')
IPA_BRACKET_RE = re.compile(r'\[([^\]]{1,40})\]')
_WIKTIONARY_FRAGMENTS: Dict[str, List[str]] = {
    "ar": ["ar", "arb", "ara", "arabic"],
    "fa": ["fa", "fas", "pes", "persian", "farsi"],
    "ckb": ["ckb", "sorani", "central kurdish", "centralkurdish"],
    "kmr": ["kmr", "kurmanji", "northern kurdish", "northernkurdish"],
    "tr": ["tr", "tur", "turkish"],
    "heb": ["he", "heb", "hebrew"],
    "syr": ["syr", "syriac"],
    "urd": ["ur", "urd", "urdu"],
}


def _split_template_args(body: str) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    link_depth = 0
    i = 0
    while i < len(body):
        if body.startswith("[[", i):
            link_depth += 1
            buf.append("[[")
            i += 2
            continue
        if body.startswith("]]", i) and link_depth:
            link_depth -= 1
            buf.append("]]")
            i += 2
            continue
        char = body[i]
        if char == "|" and link_depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
        i += 1
    parts.append("".join(buf))
    return parts


def _clean_translation_form(raw: str) -> str:
    form = re.sub(r"<[^>]+>", "", raw).strip()
    match = WIKILINK_RE.match(form)
    if match:
        target = match.group(1)
        form = target.rsplit("|", 1)[-1].strip()
    return form


class WiktionaryProvider(BaseProvider):
    name = "wiktionary"

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        for lang_code in language_codes:
            cache = self._load_cache(lang_code)
            for concept_en in concepts:
                cache_key = concept_en.lower()
                if cache_key in cache:
                    forms = cache[cache_key]
                else:
                    forms = self._lookup(concept_en, lang_code)
                    cache[cache_key] = forms
                yield FetchResult(
                    concept_en=concept_en,
                    language_code=lang_code,
                    forms=forms[:2],
                    source="wiktionary",
                )
            self._save_cache(lang_code, cache)

    def _lookup(self, concept_en: str, lang_code: str) -> List[str]:
        en_wikitext = self._fetch_en_wiktionary_wikitext(concept_en)
        if en_wikitext:
            forms = self._extract_translation_table_forms(en_wikitext, lang_code)
            if forms:
                return forms
            forms = self._extract_ipa_for_lang(en_wikitext, lang_code)
            if forms:
                return forms
        forms = self._try_target_wiktionary(concept_en, lang_code)
        if forms:
            return forms
        forms = self._try_wikipedia_interwiki(concept_en, lang_code)
        return forms

    def _fetch_en_wiktionary_wikitext(self, word: str) -> str:
        try:
            resp = requests.get(
                "https://en.wiktionary.org/w/api.php",
                params={
                    "action": "parse",
                    "page": word,
                    "prop": "wikitext",
                    "format": "json",
                },
                timeout=5,
            )
            if resp.status_code != 200:
                return ""
            data = resp.json()
            wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
            return wikitext if isinstance(wikitext, str) else ""
        except Exception:
            return ""

    def _try_en_wiktionary(self, word: str, lang_code: str) -> List[str]:
        """Return IPA forms from en.wiktionary.org; translation forms are handled in _lookup."""
        wikitext = self._fetch_en_wiktionary_wikitext(word)
        if not wikitext:
            return []
        return self._extract_ipa_for_lang(wikitext, lang_code)

    def _try_target_wiktionary(self, word: str, lang_code: str) -> List[str]:
        try:
            resp = requests.get(
                "https://{}.wiktionary.org/w/api.php".format(lang_code),
                params={
                    "action": "parse",
                    "page": word,
                    "prop": "wikitext",
                    "format": "json",
                },
                timeout=5,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
            return self._extract_any_ipa(wikitext)
        except Exception:
            return []

    def _try_wikipedia_interwiki(self, concept_en: str, lang_code: str) -> List[str]:
        try:
            resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "titles": concept_en,
                    "prop": "langlinks",
                    "lllang": lang_code,
                    "format": "json",
                },
                timeout=5,
            )
            if resp.status_code != 200:
                return []
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                langlinks = page.get("langlinks", [])
                if not langlinks:
                    continue
                target_title = langlinks[0].get("*", "")
                if target_title:
                    return self._fetch_wiki_ipa(target_title, lang_code)
        except Exception:
            pass
        return []

    def _fetch_wiki_ipa(self, title: str, lang_code: str) -> List[str]:
        try:
            resp = requests.get(
                "https://{}.wikipedia.org/w/api.php".format(lang_code),
                params={
                    "action": "parse",
                    "page": title,
                    "prop": "wikitext",
                    "format": "json",
                    "section": 0,
                },
                timeout=5,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
            return self._extract_any_ipa(wikitext)
        except Exception:
            return []

    def _extract_translation_table_forms(self, wikitext: str, lang_code: str) -> List[str]:
        fragments = _WIKTIONARY_FRAGMENTS.get(lang_code, [lang_code])
        forms: List[str] = []
        seen = set()
        for match in WIKTIONARY_TRANSLATION_RE.finditer(wikitext):
            parts = _split_template_args(match.group(1))
            if len(parts) < 3 or parts[0].strip().lower() not in {"t", "t+"}:
                continue
            wikitext_lang = parts[1].strip()
            if not lang_key_matches(wikitext_lang, fragments):
                continue
            form = _clean_translation_form(parts[2])
            if not form or "{" in form or "}" in form:
                continue
            if form not in seen:
                seen.add(form)
                forms.append(form)
        return forms

    def _extract_ipa_for_lang(self, wikitext: str, lang_code: str) -> List[str]:
        fragments = _WIKTIONARY_FRAGMENTS.get(lang_code, [lang_code])
        forms = []
        for m in WIKTIONARY_IPA_RE.finditer(wikitext):
            tag = m.group(1)
            base_tag = tag.split("-", 1)[0]
            if lang_key_matches(tag, fragments) or lang_key_matches(base_tag, fragments):
                raw = m.group(2).strip("/[]")
                if raw:
                    forms.append(raw)
        return forms[:2]

    def _extract_any_ipa(self, wikitext: str) -> List[str]:
        forms = []
        for m in IPA_SLASH_RE.finditer(wikitext):
            forms.append(m.group(1))
            if len(forms) >= 2:
                break
        if not forms:
            for m in IPA_BRACKET_RE.finditer(wikitext):
                forms.append(m.group(1))
                if len(forms) >= 2:
                    break
        return forms[:2]

    def _load_cache(self, lang_code: str) -> Dict[str, List[str]]:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _CACHE_DIR / "wiktionary_{}.json".format(lang_code)
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_cache(self, lang_code: str, cache: Dict[str, List[str]]) -> None:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _CACHE_DIR / "wiktionary_{}.json".format(lang_code)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        except OSError:
            pass
