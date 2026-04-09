# Lexibank Dataset Setup (CLEF)

This document covers local CLDF setup for the Contact Language Lexeme Fetcher (CLEF).

## What the fetcher reads

CLEF local scholarly providers automatically scan:

- `config/lexibank_data/**/cldf/*-metadata.json`

These providers use that path directly:

- `lingpy_wordlist` (LingPy `Wordlist.from_cldf`)
- `pycldf` (`pycldf.Dataset.from_metadata`)

So a plain git clone is enough to start using local datasets.

## Quick setup

From repo root:

```bash
mkdir -p config/lexibank_data

git clone https://github.com/lexibank/ids config/lexibank_data/ids
git clone https://github.com/lexibank/northeuralex config/lexibank_data/northeuralex
git clone https://github.com/lexibank/wold config/lexibank_data/wold
```

## Verify local CLDF discovery

```bash
python - <<'PY'
from pathlib import Path
root = Path('config/lexibank_data')
files = sorted(root.glob('**/cldf/*-metadata.json'))
print(f"metadata files: {len(files)}")
for p in files:
    print(p)
PY
```

If this prints metadata files, `lingpy_wordlist` and `pycldf` can consume them.

## Optional: pylexibank provider layer

`pylexibank` is optional and no-op if imports fail.

```bash
pip install pylexibank pylexibank-northeuralex pylexibank-ids pylexibank-wold
```

Current provider expectations in `python/compare/providers/pylexibank_provider.py`:

- module names: `northeuralex`, `ids`, `wold`

Quick import check:

```bash
python - <<'PY'
for mod in ('northeuralex', 'ids', 'wold'):
    try:
        __import__(mod)
        print(f"OK: {mod}")
    except Exception as e:
        print(f"FAIL: {mod}: {e}")
PY
```

## WOLD recovery notes (import issue)

If `wold` import fails in the optional `pylexibank` layer:

1. Keep the git clone at `config/lexibank_data/wold` (still usable by `lingpy_wordlist` + `pycldf`).
2. Treat `pylexibank` as best-effort, not blocking.
3. Continue fetches with default provider cascade; CLEF will fall through to later providers.

This keeps WOLD usable even when Python package import metadata is inconsistent.

## CKB (Sorani) coverage strategy

### Current practical situation

For Southern Kurdish contact-language workflows, local datasets above improve Arabic/Persian/Turkish strongly, but **CKB coverage is still sparse or inconsistent** in practice.

### Recommended strategy (now)

1. Keep default provider cascade order (registry priority):
   - `csv_override -> lingpy_wordlist -> pycldf -> pylexibank -> asjp -> cldf -> wikidata -> wiktionary -> grokipedia -> literature`
2. Use CLEF panel + `/api/contact-lexemes/coverage` to identify unresolved CKB concepts.
3. Curate high-confidence CKB forms into `config/contact_forms_override.csv` with citations in your thesis notes.
4. When a stronger CKB scholarly dataset is found, clone it under `config/lexibank_data/<dataset>/` and re-run fetch (auto-discovered by local providers).

### Why this works

- Local CLDF datasets maximize reproducibility and citation quality.
- `csv_override` gives deterministic lock-in for adjudicated forms.
- `grokipedia`/`literature` remain controlled fallback for residual gaps.

## Minimal run recipe

1. Clone datasets (above).
2. Run contact-lexeme compute from Compare mode (or API compute job).
3. Check coverage endpoint:
   - `GET /api/contact-lexemes/coverage`
4. Fill remaining CKB gaps via override + curated sources.
