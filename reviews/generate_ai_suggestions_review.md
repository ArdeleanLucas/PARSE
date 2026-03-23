# Review — `python/generate_ai_suggestions.py`

## Overall

The file is readable, the verified-first intent is good, and preloading transcripts once is the right baseline shape. The biggest problems are not style issues — they are correctness issues in candidate retention, missing/unverified semantics, Unicode normalization, and phonetic matching recall.

---

### [MAJOR] Top-N truncation happens **before** client-side positional re-ranking, so the best candidate may never reach the UI

**Where:** `find_suggestions_for_pair()` lines 567-581; design context in `INTERFACES.md` / `PROJECT_PLAN.md` (client re-ranks by positional prior).

**Why it matters:**
The script sorts candidates by **base score only** and then cuts to `top_n`. For common forms, many segments will tie at `0.92` (`exact_ortho_match`). Python’s stable sort preserves transcript order, so the earliest exact matches win and later exact matches are discarded.

That breaks the intended architecture:
- precompute base scores server-side
- apply positional prior client-side

If the candidate near the expected timestamp was dropped during precomputation, the client cannot recover it no matter how good the positional prior is.

**Concrete failure mode:**
A synthetic transcript with 10 exact `yek` hits returns only the first 5 segment starts: `[0, 100, 200, 300, 400]`. A much better hit at `700s` never reaches the client.

**Recommendation:**
- Do **not** truncate purely on base score.
- Either:
  - keep a much larger raw pool per concept×speaker and let the client prune after re-ranking, or
  - keep top-N **per method/time bucket** rather than top-N globally, or
  - incorporate a coarse positional tie-break before truncation when anchors exist.

---

### [MAJOR] Explicit `missing` status does not actually mark an entry as missing if stale ortho/IPA text is present

**Where:** `_speaker_has_concept()` lines 369-376; `_speaker_is_missing()` lines 380-386.

**Why it matters:**
The comment says “reject explicitly missing entries”, but the implementation does not. For `status in ('missing', 'unknown', '?')`, the code just `pass`es and then falls through to the ortho/IPA check.

So an entry like:

```json
{"status": "missing", "ortho": "yek"}
```

is treated as **having** the concept, which means:
- suggestions are **not generated** for that speaker/concept pair
- fallback reference collection with `require_verified=False` can still ingest stale text from explicitly missing entries

That is exactly the kind of state drift this script needs to defend against.

**Recommendation:**
- Make explicit missing-like statuses override leftover text on the lenient path.
- Separate the semantics clearly:
  - `missing`
  - `present_unverified`
  - `present_verified`
  - `present_but_rejected/bad_cut` (if that state exists upstream)
- Add regression tests for all four cases.

---

### [MAJOR] No Unicode/script normalization means exact and fuzzy matching are much less reliable than they look

**Where:** `tokenize()` lines 203-214; `match_exact()` lines 221-232; `match_fuzzy()` lines 235-263.

**Why it matters:**
The code lowercases tokens/forms but does not normalize Unicode or common Arabic/Persian/Kurdish variants. In this dataset that is a real recall problem, not a theoretical one.

Examples the current code mishandles:
- `كە` vs `کە` → exact miss, downgraded to fuzzy
- `يەك` vs `یەك` → exact miss, downgraded to fuzzy
- `دە‌نگ` vs `دەنگ` (internal ZWNJ) → exact miss, downgraded to fuzzy

For short words, a single normalization difference can consume the full Levenshtein budget, and some variants will miss entirely.

**Recommendation:**
Introduce one shared `normalize_text_for_match()` helper and apply it consistently to:
- transcript tokens
- ortho reference forms
- fuzzy distance inputs

That helper should at minimum consider:
- `unicodedata.normalize(...)`
- folding Arabic/Persian `ك/ک`, `ي/ی`, etc.
- removing tatweel and bidi/zero-width marks **inside** tokens, not only at edges
- optionally stripping combining marks if they are not contrastive for search

---

### [MAJOR] “Romanized phonetic match” does not handle common romanization digraphs, so recall is far lower than the method name suggests

**Where:** `_IPA_CHAR_MAP` lines 95-147; `ipa_to_regex()` lines 153-191; `match_phonetic()` lines 266-285.

