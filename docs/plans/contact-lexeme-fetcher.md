# Contact Language Lexeme Fetcher — Design Plan

**Status:** Partially implemented / design reference
**Priority:** High — required for borrowing adjudication in thesis
**Branch target:** branch from `origin/main` (historical note: `feat/parse-react-vite` was the old pivot lane and has been deleted)
**Thesis relevance:** §4.4 PARSE pipeline — similarity scores underpin the borrowing detection in the comparative analysis

> **Update (post-pivot merge):** provider registry code, `ContactLexemePanel`, provider tests, and coverage/fetch endpoints now exist on `main`. Use this document as a design/reference plan for the remaining fetch-and-fill work, not as a reason to branch from the deleted pivot lane.

---

## Problem Statement

`compute_similarity_scores()` in `python/compare/cognate_compute.py` computes phonetic edit distances between SK field recordings and contact language reference forms. However, `sil_contact_languages.json` has **empty `concepts: {}`** for all four contact languages (Arabic, Persian, Central Kurdish, Turkish). Without reference forms, every similarity score returns `has_reference_data: false` and `score: null` — the borrowing adjudication panel is effectively blind.

The missing piece is an **automated pipeline** that populates those contact forms for the 82 concepts in `concepts.csv`.

---

## Architecture Overview

```
concepts.csv (82 concepts, English labels)
        │
        ▼
[D1] contact_lexeme_fetcher.py
        │  fetches IPA per concept per language
        │  sources: LLM (primary) + Wiktionary (fallback)
        │
        ▼
sil_contact_languages.json  ←── written incrementally
  {
    "ar": { "concepts": { "water": ["maːʔ", "miːah"], ... } },
    "fa": { "concepts": { "water": ["aːb"], ... } },
    ...
  }
        │
        ▼
[D2] _compute_cognates() in server.py
     calls compute_similarity_scores() with populated refs
        │
        ▼
enrichments.similarity[concept][speaker][language]
  { "score": 0.23, "has_reference_data": true }
        │
        ▼
[D3] BorrowingPanel.tsx — similarity bars now have real data
     ContactLexemePanel.tsx — fill-status dashboard + re-fetch UI
```

---

## Data Sources

### Primary: LLM Agent (provider-aware, uses configured AI)

Uses the same LLM provider configured in `config/ai_config.json` (currently xAI/Grok).

**Prompt template (per concept, per language):**

```
You are a phonetics assistant. Provide IPA pronunciation(s) for the following concept in the specified language.

Concept: "{concept_en}" (Swadesh concept — basic vocabulary item)
Language: {language_name} ({iso_code})
Script note: {script_note}

Rules:
1. Return ONLY a JSON array of IPA strings, no prose.
2. Use broad transcription (phonemic), not narrow phonetic.
3. Include 1–3 common variants if they exist (dialect variation for Arabic).
4. If the concept has no native word (cultural gap), return [].
5. Diacritics: use standard IPA (e.g., ː for length, ʔ for glottal stop).

Example output: ["maːʔ", "miːah"]
Output:
```

**Script notes per language:**
- Arabic (`ar`): "Standard Arabic (MSA). Arabic words often have both fusha and common spoken variants."
- Persian (`fa`): "Standard Tehran Persian. Romanize all output as IPA, not Perso-Arabic script."
- Central Kurdish/Sorani (`ckb`): "Sorani Kurdish dialect. Related to the target language — cognates expected."
- Turkish (`tr`): "Istanbul Turkish. Agglutinative — give the bare root/stem form."

**Implementation:**
- Batch 82 concepts into groups of 10 per LLM call to reduce latency
- Validate output is a JSON array of IPA strings (regex: `^[a-zæɑɛɪʊøœɯɨəɐɜɞɵʏʑʐʒʃʂʈɖɗɓɠɧɦɣɤχħɬɮɹɺɻɽʈɸβθðʁɴɲŋɱʋʍẃẁɰʔʕʢʡǀǂǃǁːˈˌ͡ ]+$`)
- On validation failure: log and fall back to Wiktionary for that concept

### Fallback: Wiktionary API

Free, no authentication, covers Arabic and Persian well.

```python
# Wiktionary REST API
GET https://en.wiktionary.org/api/rest_v1/page/summary/{word}

# Alternative: parse IPA from wikitext
GET https://en.wiktionary.org/w/api.php?action=query&titles={word}&prop=revisions&rvprop=content&format=json
```

