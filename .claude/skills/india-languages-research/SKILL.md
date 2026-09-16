---
name: india-languages-research
description: "Indian languages academic research: Glottolog/WALS/CLDF/Lexibank/Ethnologue/ELAR/LSI lookup; Indo-Aryan, Dravidian, Munda, Tibeto-Burman; SIL fonts, Keyman, FLEx export, IPA/IAST/ISO 15919 transliteration; LSA citation; fieldwork, typology, phylogenetics."
---

# India Languages Research

End-to-end research workflow for languages of India — source discovery, data retrieval, SIL toolchain, script/transliteration, citation.

## When to Activate

- Researching an Indian language or family (phonology, morphology, syntax, typology, history)
- Field documentation work requiring prior resources or archives
- Pulling lexical/typological data for CLDF pipelines or FLEx databases
- Locating endangered/underdocumented language resources
- Formatting references for a dissertation, SIL report, or journal paper
- Phylogenetic or comparative work intersecting South Asian data

## Key Sources

| Source | Best For | Access |
|--------|----------|--------|
| **Glottolog** | Language ID, family trees, bibliography | `https://glottolog.org/resource/languoid/id/<glottocode>` |
| **Ethnologue** | Vitality, speaker counts, country reports | `https://www.ethnologue.com` (subscription) |
| **WALS** | Typological features per language | `https://wals.info/languoid/lect/wals_code_<code>` |
| **CLDF / Lexibank** | Wordlists, cognate sets | `https://github.com/lexibank` |
| **SIL Language and Culture Archive** | SIL reports, grammars, fieldwork docs | `https://www.sil.org/resources` |
| **Endangered Languages Project** | Documentation status, community resources | `https://www.endangeredlanguages.com` |
| **SOAS ELAR** | Fieldwork recordings, primary archives | `https://elar.soas.ac.uk` |
| **LSI / DSAL** | Grierson grammars + wordlists (1903–28) | `https://dsal.uchicago.edu/books/lsi/` |
| **Google Scholar / ACL Anthology** | Secondary literature, NLP papers | `https://aclanthology.org` |

## Phase 1: Language Identification

Resolve canonical identity before pulling data — sources use different codes.

1. Look up on Glottolog: `https://glottolog.org/glottolog?search=<name>`
2. Record the **Glottocode** (e.g., `telu1251`) — stable cross-source ID.
3. Note the **ISO 639-3 code** (e.g., `tel`) — needed for WALS, CLDF, archives.
4. Confirm family: Indo-Aryan → Dravidian → Munda → Tibeto-Burman → isolate.
5. Note endangerment status from Glottolog `aes` field or Endangered Languages Project.

**Checks:**
- [ ] Glottocode confirmed
- [ ] ISO 639-3 confirmed
- [ ] Family and sub-branch identified
- [ ] Endangerment / documentation status noted

## Phase 2: Source Discovery by Research Type

### 2A — Phonological / Morphological

1. DSAL digitized grammars: `https://dsal.uchicago.edu/reference/grammar/`
2. ELAR fieldwork audio: query by ISO code or name.
3. Google Scholar: `"<language>" phonology` or arxiv skill for computational phonology.
4. Indo-Aryan: **DIALING** (Dialectal Atlas of Indic Languages).
5. Dravidian: **DEDR** at `https://dsalsrv04.uchicago.edu/dictionaries/burrow/`

### 2B — Typological

1. WALS features: `https://wals.info/languoid/lect/wals_code_<code>`
2. Contact phenomena: cross-reference **APiCS** or **AUTOTYP**.
3. Areal: search `South Asian linguistic area <feature>` on Scholar.

### 2C — Lexical / Phylogenetic (CLDF / FLEx)

1. Search Lexibank:
   ```bash
   gh search repos --topic cldf --topic south-asia
   ```
2. Clone dataset; inspect `cldf/parameters.csv`, `cldf/forms.csv`.
3. Indo-Aryan Swadesh: **IELex** (Indo-European Lexical Cognacy Database).
4. Dravidian cognates: CLDF-Dravidian datasets or DEDR mappings.
5. Munda: **ASJP** — `https://asjp.clld.org/languages/<ISO>`
6. FLEx users: export as LIFT XML or SFM → convert with `cldfbench`.

### 2D — Historical / Documentary

1. LSI volumes: `https://dsal.uchicago.edu/books/lsi/`
2. Archive.org: `site:archive.org linguistic survey india <language>`
3. Manuscript/inscription: **Indic Script Corpus** or **MUFI**.

## Phase 3: Script and Transliteration

### Family → Script

| Family | Primary Scripts | Transliteration |
|--------|----------------|-----------------|
| Indo-Aryan (N) | Devanagari, Gurmukhi, Bengali, Gujarati, Odia | IAST, ISO 15919, Harvard-Kyoto |
| Dravidian | Tamil, Telugu, Kannada, Malayalam | ISO 15919 |
| Munda | Ol Chiki (Santali), Latin, Devanagari | SIL / IPA-based |
| Tibeto-Burman | Tibetan, minority scripts | Wylie, THDL, IPA |