**Why it matters:**
The regex builder is character-by-character, but common romanized Kurdish spellings are often **multi-character**:
- `ʃ` → `sh`
- `ʒ` → `zh` / `j`
- `č` → `ch`
- `x` → `kh`
- `ɣ` → `gh`

With the current logic, these all fail on full-match even though they are exactly the kinds of transcript spellings this matcher is supposed to catch.

Examples that currently fail:
- `ʃev` vs `shev`
- `ʒan` vs `zhan`
- `čaw` vs `chaw`
- `xan` vs `khan`
- `ɣar` vs `ghar`

So the phonetic tier is presently biased toward very short/simple forms like `jek`, but misses many realistic romanized tokens.

**Recommendation:**
Use alternations that allow digraphs, e.g.:
- `ʃ` → `(?:sh|ş|ʃ|s)`
- `ʒ` → `(?:zh|j|ʒ)`
- `č` → `(?:ch|č|c)`
- `x` → `(?:kh|x|χ)`
- `ɣ` → `(?:gh|ɣ|g)`

Also precompile these regexes once per concept instead of relying on repeated `re.fullmatch()` over raw pattern strings.

---

### [MINOR] Verified-first fallback is reasonable, but the output loses provenance when it falls back to unverified forms

**Where:** `generate_all_suggestions()` lines 659-676 and 699-713.

**Why it matters:**
When no verified forms exist, the script warns on `stderr` and silently falls back to unverified forms. After JSON is written, that provenance is gone. The UI/downstream tooling cannot distinguish:
- suggestions built from verified references
- suggestions built from unverified fallback material

Given the recent concern about garbage reference forms, that distinction seems worth preserving in the data, not just in logs.

**Recommendation:**
Add explicit provenance such as:
- concept-level `reference_form_source: "verified" | "unverified_fallback"`
- or per-suggestion `reference_form_source`

That would let the UI dim or annotate lower-trust suggestions.

---

### [MINOR] The inner loop repeats avoidable work across concept×speaker scans

**Where:** `find_suggestions_for_pair()` lines 478-530; `generate_all_suggestions()` lines 652-722.

**Why it matters:**
The script already avoids repeated disk reads, which is good. But it still repeats a lot of CPU work:
- tokenizing the same transcript segments for every concept
- lowercasing the same reference forms over and over
- recomputing Levenshtein against the same token/form pairs across many concepts
- building phonetic regex strings repeatedly

This is probably acceptable for the current thesis-scale dataset, but it is the main performance hotspot if you add speakers, alternate transcripts, or rerun this often.

**Recommendation:**
- pre-tokenize and normalize each transcript once when loading it
- pre-normalize reference forms once per concept
- optionally memoize `(token, form) -> distance`
- store compiled phonetic regex objects, not raw strings

---

### [MINOR] Missing regression tests and input validation around the highest-risk logic paths

**Where:** whole file / CLI.

**Why it matters:**
The tricky logic here is exactly the kind that regresses quietly:
- verified-only reference extraction
- unverified fallback behavior
- explicit `missing` overriding leftover text
- Unicode normalization cases
- phonetic digraph matching
- top-N retention vs later positional re-ranking

Right now there is no visible test coverage for any of those paths.

**Recommended minimum tests:**
1. `status: missing` + leftover ortho still counts as missing
2. verified forms are preferred over unverified forms
3. fallback to unverified is explicit in output metadata
4. `ك/ک`, `ي/ی`, internal ZWNJ normalize to the same match key
5. phonetic matcher accepts `sh/zh/ch/kh/gh`
6. top-N selection does not drop later exact hits that positional re-ranking would need
7. CLI rejects `--top-n <= 0` and malformed anchors JSON shapes

---

### [NIT] Small maintainability leftovers

**Where:** `used_verified` at line 663/670 is never read; `concept_id` and `target_speaker` parameters in `find_suggestions_for_pair()` are currently unused.

These are harmless, but they make the file look less settled than it is.

---

## Bottom line

The file is close in structure, but I would not trust its output yet for high-value review work without fixing the four major issues above:
1. pre-truncation before positional re-ranking
2. explicit missing status being ignored
3. lack of Unicode/script normalization
4. phonetic matcher missing digraph-based romanization
