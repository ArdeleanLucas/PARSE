"""Wikidata provider — SPARQL lexeme lookup for IPA forms."""

import sys
from typing import Dict, Iterator, List

import requests

from .base import BaseProvider, FetchResult

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

CONCEPT_TO_QID = {
    "water": "Q283",
    "fire": "Q3196",
    "tree": "Q10884",
    "stone": "Q8063",
    "blood": "Q7873",
    "bone": "Q265868",
    "eye": "Q4416088",
    "ear": "Q13218254",
    "hand": "Q33767",
    "foot": "Q1310",
    "sun": "Q525",
    "moon": "Q405",
    "star": "Q523",
    "night": "Q8269",
    "day": "Q573",
    "fish": "Q19159",
    "dog": "Q144",
    "bird": "Q5113",
    "person": "Q215627",
    "woman": "Q467",
    "man": "Q8441",
    "name": "Q82799",
    "path": "Q628179",
}

LANG_ISO_TO_WIKIDATA_LID = {
    "ar": "Q13955",
    "fa": "Q9168",
    "ckb": "Q36811",
    "tr": "Q256",
}

_SPARQL_TEMPLATE = """
SELECT ?form ?ipa WHERE {{
  ?lexeme dct:language wd:{lang_qid} ;
          ontolex:sense/wdt:P5137 wd:{concept_qid} ;
          ontolex:lexicalForm ?fn .
  ?fn ontolex:representation ?form .
  OPTIONAL {{ ?fn wdt:P898 ?ipa }}
}} LIMIT 3
"""


class WikidataProvider(BaseProvider):
    name = "wikidata"

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        for lang_code in language_codes:
            lang_qid = LANG_ISO_TO_WIKIDATA_LID.get(lang_code)
            if not lang_qid:
                for concept_en in concepts:
                    yield FetchResult(
                        concept_en=concept_en,
                        language_code=lang_code,
                        forms=[],
                        source="wikidata",
                    )
                continue

            for concept_en in concepts:
                concept_qid = CONCEPT_TO_QID.get(concept_en)
                if not concept_qid:
                    yield FetchResult(
                        concept_en=concept_en,
                        language_code=lang_code,
                        forms=[],
                        source="wikidata",
                    )
                    continue

                forms = self._query(lang_qid, concept_qid)
                yield FetchResult(
                    concept_en=concept_en,
                    language_code=lang_code,
                    forms=forms,
                    source="wikidata",
                )

    def _query(self, lang_qid: str, concept_qid: str) -> List[str]:
        sparql = _SPARQL_TEMPLATE.format(lang_qid=lang_qid, concept_qid=concept_qid)
        try:
            resp = requests.get(
                SPARQL_ENDPOINT,
                params={"query": sparql, "format": "json"},
                headers={"User-Agent": "PARSE-LexemeFetcher/1.0"},
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            forms = []
            for binding in data.get("results", {}).get("bindings", []):
                ipa = binding.get("ipa", {}).get("value", "")
                form = binding.get("form", {}).get("value", "")
                val = ipa if ipa else form
                if val and val not in forms:
                    forms.append(val)
            return forms
        except Exception as exc:
            print("[wikidata] SPARQL failed: {}".format(exc), file=sys.stderr)
            return []
