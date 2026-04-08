"""Literature provider — searches Semantic Scholar for papers with wordlists."""

import re
import sys
from typing import Dict, Iterator, List

import requests

from .base import BaseProvider, FetchResult

SS_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"

IPA_IN_SLASH = re.compile(r'/([a-z\u00e6\u0251\u025b\u026a\u028a\u0259\u02d0\u02c8\u02cc\u0294\u0295\u0283\u0292\u0263 ]{1,20})/')


class LiteratureProvider(BaseProvider):
    name = "literature"

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        for lang_code in language_codes:
            lang_name = language_meta.get(lang_code, {}).get("name", lang_code)
            for concept_en in concepts:
                query = '"{}" wordlist "{}" IPA'.format(lang_name, concept_en)
                forms = self._search_papers(query, concept_en)
                yield FetchResult(
                    concept_en=concept_en,
                    language_code=lang_code,
                    forms=forms,
                    source="literature",
                )

    def _search_papers(self, query: str, concept_en: str) -> List[str]:
        try:
            resp = requests.get(
                SS_ENDPOINT,
                params={
                    "query": query,
                    "fields": "title,year,openAccessPdf",
                    "limit": 3,
                },
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            papers = resp.json().get("data", [])
            for paper in papers:
                pdf_info = paper.get("openAccessPdf") or {}
                pdf_url = pdf_info.get("url")
                if pdf_url:
                    forms = _extract_ipa_from_pdf_url(pdf_url, concept_en)
                    if forms:
                        return forms
        except Exception as exc:
            print("[literature] search failed: {}".format(exc), file=sys.stderr)
        return []


def _extract_ipa_from_pdf_url(pdf_url: str, concept_en: str) -> List[str]:
    try:
        resp = requests.get(pdf_url, timeout=10)
        text = resp.content.decode("utf-8", errors="ignore")
        idx = text.lower().find(concept_en.lower())
        if idx == -1:
            return []
        window = text[max(0, idx - 50) : idx + 300]
        return [m.group(1) for m in IPA_IN_SLASH.finditer(window)][:2]
    except Exception:
        return []
