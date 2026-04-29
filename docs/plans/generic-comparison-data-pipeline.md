# Generic Comparison Data Pipeline for PARSE — Design Document

**MC-294**
**Status:** Design Complete / historical reference
**Author:** dr-kurd (spawned Opus session equivalent via orchestration)
**Date:** 2026-04-08
**Branch target:** `feat/generic-comparison-pipeline` (from `origin/main`; historical note: `feat/parse-react-vite` has been merged and deleted)

> **Update (post-pivot merge):** core provider plumbing now lives on `main` under `python/compare/providers/`. Use this design doc for future expansion work, but branch from `origin/main`, not the deleted pivot lane.

## Executive Summary

The existing `contact_lexeme_fetcher.py` (from the contact-lexeme-fetcher.md plan) is a good starting point but is tightly coupled to four specific contact languages. This document generalizes it into a **pluggable, provider-based pipeline** that can pull lexical, IPA, and cognate data for arbitrary languages. It supports the review tool's lexical comparison, BorrowingPanel similarity bars, and the thesis §4.4 borrowing adjudication with high-quality, validated reference forms.

The pipeline uses a priority fallback chain, strict IPA validation, caching, and a language registry. It directly supports the firm PARSE audio rule (full recordings + timestamps only) and the wav2vec2-xlsr-53-espeak-cv-ft model for IPA.

## Provider Registry Architecture

```python
# python/compare/providers/registry.py (new)
class ProviderRegistry:
    def __init__(self, ai_config: Dict):
        self.providers = {}
        self.register('csv_override', CsvOverrideProvider())
        self.register('asjp', AsjpProvider())
        self.register('wiktionary', WiktionaryProvider())
        self.register('wikipedia', WikipediaProvider())
        self.register('wikidata', WikidataProvider())
        self.register('grok_llm', GrokLlmProvider(ai_config))  # xAI primary
        self.register('literature', LiteratureReviewProvider())  # uses our tools

    def fetch(self, concepts: List[str], languages: List[str], priority_order: List[str] = None) -> Iterator[FetchResult]:
        ...
```

**Language Registry** (config/languages.json or embedded):
```json
{
  "ar": {"name": "Arabic", "iso": "ar", "script_note": "MSA + dialect variants", "glottocode": "arab1395"},
  "fa": {"name": "Persian", "iso": "fa", "script_note": "Tehran standard", "glottocode": "pers1243"},
  ...
}
```

## Per-Suggestion Application

### 1. Wikipedia / MediaWiki API
**Application:** Provider queries `[iso].wikipedia.org/w/api.php` with concept as title or "List of [concept] in [language]". Extracts pronunciation from infobox or "Pronunciation" section using parsoid or regex on wikitext. Falls back to English Wikipedia for gloss translation.

**Code sketch:**
```python
def fetch_wikipedia(self, concept: str, lang_code: str) -> List[str]:
    url = f"https://{lang_code}.wikipedia.org/w/api.php?action=query&titles={concept}&prop=extracts&format=json"
    # parse for {{IPA|...}} or audio links → STT fallback
```

**Pros:** Broad coverage, up-to-date, free. Good for major languages.
**Cons:** Inconsistent structure across language editions; noisy for low-resource languages.
**Broad languages:** Excellent for major families; poor for dialects (use with Grok LLM fallback).
**Integration:** Second in priority after CSV/ASJP. Feeds IPA directly to sil_contact_languages.json.
**Thesis:** Provides transparent, citable sources for comparative tables in Ch4.

### 2. xAI/Grok "Grok LLM" mode via xAI API
**Application:** Primary LLM provider. System prompt "You are Grok LLM, a linguistics database specialized in IPA for Swadesh concepts..." with few-shot examples for consistent JSON output. Uses the existing xai:default profile and grok-4.20-0309-reasoning model. Batch 10-20 concepts per call.

**Code sketch:**
```python
def _fetch_batch_grok_llm(self, batch: List[str], lang: Dict):
    prompt = f"Concept list: {batch}\nLanguage: {lang['name']} ({lang['iso']})\nReturn ONLY JSON array of IPA arrays."
    response = xai_client.chat.completions.create(model="grok-4.20-0309-reasoning", messages=[{"role": "system", "content": SYSTEM_PROMPT}, ...])
    parsed = json.loads(response.choices[0].message.content)
    return {concept: forms for concept, forms in zip(batch, parsed)}
```

**Pros:** High quality for rare variants, reasoning for dialect notes, no rate limit issues with xAI key.
**Cons:** Non-deterministic (mitigated by temperature=0.1 + validation retry).
**Broad languages:** Best for low-resource; can reason about related dialects (e.g., Faili Arabic influence).
**Integration:** Default primary provider. Validates against IPA_PATTERN before writing.
**Thesis:** Allows dynamic addition of new contact languages without manual data entry.

