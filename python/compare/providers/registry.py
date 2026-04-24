"""Provider registry — orchestrates all providers in priority order."""

import sys
from typing import Any, Callable, Dict, List, Optional

from .asjp import AsjpProvider
from .cldf import CldfProvider
from .csv_override import CsvOverrideProvider
from .grokipedia import GrokipediaProvider
from .lingpy_wordlist import LingPyCldfProvider
from .literature import LiteratureProvider
from .pycldf_provider import PycldfProvider
from .pylexibank_provider import PylexibankProvider
from .wikidata import WikidataProvider
from .wiktionary import WiktionaryProvider

PROVIDER_PRIORITY = [
    "csv_override",
    "lingpy_wordlist",  # local CLDF datasets via LingPy — highest offline quality
    "pycldf",           # same datasets via pycldf — adds citation metadata
    "pylexibank",       # installed pylexibank datasets (optional, may be no-op)
    "asjp",             # ASJP REST API — 40 Swadesh concepts
    "cldf",             # HTTP CSV download fallback
    "wikidata",
    "wiktionary",
    "grokipedia",       # LLM fallback for anything not found above
    "literature",
]


# Public shape of a single populated form as emitted by the registry and
# persisted into sil_contact_languages.json. ``sources`` is a sorted list
# of provider names that independently contributed this exact form (dedup
# is case-sensitive on the form string). Readers MUST also accept bare
# strings for backward compatibility with pre-provenance data.
FormWithSources = Dict[str, Any]  # {"form": str, "sources": List[str]}


class ProviderRegistry:
    def __init__(self, ai_config: Dict = None):
        self._providers = {
            "csv_override": CsvOverrideProvider(),
            "lingpy_wordlist": LingPyCldfProvider(),
            "pycldf": PycldfProvider(),
            "pylexibank": PylexibankProvider(),
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
    ) -> Dict[str, Dict[str, List[FormWithSources]]]:
        """
        Returns: {lang_code: {concept_en: [{"form": str, "sources": [provider, ...]}, ...]}}

        Runs providers in priority order. When ``stop_on_first_hit=True``
        (the default), once a concept x lang has any forms the remaining
        providers are skipped for that pair; the winning forms carry the
        single provider name that produced them. When
        ``stop_on_first_hit=False`` all providers run and we union the
        form lists, deduping by form string and merging the ``sources``
        list so a form emitted by two providers carries both attributions.
        """
        order = priority_order or PROVIDER_PRIORITY
        results: Dict[str, Dict[str, List[FormWithSources]]] = {lc: {} for lc in language_codes}
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
                        source = result.source or provider_name
                        if not existing:
                            results[result.language_code][result.concept_en] = [
                                {"form": f, "sources": [source]} for f in result.forms
                            ]
                        elif not stop_on_first_hit:
                            # Union: preserve the existing ordering, add
                            # new forms at the end, merge sources for
                            # duplicates. Keeps priority-order intact so
                            # the "primary" citation stays first.
                            merged = list(existing)
                            by_form = {entry["form"]: entry for entry in merged}
                            for f in result.forms:
                                if f in by_form:
                                    if source not in by_form[f]["sources"]:
                                        by_form[f]["sources"].append(source)
                                else:
                                    entry = {"form": f, "sources": [source]}
                                    merged.append(entry)
                                    by_form[f] = entry
                            results[result.language_code][result.concept_en] = merged
                    done += 1
                    if progress_callback and done % 5 == 0:
                        progress_callback(done / total * 100, "{}: {}".format(provider_name, result.concept_en))
            except Exception as e:
                print("[registry] provider {} failed: {}".format(provider_name, e), file=sys.stderr)
                continue

        return results
