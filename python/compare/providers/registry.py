"""Provider registry — orchestrates all providers in priority order."""

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .asjp import ASJP_CONCEPT_MAP, AsjpProvider
from .cldf import CldfProvider
from .csv_override import CsvOverrideProvider, _OVERRIDE_PATH
from .grok_llm import GrokLlmProvider, _get_auth_token as _grok_get_auth_token
from .lingpy_wordlist import LingPyCldfProvider
from .literature import LiteratureProvider
from .pycldf_provider import PycldfProvider
from .pylexibank_provider import PYLEXIBANK_AVAILABLE, PylexibankProvider
from .wikidata import CONCEPT_TO_QID, WikidataProvider
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
    "literature",
    "grok_llm",         # LLM fallback for anything not found above
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
            "literature": LiteratureProvider(),
            "grok_llm": GrokLlmProvider(ai_config or {}),
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
        detailed = self.fetch_all_detailed(
            concepts=concepts,
            language_codes=language_codes,
            language_meta=language_meta,
            priority_order=priority_order,
            stop_on_first_hit=stop_on_first_hit,
            progress_callback=progress_callback,
        )
        return detailed["results"]

    def fetch_all_detailed(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
        priority_order: Optional[List[str]] = None,
        stop_on_first_hit: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """Return populated forms plus provider diagnostics.

        The core ``results`` payload is identical to ``fetch_all()``. The
        extra keys make silent-empty CLEF runs debuggable from the backend:
        ``provider_errors`` surfaces raised exceptions or explicit
        ``FetchResult.error`` messages, while ``warnings`` captures common
        readiness / coverage gaps (missing local datasets, missing API keys,
        concept maps that do not cover the remaining concepts, etc.).
        """
        order = list(priority_order or PROVIDER_PRIORITY)
        results: Dict[str, Dict[str, List[FormWithSources]]] = {lc: {} for lc in language_codes}
        total_pairs = max(1, len(concepts) * len(language_codes))
        done = 0
        provider_errors: List[str] = []
        warnings: List[str] = []
        providers_attempted: List[str] = []
        providers_returning_forms: List[str] = []
        provider_stats: Dict[str, Dict[str, int]] = {}

        for provider_name in order:
            provider = self._providers.get(provider_name)
            if not provider:
                warnings.append(
                    "Requested CLEF provider '{0}' is not registered.".format(provider_name)
                )
                continue

            remaining_concepts = concepts if not stop_on_first_hit else [
                concept_en
                for concept_en in concepts
                if any(not results[lang_code].get(concept_en) for lang_code in language_codes)
            ]
            if not remaining_concepts:
                break

            providers_attempted.append(provider_name)
            warnings.extend(self._provider_preflight_warnings(provider_name, provider, remaining_concepts))
            stats = {
                "concepts_requested": len(remaining_concepts),
                "pairs_requested": len(remaining_concepts) * len(language_codes),
                "results_seen": 0,
                "pairs_with_forms": 0,
                "forms_emitted": 0,
            }
            provider_had_forms = False

            try:
                iterator = provider.fetch(remaining_concepts, language_codes, language_meta) or ()
                for result in iterator:
                    stats["results_seen"] += 1
                    if result.error:
                        provider_errors.append(
                            "{0}: {1}".format(provider_name, result.error)
                        )
                    if result.forms:
                        provider_had_forms = True
                        stats["pairs_with_forms"] += 1
                        stats["forms_emitted"] += len(result.forms)
                        existing = results[result.language_code].get(result.concept_en, [])
                        source = result.source or provider_name
                        if not existing:
                            results[result.language_code][result.concept_en] = [
                                {"form": form, "sources": [source]}
                                for form in result.forms
                            ]
                        elif not stop_on_first_hit:
                            merged = list(existing)
                            by_form = {entry["form"]: entry for entry in merged}
                            for form in result.forms:
                                if form in by_form:
                                    if source not in by_form[form]["sources"]:
                                        by_form[form]["sources"].append(source)
                                else:
                                    entry = {"form": form, "sources": [source]}
                                    merged.append(entry)
                                    by_form[form] = entry
                            results[result.language_code][result.concept_en] = merged
                    done += 1
                    if progress_callback and done % 5 == 0:
                        progress_callback(done / total_pairs * 100, "{}: {}".format(provider_name, result.concept_en))
            except Exception as exc:
                print("[registry] provider {} failed: {}".format(provider_name, exc), file=sys.stderr)
                provider_errors.append("{0}: {1}".format(provider_name, exc))

            if provider_had_forms:
                providers_returning_forms.append(provider_name)
            provider_stats[provider_name] = stats

        return {
            "results": results,
            "providers_requested": list(order),
            "providers_attempted": providers_attempted,
            "providers_returning_forms": providers_returning_forms,
            "provider_errors": _dedupe_preserve(provider_errors),
            "warnings": _dedupe_preserve(warnings),
            "provider_stats": provider_stats,
        }

    def _provider_preflight_warnings(
        self,
        provider_name: str,
        provider: Any,
        concepts: List[str],
    ) -> List[str]:
        warnings: List[str] = []
        try:
            if provider_name == "csv_override":
                if not _OVERRIDE_PATH.exists():
                    warnings.append(
                        "csv_override: no override file found at {0}.".format(_OVERRIDE_PATH)
                    )
            elif provider_name in {"lingpy_wordlist", "pycldf"}:
                finder = getattr(provider, "_find_metadata_files", None)
                metadata_files = list(finder()) if callable(finder) else []
                data_dir = getattr(provider, "_data_dir", None)
                data_dir_label = data_dir if isinstance(data_dir, Path) else "config/lexibank_data"
                if not metadata_files:
                    warnings.append(
                        "{0}: no local CLDF datasets found under {1}. Drop a Lexibank dataset clone into that directory to enable this provider.".format(
                            provider_name,
                            data_dir_label,
                        )
                    )
            elif provider_name == "pylexibank":
                if not PYLEXIBANK_AVAILABLE:
                    warnings.append(
                        "pylexibank: optional pylexibank package is not installed (install with `pip install pylexibank` if you want to use installed dataset packages)."
                    )
                else:
                    datasets = provider._load_installed_datasets()
                    if not datasets:
                        warnings.append(
                            "pylexibank: no installed pylexibank datasets were found."
                        )
            elif provider_name == "asjp":
                overlap_count = sum(1 for concept_en in concepts if concept_en in ASJP_CONCEPT_MAP)
                if overlap_count < len(concepts):
                    warnings.append(
                        "asjp: ASJP's built-in 40-concept Swadesh map covers {0} of your {1} requested concepts (this is normal — ASJP is a small reference set, not a coverage gap).".format(
                            overlap_count,
                            len(concepts),
                        )
                    )
            elif provider_name == "wikidata":
                overlap_count = sum(1 for concept_en in concepts if concept_en in CONCEPT_TO_QID)
                if overlap_count < len(concepts):
                    warnings.append(
                        "wikidata: Wikidata's built-in concept→QID map covers {0} of your {1} requested concepts (this is normal — Wikidata coverage depends on the bundled concept map, not a runtime failure).".format(
                            overlap_count,
                            len(concepts),
                        )
                    )
            elif provider_name == "grok_llm":
                ai_config = getattr(provider, "_ai_config", {}) or {}
                xai_key = _grok_get_auth_token("xai") or ai_config.get("xai_api_key")
                openai_key = _grok_get_auth_token("openai") or ai_config.get("openai_api_key")
                if not xai_key and not openai_key:
                    warnings.append(
                        "grok_llm: no xAI or OpenAI API key configured. Open the Settings tab in CLEF Configure to add one, or skip this provider."
                    )
        except Exception as exc:
            warnings.append(
                "{0}: readiness diagnostics failed: {1}".format(provider_name, exc)
            )
        return warnings


def _dedupe_preserve(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
