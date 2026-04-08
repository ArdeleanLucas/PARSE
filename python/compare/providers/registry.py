"""Provider registry — orchestrates all providers in priority order."""

import sys
from typing import Callable, Dict, List, Optional

from .asjp import AsjpProvider
from .cldf import CldfProvider
from .csv_override import CsvOverrideProvider
from .grokipedia import GrokipediaProvider
from .literature import LiteratureProvider
from .wikidata import WikidataProvider
from .wiktionary import WiktionaryProvider

PROVIDER_PRIORITY = [
    "csv_override", "asjp", "cldf", "wikidata", "wiktionary", "grokipedia", "literature",
]


class ProviderRegistry:
    def __init__(self, ai_config: Dict = None):
        self._providers = {
            "csv_override": CsvOverrideProvider(),
            "asjp": AsjpProvider(),
            "cldf": CldfProvider(),
            "wikidata": WikidataProvider(),
            "wiktionary": WiktionaryProvider(),
            "grokipedia": GrokipediaProvider(ai_config or {}),
            "literature": LiteratureProvider(),
        }

    def fetch_all(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
        priority_order: Optional[List[str]] = None,
        stop_on_first_hit: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Returns: {lang_code: {concept_en: [forms]}}
        Runs providers in priority order. If stop_on_first_hit=True,
        once a concept x lang has forms from any provider, skip remaining providers for it.
        """
        order = priority_order or PROVIDER_PRIORITY
        results: Dict[str, Dict[str, List[str]]] = {lc: {} for lc in language_codes}
        total = len(concepts) * len(language_codes)
        done = 0

        for provider_name in order:
            provider = self._providers.get(provider_name)
            if not provider:
                continue
            remaining_concepts = concepts if not stop_on_first_hit else [
                c for c in concepts
                if any(not results[lc].get(c) for lc in language_codes)
            ]
            if not remaining_concepts:
                break
            try:
                for result in provider.fetch(remaining_concepts, language_codes, language_meta):
                    if result.forms:
                        existing = results[result.language_code].get(result.concept_en, [])
                        if not existing or not stop_on_first_hit:
                            results[result.language_code][result.concept_en] = result.forms
                    done += 1
                    if progress_callback and done % 5 == 0:
                        progress_callback(done / total * 100, "{}: {}".format(provider_name, result.concept_en))
            except Exception as e:
                print("[registry] provider {} failed: {}".format(provider_name, e), file=sys.stderr)
                continue

        return results