**IPA extraction:** Parse `{{IPA|ar|/.../ }}` or `{{IPA|fa|/.../ }}` markers from wikitext.

**Limitation:** Requires knowing the target-language word first (we have the English gloss, not the Arabic/Persian word). Use the LLM to generate the word, then Wiktionary to verify/get IPA.

### Manual Override: CSV Import

Researcher can provide a pre-built `contact_forms_override.csv`:

```csv
concept_en,ar,fa,ckb,tr
water,"maːʔ,miːah",aːb,aːw,su
fire,naːr,aːtaʃ,aːgiː,ateʃ
```

The fetcher reads this as the highest-priority source (overrides both LLM and Wiktionary).

---

## Implementation Plan

### D1 — `python/compare/contact_lexeme_fetcher.py` (new file)

**Owner:** ParseBuilder  
**Estimated effort:** 3–4 hours  
**Dependencies:** `ai/` module (existing), `sil_contact_languages.json`, `concepts.csv`

```python
"""
contact_lexeme_fetcher.py — Populate sil_contact_languages.json with IPA forms.

Usage (standalone):
    python compare/contact_lexeme_fetcher.py \
        --concepts ../../concepts.csv \
        --output ../../config/sil_contact_languages.json \
        --languages ar fa ckb \
        --provider llm  # or: wiktionary, csv
"""
```

**Public interface:**

```python
@dataclass
class FetchResult:
    concept_en: str
    language_code: str
    forms: List[str]          # IPA strings, may be empty
    source: str               # "llm", "wiktionary", "csv", "cached"
    error: Optional[str]

def fetch_contact_forms(
    concepts: List[str],           # English concept labels from concepts.csv
    language_codes: List[str],     # e.g. ["ar", "fa", "ckb"]
    provider: str,                 # "llm", "wiktionary", "csv", "auto"
    ai_config: Dict,               # from config/ai_config.json
    csv_override_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Iterator[FetchResult]:
    """Yields FetchResult for each concept×language combination."""

def merge_results_into_config(
    results: Iterable[FetchResult],
    config_path: Path,
    overwrite: bool = False,       # if False, skip concepts already having forms
) -> Dict[str, int]:               # returns {"ar": 41, "fa": 38, ...} filled counts
```

**Key internals:**

```python
def _fetch_batch_via_llm(
    concepts: List[str],
    language_code: str,
    language_name: str,
    script_note: str,
    ai_config: Dict,
    batch_size: int = 10,
) -> Dict[str, List[str]]:
    """Calls LLM for up to batch_size concepts at once.
    Returns {concept_en: [ipa_form, ...]}."""

def _fetch_via_wiktionary(
    concept_en: str,
    language_code: str,
    llm_word: Optional[str] = None,  # if LLM already provided the word
) -> List[str]:
    """Queries Wiktionary for the word, extracts IPA."""

def _validate_ipa_form(form: str) -> bool:
    """Returns True if the string looks like valid broad IPA."""

def _ipa_from_arabic_script(arabic_text: str) -> str:
    """Rough rule-based Arabic script → IPA (existing logic in cross_speaker_match.py)."""
```

---

### D2 — `python/server.py` — new compute type `"contact-lexemes"`

**Owner:** ParseBuilder  
**Estimated effort:** 1 hour  
**Scope:** Python backend (FROZEN rule exception — this adds a new compute type, does not modify existing endpoints)

Add handler in `_run_compute_job()`:

```python
elif normalized_type == "contact-lexemes":
    result = _compute_contact_lexemes(job_id, payload)
```

New function:

```python
def _compute_contact_lexemes(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetches IPA forms for contact languages and writes to sil_contact_languages.json.

    Payload fields:
      provider: "llm" | "wiktionary" | "csv" | "auto"   (default: "auto")
      languages: ["ar", "fa", "ckb", "tr"]               (default: all configured)
      overwrite: bool                                     (default: false)
      csv_path: str                                       (optional, for "csv" provider)
    """
```

**Progress reporting:**
- 0%: starting
- 2% per concept processed (82 concepts × ~4 languages = ~328 steps at ~0.3% each — report per concept batch)
- 95%: writing to config file
- 100%: done