### Conventions

- **IAST** — standard for Indo-Aryan historical linguistics; all Sanskrit-derived forms.
- **ISO 15919** — extends IAST to Dravidian; preferred for comparative work.
- **IPA** — always specify dialect/variety.
- Use the dataset's declared `orthography_profile` in CLDF/FLEx — do not silently convert.

### SIL Fonts

| Script | Font | Notes |
|--------|------|-------|
| Latin + diacritics (IAST/IPA) | **Charis SIL**, **Doulos SIL** | Full Unicode IPA |
| Devanagari | **Annapurna SIL** | Minority Indo-Aryan languages |
| Tamil | Noto Serif Tamil | No dedicated SIL font |
| Ol Chiki | Noto Sans Ol Chiki | Unicode Ol Chiki encoding |

All SIL fonts: `https://software.sil.org/fonts/`

### Input / Keyboard

- **Keyman** (SIL): `https://keyman.com` — hundreds of Indian script layouts
- **SIL IPA keyboard** — phonetic transcription on any OS
- macOS/Windows: ITRANS or InScript for major scripts
- FLEx: set writing system keyboard to Keyman before data entry.

### Practical Tips

- Script conversion: **Aksharamukha** (`https://aksharamukha.appspot.com`)
- Python: `indic-transliteration` — Devanagari ↔ IAST ↔ ISO 15919
- IPA for Hindi/Urdu: `indicnlp` or hand-map from phonemic inventory

## Phase 4: Citation Formatting

**Leipzig Glossing Rules** for interlinear examples. **LSA Unified Stylesheet** for references (SIL archive format is similar author-date).

### Reference Format (LSA)

```
Author, First. Year. Title. Journal volume(issue). pages. DOI.
Author, First & Second Author. Year. Book Title. Place: Publisher.
```

```
Masica, Colin P. 1991. The Indo-Aryan Languages. Cambridge: Cambridge University Press.
Krishnamurti, Bhadriraju. 2003. The Dravidian Languages. Cambridge: Cambridge University Press.
Nordhoff, Sebastian & Harald Hammarström. 2011. Glottolog/Langdoc. ISWC Workshop. 1–3.
```

### Interlinear (Leipzig)

```
tʃʰoʈ-a   laɽ-ka   dʰ-il-e   ʤa-ta   hɛ
small-M   boy-M    slow-ADV  go-IPFV  AUX
'The small boy goes slowly.'
```

## Phase 5: Quality Checklist

- [ ] Glottocode and ISO 639-3 verified for every language
- [ ] Source edition confirmed (LSI vol. / Lexibank commit hash / WALS access date)
- [ ] Script/transliteration scheme explicitly declared
- [ ] IPA transcriptions specify variety and source
- [ ] CLDF/FLEx imports validated against declared `orthography_profile`
- [ ] SIL font appropriate for script and publication target
- [ ] Citations follow LSA Unified Stylesheet (or SIL archive format)
- [ ] Endangerment/ethics note included for underdocumented languages
- [ ] Community consent / data-sharing agreements confirmed for primary fieldwork data

## Examples

### Pull Gondi typological data

```bash
# Glottocode: gond1265 (Northern Gondi), ISO: gno — Dravidian > South-Central
open https://wals.info/languoid/lect/wals_code_gnd
gh search repos "gondi cldf" --topic cldf
curl "https://asjp.clld.org/languages/GONDI" -H "Accept: application/json"
open "https://www.sil.org/search?query=gondi"
```

### Locate grammar for an underdocumented Munda language (Kharia)

```bash
# Glottocode: khar1287, ISO: khr — Munda > Kherwarian
open "https://glottolog.org/glottolog?search=kharia"
open "https://elar.soas.ac.uk/Search?q=kharia"
open "https://dsal.uchicago.edu/books/lsi/"  # Vol. IV: Munda and Dravidian (Grierson 1906)
open "https://scholar.google.com/scholar?q=Kharia+grammar+phonology"
```

## Anti-patterns

- Never use ISO 639-1 (2-letter) codes — always ISO 639-3.
- Never treat Glottolog trees as phylogenetic trees without verifying the grouping is genealogical, not areal.
- Never import CLDF data without confirming the orthography profile — silent mismatches corrupt cognate sets.
- Never cite LSI without the volume year — the survey ran 1898–1928 across 19+ volumes.
- Never say "Hindi" without specifying dialect/variety for phonological claims.

## Integration

- `lingpy-cldf-lexibank` — CLDF manipulation and cognate detection
- `arxiv` — computational linguistics papers on Indian NLP/phonology
- `dspy` — structured extraction from scanned grammar PDFs
- `ocr-and-documents` — reading LSI scans and old fieldwork PDFs
- `thesis-research-citations` — bibliography management in LSA/SIL format
- `whisper` — transcribing fieldwork audio before FLEx import
