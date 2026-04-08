"""ASJP provider — queries the ASJP REST API at asjp.clld.org."""

import json
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import requests

from .base import BaseProvider, FetchResult

_CACHE_DIR = Path(__file__).resolve().parents[3] / "config" / "cache"

ASJP_CONCEPT_MAP = {
    "I": 1, "you": 2, "we": 3, "one": 8, "two": 9,
    "person": 16, "fish": 18, "dog": 20, "louse": 21,
    "tree": 22, "leaf": 24, "blood": 32, "bone": 33,
    "horn": 35, "ear": 38, "eye": 39, "nose": 41,
    "tooth": 43, "tongue": 44, "hand": 45, "knee": 47,
    "heart": 49, "liver": 50, "drink": 51, "see": 54,
    "hear": 55, "die": 57, "sun": 62, "moon": 63,
    "star": 64, "water": 66, "stone": 67, "fire": 68,
    "path": 69, "mountain": 70, "night": 73, "full": 75,
    "new": 76, "name": 82,
}


class AsjpProvider(BaseProvider):
    name = "asjp"

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        for lang_code in language_codes:
            lang_data = self._get_language_data(lang_code, language_meta)
            for concept_en in concepts:
                concept_id = ASJP_CONCEPT_MAP.get(concept_en)
                if concept_id is None:
                    yield FetchResult(
                        concept_en=concept_en,
                        language_code=lang_code,
                        forms=[],
                        source="asjp",
                    )
                    continue
                forms = self._extract_forms(lang_data, concept_id, concept_en)
                yield FetchResult(
                    concept_en=concept_en,
                    language_code=lang_code,
                    forms=forms,
                    source="asjp",
                )

    def _get_language_data(self, lang_code: str, language_meta: Dict) -> Optional[dict]:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _CACHE_DIR / "asjp_{}.json".format(lang_code)
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        lang_name = language_meta.get(lang_code, {}).get("name", "")
        data = self._fetch_from_api(lang_code, lang_name)
        if data is not None:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            except OSError:
                pass
        return data

    def _fetch_from_api(self, lang_code: str, lang_name: str) -> Optional[dict]:
        # Try searching by ISO code
        try:
            url = "https://asjp.clld.org/languages.json"
            resp = requests.get(url, params={"iso": lang_code}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    return data
        except Exception as exc:
            print("[asjp] API search failed for {}: {}".format(lang_code, exc), file=sys.stderr)

        # Try searching by language name
        if lang_name:
            try:
                url = "https://asjp.clld.org/languages.json"
                resp = requests.get(url, params={"name": lang_name}, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data:
                        return data
            except Exception as exc:
                print("[asjp] API name search failed for {}: {}".format(lang_name, exc), file=sys.stderr)

        return None

    def _extract_forms(self, lang_data: Optional[dict], concept_id: int, concept_en: str) -> List[str]:
        if not lang_data:
            return []
        forms = []
        # Handle various ASJP JSON response structures
        wordlists = lang_data if isinstance(lang_data, list) else [lang_data]
        for entry in wordlists:
            if not isinstance(entry, dict):
                continue
            # Check for concept match in various possible structures
            for key in ("words", "items", "data"):
                items = entry.get(key, [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_concept = item.get("parameter_id") or item.get("concept_id") or item.get("meaning_id")
                    if str(item_concept) == str(concept_id) or item.get("meaning") == concept_en:
                        form = item.get("form") or item.get("word") or item.get("transcription") or ""
                        if form and isinstance(form, str):
                            forms.append(form)
        return forms