### 3. ASJP Database
**Application:** Offline download of ASJP wordlist.tsv. Index by language ISO/glottocode and concept (mapped from English gloss). Provides 40-item Swadesh overlap.

**Code sketch:**
```python
def fetch_asjp(self, concepts: List[str], lang_code: str) -> List[str]:
    df = pd.read_csv(self.asjp_path, sep='\t')
    row = df[(df['ISO'] == lang_code) & (df['CONCEPT'].isin(concepts))]
    return row['FORM'].tolist()  # already in rough IPA-like transcription
```

**Pros:** Zero cost, fast, consistent for basic vocabulary.
**Cons:** Limited to 40 concepts; transcription is broad and not always standard IPA.
**Broad languages:** Excellent coverage (7000+ languages).
**Integration:** High priority after CSV. Normalizes transcription to match IPA_PATTERN.
**Thesis:** Provides reproducible baseline for all 82 concepts where possible.

### 4. Lexibank / CLDF Repositories
**Application:** Clone or API access to CLDF datasets. Query by concept ID (from concepts.csv) and language glottocode. Many datasets include IPA.

**Pros:** High scholarly quality, standardized, citable.
**Cons:** Not real-time; requires local mirror or GitHub raw access.
**Broad languages:** Strong for documented languages; gaps in obscure dialects.
**Integration:** Offline-first provider. Updates enrichments with source citation.

### 5. Wikidata + Glottolog
**Application:** Query Wikidata SPARQL or API for lexeme forms linked to concepts (P5137 for concept). Glottolog for language classification and links to wordlists.

**Pros:** Linked open data, machine-readable, growing rapidly.
**Cons:** Incomplete for IPA in many entries.
**Broad languages:** Good for classification puzzle aspect of SK varieties.

### 6. Research Literature APIs / literature-review tools
**Application:** Use our built-in literature-review skill (Semantic Scholar, OpenAlex, Crossref) to find papers with wordlists for specific languages. Extract tables or use web_fetch to parse PDFs (with pdf tool). Ingest into the pipeline as "literature" provider.

**Pros:** Highest academic rigor, directly supports thesis citations.
**Cons:** Slow, requires human validation for extraction errors.
**Broad languages:** Ideal for specialized dialect data (e.g., Fattah groups, Belelli 2019).
**Integration:** Lowest priority fallback; results cached with DOI references in the JSON.

## Provider Comparison Table

| Provider | Latency | Coverage (broad) | Accuracy | Cost | Best For |
|----------|---------|------------------|----------|------|----------|
| CSV Override | Instant | Full | Highest | 0 | Researcher-provided gold data |
| ASJP | Instant | Very High | Medium | 0 | Baseline Swadesh |
| Grok LLM (xAI) | 2-8s/batch | Highest | High (with validation) | API quota | Rare dialects, variants |
| Wiktionary/Wikipedia | 1-3s | High | Medium-High | 0 | Major languages |
| Lexibank/CLDF | Instant (local) | Medium-High | Very High | 0 | Scholarly citations |
| Literature APIs | 10-60s | Variable | Highest (with review) | 0 | Thesis evidence |

## Caching, Validation, and Data Flow

- **Cache:** `config/cache/comparison_forms/{lang_iso}.json` with ETag or last-modified.
- **Validation:** All forms must match the IPA_PATTERN regex from the original plan. Retry with different provider on failure.
- **Output:** Generalized `comparison_data.json` (extends sil_contact_languages.json) with source, confidence, citation.
- **Pipeline trigger:** New `/api/compute/comparison-data` endpoint that runs the registry for specified languages/concepts, then triggers cognate recompute.
- **UI:** Extend ContactLexemePanel to show provider breakdown and "Refresh from [provider]" buttons.

## Thesis Relevance (§4.4)

The pipeline makes borrowing adjudication empirical rather than manual. Similarity scores now have traceable sources (e.g., "Grok LLM + ASJP, validated against Belelli 2019"). This strengthens the Bayesian phylogeny by quantifying contact effects without outgroups. All sources are documented in the output JSON for the methodology appendix.

## Implementation Roadmap (estimated effort)

1. MC-294.1: Provider registry + Grok LLM/xAI (4h)
2. MC-294.2: ASJP + Wikipedia providers + validation (3h)
3. MC-294.3: Literature and CLDF/Wikidata (3h)
4. MC-294.4: Server endpoints, caching, generalize fetcher (2h)
5. MC-294.5: UI updates to ContactLexemePanel and review tool (2h)
6. MC-294.6: Tests, integration with cognate compute, PR (2h)

**Total:** ~16 hours. Spawn sub-agents per file ownership rule. Next suggested MC-295: Implement provider registry core.

**File written:** `docs/plans/generic-comparison-data-pipeline.md`

This design makes the pipeline robust, extensible, and aligned with the thesis's rigorous comparative method. Ready for implementation. 