**Response shape:**
```json
{
  "filled": {"ar": 41, "fa": 38, "ckb": 22, "tr": 18},
  "skipped": {"ar": 3, "fa": 0, "ckb": 7},
  "errors": [],
  "config_path": "config/sil_contact_languages.json"
}
```

---

### D3 — `src/api/client.ts` — new API function

**Owner:** ParseBuilder

```typescript
// Add to existing compute helpers:
export async function startContactLexemeFetch(options: {
  provider?: "llm" | "wiktionary" | "csv" | "auto";
  languages?: string[];
  overwrite?: boolean;
}): Promise<ComputeJob> {
  return startCompute("contact-lexemes", options);
}
```

Also update `startCompute` to accept an optional payload body:

```typescript
export async function startCompute(
  computeType: string,
  payload?: Record<string, unknown>   // add this parameter
): Promise<ComputeJob> {
  const body = payload ? JSON.stringify(payload) : undefined;
  ...
}
```

---

### D4 — `src/components/compare/ContactLexemePanel.tsx` (new component)

**Owner:** ParseBuilder  
**Estimated effort:** 2 hours

**Purpose:** Dashboard showing which concepts have contact forms populated, with controls to trigger the fetch.

**Layout:**

```
┌─ Contact Language Lexemes ──────────────────────────────────────────┐
│  [Fetch Missing ▾] [Overwrite All ▾]   Provider: [LLM ▾]           │
│  Languages: [ar ✓] [fa ✓] [ckb ✓] [tr ○]                          │
│                                                                      │
│  Coverage:                                                           │
│  ar  ████████████████░░░░  78/82 concepts   (4 empty)               │
│  fa  ████████████████████  82/82 concepts   complete                │
│  ckb ████████░░░░░░░░░░░░  41/82 concepts   (41 empty)              │
│  tr  ░░░░░░░░░░░░░░░░░░░░   0/82 concepts   not fetched             │
│                                                                      │
│  [Running... cognate 37/82 — fetching Sorani forms]                │
│                                                                      │
│  Recent results (last fetch):                                        │
│  water   ar: maːʔ, miːah ✓   fa: aːb ✓   ckb: aːw ✓               │
│  fire    ar: naːr ✓           fa: aːtaʃ ✓  ckb: aːgiː ✓            │
│  stone   ar: ħadʒar ✓        fa: sang ✓    ckb: berd ✓             │
└──────────────────────────────────────────────────────────────────────┘
```

**State:**
- `contactLexemeStore` (Zustand) or local state with `useContactLexeme` hook
- Coverage computed from `sil_contact_languages.json` via new GET endpoint
- Job progress via `useComputeJob("contact-lexemes")`

**Integration point:** Mount inside `CompareMode.tsx` as a collapsible panel alongside BorrowingPanel.

---

### D5 — `GET /api/contact-lexemes/coverage` — new read endpoint

**Purpose:** Return per-language, per-concept fill status without triggering a compute job.

**Response:**
```json
{
  "languages": {
    "ar": { "total": 82, "filled": 78, "empty": 4, "concepts": { "water": ["maːʔ"], "fire": ["naːr"], ... } },
    "fa": { "total": 82, "filled": 82, "empty": 0 },
    "ckb": { "total": 82, "filled": 41, "empty": 41 },
    "tr": { "total": 82, "filled": 0, "empty": 82 }
  }
}
```

Reads directly from `sil_contact_languages.json` — no compute needed.

---

### D6 — `src/api/types.ts` additions

```typescript
export interface ContactLexemeCoverage {
  languages: Record<string, {
    total: number;
    filled: number;
    empty: number;
    concepts: Record<string, string[]>;  // concept_en → IPA forms
  }>;
}

export interface ContactLexemeFetchOptions {
  provider?: "llm" | "wiktionary" | "csv" | "auto";
  languages?: string[];
  overwrite?: boolean;
}
```

---

### D7 — Tests

**Unit tests** (`src/__tests__/contactLexemes.test.ts`):
- `ContactLexemePanel` renders with empty coverage
- Coverage bars update when store has data
- "Fetch Missing" button triggers `startContactLexemeFetch()`
- Progress updates via `useComputeJob`

**Integration test** (extend `src/__tests__/apiRegression.test.ts`):
- `GET /api/contact-lexemes/coverage` returns expected shape
- `POST /api/compute/contact-lexemes` returns `{jobId, status: "running"}`

**Python unit test** (`python/compare/test_contact_lexeme_fetcher.py`):
- `_validate_ipa_form("maːʔ")` → True
- `_validate_ipa_form("مَاء")` → False (Arabic script, not IPA)
- `merge_results_into_config()` does not overwrite when `overwrite=False`
- LLM response parser handles malformed JSON gracefully

---

## IPA Validation Rules

The fetcher must reject non-IPA input. Arabic script (`مَاء`), Latin transliteration (`ma'a`), and English spellings (`water`) are all invalid.

```python
# Allowed IPA characters (broad transcription)
IPA_PATTERN = re.compile(
    r'^[a-z'  # basic Latin (vowel+consonant letters)
    r'æɑɒɐɛɜɪɨʉʊɯɵøœɶəɤ'  # IPA vowels
    r'βθðʃʒʂʐɕʑɸχɣħʕʔʡʢ'  # fricatives
    r'ʈɖɗɓɠɦɬɮɹɺɻɽɴɲŋɱ'   # other consonants
    r'ʋwjɰʍ'               # approximants
    r'ːˈˌ͡ ˑ.,-]+'         # diacritics, length, tone
    r'$'
)
```

---

## Data Flow into Enrichments

After fetching, the user triggers a new `POST /api/compute/cognates` job. This re-runs the full enrichment pipeline:

```
sil_contact_languages.json  (now populated)
        │
        ▼
_compute_cognates() in server.py
  1. load_contact_language_data() → reads new forms
  2. _compute_cognate_sets_with_lingpy() → LexStat on SK speakers
  3. compute_similarity_scores() → edit distance SK forms ↔ contact forms
        │
        ▼
enrichments.similarity[concept][speaker][language]
  { "score": 0.18, "has_reference_data": true }  ← now populated
        │
        ▼
BorrowingPanel.tsx  ← similarity bars now meaningful
```

**Threshold interpretation for borrowing:**
- `score < 0.35` → strong borrowing candidate (phonetically close)
- `0.35 ≤ score < 0.60` → possible borrowing (moderate similarity)
- `score ≥ 0.60` → likely native / distant

These thresholds are informed by the existing `lexstat_threshold: 0.6` and should be configurable.

---

## Implementation Order

| Step | File | Time | Blocker |
|------|------|------|---------|
| D1 | `python/compare/contact_lexeme_fetcher.py` | 4h | None |
| D2 | `python/server.py` — compute type + coverage endpoint | 2h | D1 |
| D3 | `src/api/client.ts` + `types.ts` | 30m | D2 |
| D4 | `src/components/compare/ContactLexemePanel.tsx` | 2h | D3 |
| D5 | Mount in `CompareMode.tsx` | 30m | D4 |
| D6 | Tests (Python + Vitest) | 2h | D4 |
| D7 | Integration: run fetch + re-run cognates + verify scores | 1h | D6 |

**Total estimate:** ~12 hours development time

---

## Branch Strategy

```
origin/main
  └── feat/contact-lexemes  (new additive branch from current trunk)
```

Keep this on the later-stage test/build list rather than using C6 as a hard blocker. It becomes worth doing once onboarding/import and broader end-to-end testing are working well enough that new similarity signals can actually be exercised in the real workflow. This is additive work, not a blocker for thesis submission — but having real similarity scores would make the borrowing adjudication section of the thesis concrete.

---

## Open Questions for Lucas

1. **LLM provider preference for fetching:** Grok (current default) or GPT-4o? The IPA output quality matters here — GPT-4o tends to be more reliable for narrow phonetic tasks.
2. **CKB forms:** Central Kurdish (Sorani) is closely related to SK — do you want CKB forms, or is the inter-dialect comparison out of scope for the thesis?
3. **ASJP as alternative source:** ASJP database covers Arabic (`ara`) and Persian (`pes`) with ~40 concepts from the Swadesh list. It's a downloadable `.tsv` file that could populate ~40% of forms without any API calls. Worth including as a zero-cost offline source?
4. **Borrowing threshold:** The `0.35` cutoff above is a reasonable heuristic. Do you have a specific threshold from the thesis methodology that should be used instead?
5. **Overwrite policy:** Once forms are fetched, should the user be able to manually edit individual concept/language entries in the UI, or is this researcher-editable via CSV only?
